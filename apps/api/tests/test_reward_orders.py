from __future__ import annotations

import pyotp
from sqlalchemy import func, select

from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.reward_catalog import RewardCatalogItem
from password_detective.db.models.reward_order import (
    RewardEntitlementGrant,
    RewardInventoryEvent,
    RewardOrder,
)
from password_detective.db.models.user import User, UserRole
from password_detective.modules.rewards.service import process_pending_fulfillments

PASSWORD = "SyntheticRewardOrdersPass123!"


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], str]:
    payload = {
        "username": f"rw_order_{suffix}",
        "email": f"reward-order-{suffix}@synthetic.example.com",
        "password": PASSWORD,
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    login = client.post(
        "/api/v1/auth/login", json={"login": payload["username"], "password": PASSWORD}
    )
    assert login.status_code == 200
    with client.app.state.database.session_factory() as db:
        user_id = db.scalar(select(User.id).where(User.username == payload["username"]))
        assert user_id is not None
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, user_id


def _admin_session(client, suffix: str) -> dict[str, str]:
    headers, user_id = _register_and_login(client, f"admin_{suffix}")
    with client.app.state.database.session_factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()
    setup = client.post("/api/v1/admin/totp/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert (
        client.post(
            "/api/v1/admin/totp/confirm",
            headers=headers,
            json={"code": pyotp.TOTP(secret).now()},
        ).status_code
        == 200
    )
    login = client.post(
        "/api/v1/auth/login",
        json={
            "login": f"rw_order_admin_{suffix}",
            "password": PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create_catalog(client, admin_headers: dict[str, str], slug: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/admin/rewards/catalog",
        headers={**admin_headers, "Idempotency-Key": f"reward-catalog-{slug}-0001"},
        json={
            "slug": slug,
            "name": "合成社区支持权益",
            "description": "用于订单闭环测试的合成虚拟权益。",
            "kind": "virtual",
            "cost_points": 25,
            "stock": 8,
            "per_user_limit": 3,
            "category": "community",
            "tags": ["featured", "community"],
            "sort_weight": 10,
            "entitlement_key": "community_supporter",
            "entitlement_duration_days": 30,
            "redeem_start_at": None,
            "redeem_end_at": None,
            "status": "active",
            "reason_code": "synthetic_catalog_setup",
        },
    )
    assert response.status_code == 201
    return response.json()


def _credit_points(client, user_id: str, amount: int, reference_id: str) -> None:
    with client.app.state.database.session_factory() as db:
        db.add(
            PointsLedger(
                user_id=user_id,
                amount=amount,
                event_type="synthetic.reward.credit",
                reference_id=reference_id,
                status=PointsLedgerStatus.POSTED,
            )
        )
        db.commit()


def test_reward_order_is_idempotent_and_worker_grants_entitlement(client):
    admin_headers = _admin_session(client, "fulfillment")
    item = _create_catalog(client, admin_headers, "synthetic-order-entitlement")
    user_headers, user_id = _register_and_login(client, "fulfillment")
    _credit_points(client, user_id, 200, "synthetic-order-credit-1")

    request_headers = {
        **user_headers,
        "Idempotency-Key": "reward-order-fulfillment-0001",
    }
    created = client.post(
        "/api/v1/rewards/orders",
        headers=request_headers,
        json={"catalog_item_id": item["id"], "quantity": 2},
    )
    assert created.status_code == 201
    assert created.json()["status"] == "pending_fulfillment"
    assert created.json()["total_cost_points"] == 50
    assert created.json()["available_points"] == 150

    repeated = client.post(
        "/api/v1/rewards/orders",
        headers=request_headers,
        json={"catalog_item_id": item["id"], "quantity": 2},
    )
    assert repeated.status_code == 201
    assert repeated.json()["id"] == created.json()["id"]

    with client.app.state.database.session_factory() as db:
        assert db.scalar(select(func.count(RewardOrder.id))) == 1
        assert (
            db.scalar(
                select(func.count(PointsLedger.id)).where(
                    PointsLedger.event_type == "reward.redeemed"
                )
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count(RewardInventoryEvent.id)).where(
                    RewardInventoryEvent.order_id == created.json()["id"]
                )
            )
            == 1
        )
        catalog = db.get(RewardCatalogItem, item["id"])
        assert catalog is not None
        assert catalog.stock == 6
        result = process_pending_fulfillments(db)
        assert result == {"processed": 1, "succeeded": 1, "retried": 0, "failed": 0}

    detail = client.get(f"/api/v1/rewards/orders/{created.json()['id']}", headers=user_headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "fulfilled"
    assert detail.json()["entitlement"]["entitlement_key"] == "community_supporter"
    assert detail.json()["fulfillment"]["status"] == "succeeded"
    with client.app.state.database.session_factory() as db:
        assert db.scalar(select(func.count(RewardEntitlementGrant.id))) == 1


def test_pending_order_cancel_restores_points_and_inventory_once(client):
    admin_headers = _admin_session(client, "cancel")
    item = _create_catalog(client, admin_headers, "synthetic-order-cancel")
    user_headers, user_id = _register_and_login(client, "cancel")
    _credit_points(client, user_id, 100, "synthetic-order-credit-2")

    created = client.post(
        "/api/v1/rewards/orders",
        headers={**user_headers, "Idempotency-Key": "reward-order-cancel-create-0001"},
        json={"catalog_item_id": item["id"], "quantity": 1},
    )
    assert created.status_code == 201
    cancel_headers = {
        **user_headers,
        "Idempotency-Key": "reward-order-cancel-action-0001",
    }
    cancelled = client.post(
        f"/api/v1/rewards/orders/{created.json()['id']}/cancel", headers=cancel_headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["available_points"] == 100
    repeated = client.post(
        f"/api/v1/rewards/orders/{created.json()['id']}/cancel", headers=cancel_headers
    )
    assert repeated.status_code == 200
    assert repeated.json()["compensated_at"] == cancelled.json()["compensated_at"]

    with client.app.state.database.session_factory() as db:
        catalog = db.get(RewardCatalogItem, item["id"])
        assert catalog is not None
        assert catalog.stock == 8
        assert (
            db.scalar(
                select(func.count(PointsLedger.id)).where(
                    PointsLedger.event_type == "reward.cancelled_compensation"
                )
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count(RewardInventoryEvent.id)).where(
                    RewardInventoryEvent.order_id == created.json()["id"]
                )
            )
            == 2
        )


def test_inventory_adjustment_and_operations_stats_require_admin_mfa(client):
    admin_headers = _admin_session(client, "operations")
    item = _create_catalog(client, admin_headers, "synthetic-operations")
    user_headers, _ = _register_and_login(client, "operations")

    denied = client.get("/api/v1/admin/rewards/operations/stats", headers=user_headers)
    assert denied.status_code == 403
    adjusted = client.post(
        f"/api/v1/admin/rewards/catalog/{item['id']}/inventory-adjustments",
        headers={**admin_headers, "Idempotency-Key": "reward-inventory-adjust-0001"},
        json={
            "delta": 5,
            "reason_code": "restock",
            "expected_version": item["version"],
            "note": "合成库存补充",
        },
    )
    assert adjusted.status_code == 200
    assert adjusted.json()["stock"] == 13
    assert adjusted.json()["version"] == item["version"] + 1

    events = client.get(
        f"/api/v1/admin/rewards/catalog/{item['id']}/inventory-events",
        headers=admin_headers,
    )
    assert events.status_code == 200
    assert events.json()["total"] == 2
    assert events.json()["items"][0]["delta"] == 5
    stats = client.get("/api/v1/admin/rewards/operations/stats", headers=admin_headers)
    assert stats.status_code == 200
    assert stats.json()["total_orders"] == 0
