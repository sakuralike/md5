from __future__ import annotations

import pyotp
from sqlalchemy import select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.user import User, UserRole

PASSWORD = "SyntheticRewardsPass123!"


def _admin_session(client, suffix: str) -> tuple[dict[str, str], str]:
    registration = {
        "username": f"rewards_admin_{suffix}",
        "email": f"rewards-admin-{suffix}@synthetic.example.com",
        "password": PASSWORD,
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    initial = client.post(
        "/api/v1/auth/login", json={"login": registration["username"], "password": PASSWORD}
    )
    assert initial.status_code == 200
    initial_headers = {"Authorization": f"Bearer {initial.json()['access_token']}"}
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()
        user_id = user.id
    setup = client.post("/api/v1/admin/totp/setup", headers=initial_headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert client.post(
        "/api/v1/admin/totp/confirm",
        headers=initial_headers,
        json={"code": pyotp.TOTP(secret).now()},
    ).status_code == 200
    authenticated = client.post(
        "/api/v1/auth/login",
        json={
            "login": registration["username"],
            "password": PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert authenticated.status_code == 200
    return {"Authorization": f"Bearer {authenticated.json()['access_token']}"}, user_id


def _catalog_payload(slug: str, *, status: str = "active") -> dict[str, object]:
    return {
        "slug": slug,
        "name": "合成积分权益",
        "description": "用于合成环境验收的虚拟权益目录项目。",
        "kind": "virtual",
        "cost_points": 25,
        "stock": 8,
        "per_user_limit": 2,
        "status": status,
        "reason_code": "synthetic_catalog_setup",
    }


def test_public_catalog_hides_drafts_and_exposes_only_stock_band(client):
    admin_headers, admin_id = _admin_session(client, "public")
    active = client.post(
        "/api/v1/admin/rewards/catalog",
        headers={**admin_headers, "Idempotency-Key": "reward-create-public-001"},
        json=_catalog_payload("synthetic-active"),
    )
    assert active.status_code == 201
    draft = client.post(
        "/api/v1/admin/rewards/catalog",
        headers={**admin_headers, "Idempotency-Key": "reward-create-draft-001"},
        json=_catalog_payload("synthetic-draft", status="draft"),
    )
    assert draft.status_code == 201

    public = client.get("/api/v1/rewards/catalog")
    assert public.status_code == 200
    assert [item["slug"] for item in public.json()["items"]] == ["synthetic-active"]
    assert public.json()["items"][0]["stock_status"] == "limited"
    assert "stock" not in public.json()["items"][0]
    assert public.json()["available_points"] is None

    with client.app.state.database.session_factory() as db:
        db.add(
            PointsLedger(
                user_id=admin_id,
                amount=100,
                event_type="synthetic.reward.test",
                reference_id="synthetic-reward-points-1",
                status=PointsLedgerStatus.POSTED,
            )
        )
        db.commit()
    authenticated = client.get("/api/v1/rewards/catalog", headers=admin_headers)
    assert authenticated.status_code == 200
    assert authenticated.json()["available_points"] == 100


def test_admin_catalog_requires_mfa_idempotency_and_version(client):
    registration = {
        "username": "rewards_user_only",
        "email": "rewards-user-only@synthetic.example.com",
        "password": PASSWORD,
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login", json={"login": registration["username"], "password": PASSWORD}
    )
    user_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    denied = client.get("/api/v1/admin/rewards/catalog", headers=user_headers)
    assert denied.status_code == 403

    admin_headers, _ = _admin_session(client, "governance")
    missing_key = client.post(
        "/api/v1/admin/rewards/catalog",
        headers=admin_headers,
        json=_catalog_payload("synthetic-key"),
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["code"] == "request.invalid_idempotency_key"

    created = client.post(
        "/api/v1/admin/rewards/catalog",
        headers={**admin_headers, "Idempotency-Key": "reward-create-governance-001"},
        json=_catalog_payload("synthetic-governance"),
    )
    assert created.status_code == 201
    item = created.json()
    update_payload = {
        "name": "合成积分权益更新",
        "description": "更新后的合成虚拟权益说明。",
        "kind": "virtual",
        "cost_points": 30,
        "stock": 20,
        "per_user_limit": 1,
        "status": "active",
        "expected_version": item["version"],
        "reason_code": "synthetic_catalog_update",
    }
    updated = client.patch(
        f"/api/v1/admin/rewards/catalog/{item['id']}",
        headers={**admin_headers, "Idempotency-Key": "reward-update-governance-001"},
        json=update_payload,
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == item["version"] + 1

    conflict = client.patch(
        f"/api/v1/admin/rewards/catalog/{item['id']}",
        headers={**admin_headers, "Idempotency-Key": "reward-update-conflict-001"},
        json=update_payload,
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "reward.catalog_version_conflict"

    with client.app.state.database.session_factory() as db:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "admin.rewards.catalog.updated",
                AuditLog.target_id == item["id"],
            )
        )
        assert audit is not None
        assert audit.details["reason_code"] == "synthetic_catalog_update"


def test_catalog_rejects_physical_kind_and_invalid_limits(client):
    admin_headers, _ = _admin_session(client, "validation")
    physical = _catalog_payload("synthetic-physical")
    physical["kind"] = "physical"
    response = client.post(
        "/api/v1/admin/rewards/catalog",
        headers={**admin_headers, "Idempotency-Key": "reward-create-physical-001"},
        json=physical,
    )
    assert response.status_code == 422

    invalid = _catalog_payload("synthetic-invalid")
    invalid["cost_points"] = 0
    response = client.post(
        "/api/v1/admin/rewards/catalog",
        headers={**admin_headers, "Idempotency-Key": "reward-create-invalid-001"},
        json=invalid,
    )
    assert response.status_code == 422
