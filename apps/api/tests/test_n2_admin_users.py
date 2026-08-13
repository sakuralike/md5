from __future__ import annotations

from datetime import timedelta

import pyotp
from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.privacy_request import (
    PrivacyDeletionRequest,
    PrivacyDeletionStatus,
    PrivacyExport,
    PrivacyExportStatus,
)
from password_detective.db.models.reputation_event import ReputationEvent
from password_detective.db.models.user import User, UserRole, UserStatus

PASSWORD = "SyntheticUsersPass123!"


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], dict[str, str]]:
    registration = {
        "username": f"users_{suffix}",
        "email": f"users-{suffix}@synthetic.example.com",
        "password": PASSWORD,
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": PASSWORD},
    )
    assert login.status_code == 200
    return registration, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _privileged_headers(
    client,
    *,
    suffix: str,
    role: UserRole,
) -> tuple[dict[str, str], str]:
    registration, initial_headers = _register_and_login(client, suffix)
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = role
        db.commit()
        user_id = user.id

    setup = client.post("/api/v1/admin/totp/setup", headers=initial_headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    confirm = client.post(
        "/api/v1/admin/totp/confirm",
        headers=initial_headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert confirm.status_code == 200
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


def _seed_user_governance_data(client, user_id: str) -> None:
    now = utc_now()
    with client.app.state.database.session_factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        user.role = UserRole.TRUSTED_CONTRIBUTOR
        user.status = UserStatus.DISABLED
        user.reputation_score = 71
        db.add_all(
            [
                PointsLedger(
                    user_id=user_id,
                    amount=40,
                    event_type="synthetic.credit",
                    reference_id="synthetic-credit-1",
                    status=PointsLedgerStatus.POSTED,
                ),
                PointsLedger(
                    user_id=user_id,
                    amount=-7,
                    event_type="synthetic.debit",
                    reference_id="synthetic-debit-1",
                    status=PointsLedgerStatus.POSTED,
                ),
                PointsLedger(
                    user_id=user_id,
                    amount=99,
                    event_type="synthetic.pending",
                    reference_id="synthetic-pending-1",
                    status=PointsLedgerStatus.PENDING,
                ),
                ReputationEvent(
                    user_id=user_id,
                    amount=21,
                    event_type="synthetic.reputation",
                    reference_id="synthetic-reputation-1",
                    reason_code="synthetic_reason",
                    rule_version="test-v1",
                    previous_score=50,
                    next_score=71,
                ),
                PrivacyExport(
                    user_id=user_id,
                    status=PrivacyExportStatus.PROCESSING,
                ),
                PrivacyDeletionRequest(
                    user_id=user_id,
                    status=PrivacyDeletionStatus.PENDING,
                    cancel_before=now + timedelta(days=7),
                ),
            ]
        )
        db.commit()


def test_admin_user_governance_list_and_detail(client):
    target_registration, _ = _register_and_login(client, "target")
    admin_headers, _ = _privileged_headers(
        client,
        suffix="admin",
        role=UserRole.ADMIN,
    )
    moderator_headers, _ = _privileged_headers(
        client,
        suffix="moderator",
        role=UserRole.MODERATOR,
    )
    with client.app.state.database.session_factory() as db:
        target = db.scalar(
            select(User).where(User.username == target_registration["username"])
        )
        assert target is not None
        target_id = target.id
    _seed_user_governance_data(client, target_id)

    forbidden = client.get("/api/v1/admin/users", headers=moderator_headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "auth.forbidden"

    listed = client.get(
        "/api/v1/admin/users",
        headers=admin_headers,
        params={
            "status": "disabled",
            "role": "trusted_contributor",
            "query": target_registration["email"],
            "page": 1,
            "page_size": 10,
        },
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == target_id
    assert item["uid"] == target_id
    assert item["username"] == target_registration["username"]
    assert item["masked_email"].startswith("u***@s***.")
    assert target_registration["email"] not in listed.text
    assert item["status"] == "disabled"
    assert item["role"] == "trusted_contributor"
    assert item["reputation_score"] == 71
    assert item["active_session_count"] >= 1
    assert item["last_active_at"] is not None

    uid_search = client.get(
        "/api/v1/admin/users",
        headers=admin_headers,
        params={"query": target_id, "page": 1, "page_size": 10},
    )
    assert uid_search.status_code == 200
    assert uid_search.json()["total"] == 1
    assert uid_search.json()["items"][0]["uid"] == target_id

    username_search = client.get(
        "/api/v1/admin/users",
        headers=admin_headers,
        params={"query": target_registration["username"], "page": 1, "page_size": 10},
    )
    assert username_search.status_code == 200
    assert username_search.json()["items"][0]["uid"] == target_id

    detail = client.get(f"/api/v1/admin/users/{target_id}", headers=admin_headers)
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["id"] == target_id
    assert detail_body["uid"] == target_id
    assert detail_body["points_balance"] == 33
    assert detail_body["reputation_event_count"] == 1
    assert detail_body["pending_privacy_export_count"] == 1
    assert detail_body["pending_deletion_request_count"] == 1
    assert detail_body["total_session_count"] >= 1
    assert detail_body["submission_count"] == 0
    assert detail_body["trust_case_count"] == 0

    missing = client.get("/api/v1/admin/users/missing-synthetic", headers=admin_headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "admin.user_not_found"


def test_admin_user_governance_validates_filters_and_pagination(client):
    admin_headers, _ = _privileged_headers(
        client,
        suffix="validation_admin",
        role=UserRole.ADMIN,
    )

    invalid_status = client.get(
        "/api/v1/admin/users",
        headers=admin_headers,
        params={"status": "unknown"},
    )
    assert invalid_status.status_code == 422

    invalid_page_size = client.get(
        "/api/v1/admin/users",
        headers=admin_headers,
        params={"page_size": 101},
    )
    assert invalid_page_size.status_code == 422


def test_admin_can_login_and_reauthenticate_without_enabling_totp(client):
    registration, _ = _register_and_login(client, "no_totp_admin")
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()
        user_id = user.id

    admin_login = client.post(
        "/api/v1/admin/auth/login",
        headers={"Origin": "http://testserver"},
        json={"login": registration["email"], "password": PASSWORD},
    )
    assert admin_login.status_code == 200
    body = admin_login.json()
    assert body["user"]["uid"] == user_id
    assert body["user"]["totp_enabled"] is False
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    access = client.get("/api/v1/admin/access-check", headers=headers)
    assert access.status_code == 200
    assert access.json()["mfa"] == "not_verified"

    reauth = client.post(
        "/api/v1/admin/auth/reauthenticate",
        headers=headers,
        json={"current_password": PASSWORD},
    )
    assert reauth.status_code == 200
    assert reauth.json()["reauth_token"].startswith("reauth_")
