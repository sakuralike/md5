from __future__ import annotations

import pyotp
from sqlalchemy import func, select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.reauthentication_grant import ReauthenticationGrant
from password_detective.db.models.role_change_request import (
    RoleChangeRequest,
    RoleChangeRequestStatus,
)
from password_detective.db.models.user import User, UserRole
from password_detective.db.models.user_session import UserSession

PASSWORD = "SyntheticRoleGovernancePass123!"


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], dict[str, str], str]:
    registration = {
        "username": f"roles_{suffix}",
        "email": f"roles-{suffix}@synthetic.example.com",
        "password": PASSWORD,
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": PASSWORD},
    )
    assert login.status_code == 200
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user_id = user.id
    return registration, {"Authorization": f"Bearer {login.json()['access_token']}"}, user_id


def _privileged_session(
    client,
    *,
    suffix: str,
    role: UserRole,
) -> tuple[dict[str, str], str, str]:
    registration, initial_headers, user_id = _register_and_login(client, suffix)
    with client.app.state.database.session_factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        user.role = role
        db.commit()

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
    return (
        {"Authorization": f"Bearer {authenticated.json()['access_token']}"},
        user_id,
        secret,
    )


def _reauthenticate(client, headers: dict[str, str], secret: str) -> str:
    response = client.post(
        "/api/v1/admin/auth/reauthenticate",
        headers=headers,
        json={
            "purpose": "admin_user_governance",
            "current_password": PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert response.status_code == 200
    return response.json()["reauth_token"]


def test_role_change_requires_admin_dual_control_and_revokes_sessions(client):
    _, target_headers, target_id = _register_and_login(client, "target")
    requester_headers, requester_id, requester_secret = _privileged_session(
        client, suffix="requester", role=UserRole.ADMIN
    )
    reviewer_headers, reviewer_id, reviewer_secret = _privileged_session(
        client, suffix="reviewer", role=UserRole.ADMIN
    )
    moderator_headers, _, _ = _privileged_session(
        client, suffix="moderator", role=UserRole.MODERATOR
    )

    forbidden = client.get("/api/v1/admin/role-change-requests", headers=moderator_headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "auth.forbidden"

    requester_token = _reauthenticate(client, requester_headers, requester_secret)
    create_headers = {
        **requester_headers,
        "Idempotency-Key": "n2-role-create-0001",
    }
    payload = {
        "expected_role": "user",
        "requested_role": "trusted_contributor",
        "reason_code": "trust_promotion",
        "reauth_token": requester_token,
    }
    created = client.post(
        f"/api/v1/admin/users/{target_id}/role-change-requests",
        headers=create_headers,
        json=payload,
    )
    assert created.status_code == 201
    request_id = created.json()["request"]["id"]
    assert created.json()["request"]["status"] == "pending"
    assert created.json()["request"]["requested_by"] == requester_id

    replay = client.post(
        f"/api/v1/admin/users/{target_id}/role-change-requests",
        headers=create_headers,
        json={**payload, "reauth_token": "reauth_synthetic_replay_token"},
    )
    assert replay.status_code == 201
    assert replay.json() == created.json()

    self_review_token = _reauthenticate(client, requester_headers, requester_secret)
    self_review = client.post(
        f"/api/v1/admin/role-change-requests/{request_id}/approve",
        headers={**requester_headers, "Idempotency-Key": "n2-role-self-review-01"},
        json={
            "expected_status": "pending",
            "reason_code": "verified",
            "reauth_token": self_review_token,
        },
    )
    assert self_review.status_code == 403
    assert self_review.json()["code"] == "admin.role_change_self_approval_forbidden"

    with client.app.state.database.session_factory() as db:
        self_grant = db.scalar(
            select(ReauthenticationGrant).where(
                ReauthenticationGrant.token_hash.is_not(None),
                ReauthenticationGrant.user_id == requester_id,
            ).order_by(ReauthenticationGrant.created_at.desc())
        )
        assert self_grant is not None
        assert self_grant.consumed_at is None

    reviewer_token = _reauthenticate(client, reviewer_headers, reviewer_secret)
    approved = client.post(
        f"/api/v1/admin/role-change-requests/{request_id}/approve",
        headers={**reviewer_headers, "Idempotency-Key": "n2-role-approve-0001"},
        json={
            "expected_status": "pending",
            "reason_code": "verified",
            "reauth_token": reviewer_token,
        },
    )
    assert approved.status_code == 200
    assert approved.json()["request"]["status"] == "approved"
    assert approved.json()["request"]["reviewed_by"] == reviewer_id
    assert approved.json()["revoked_session_count"] >= 1

    target_access = client.get("/api/v1/me/profile", headers=target_headers)
    assert target_access.status_code == 401
    assert target_access.json()["code"] == "auth.session_revoked"

    filtered = client.get(
        "/api/v1/admin/role-change-requests?status=approved",
        headers=requester_headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["id"] == request_id

    with client.app.state.database.session_factory() as db:
        target = db.get(User, target_id)
        assert target is not None
        assert target.role == UserRole.TRUSTED_CONTRIBUTOR
        active_sessions = db.scalar(
            select(func.count())
            .select_from(UserSession)
            .where(UserSession.user_id == target_id, UserSession.revoked_at.is_(None))
        )
        assert active_sessions == 0
        record = db.get(RoleChangeRequest, request_id)
        assert record is not None
        assert record.status == RoleChangeRequestStatus.APPROVED
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "admin.role_change.approved",
                AuditLog.target_id == request_id,
            )
        )
        assert audit is not None
        assert audit.details["target_user_id"] == target_id
        assert "reauth_token" not in audit.details
        assert "password" not in audit.details


def test_role_change_rejection_and_optimistic_conflict_do_not_consume_grant(client):
    _, _, target_id = _register_and_login(client, "reject_target")
    requester_headers, _, requester_secret = _privileged_session(
        client, suffix="reject_requester", role=UserRole.ADMIN
    )
    reviewer_headers, reviewer_id, reviewer_secret = _privileged_session(
        client, suffix="reject_reviewer", role=UserRole.ADMIN
    )

    create_token = _reauthenticate(client, requester_headers, requester_secret)
    created = client.post(
        f"/api/v1/admin/users/{target_id}/role-change-requests",
        headers={**requester_headers, "Idempotency-Key": "n2-role-reject-create-01"},
        json={
            "expected_role": "user",
            "requested_role": "trusted_contributor",
            "reason_code": "role_alignment",
            "reauth_token": create_token,
        },
    )
    assert created.status_code == 201
    request_id = created.json()["request"]["id"]

    with client.app.state.database.session_factory() as db:
        target = db.get(User, target_id)
        assert target is not None
        target.role = UserRole.MODERATOR
        db.commit()

    reviewer_token = _reauthenticate(client, reviewer_headers, reviewer_secret)
    conflict = client.post(
        f"/api/v1/admin/role-change-requests/{request_id}/approve",
        headers={**reviewer_headers, "Idempotency-Key": "n2-role-conflict-0001"},
        json={
            "expected_status": "pending",
            "reason_code": "verified",
            "reauth_token": reviewer_token,
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "admin.role_change_conflict"

    rejected = client.post(
        f"/api/v1/admin/role-change-requests/{request_id}/reject",
        headers={**reviewer_headers, "Idempotency-Key": "n2-role-reject-0001"},
        json={
            "expected_status": "pending",
            "reason_code": "policy_conflict",
            "reauth_token": reviewer_token,
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["request"]["status"] == "rejected"
    assert rejected.json()["request"]["reviewed_by"] == reviewer_id
    assert rejected.json()["revoked_session_count"] == 0

    second_review = client.post(
        f"/api/v1/admin/role-change-requests/{request_id}/reject",
        headers={**reviewer_headers, "Idempotency-Key": "n2-role-reject-second-01"},
        json={
            "expected_status": "pending",
            "reason_code": "policy_conflict",
            "reauth_token": "reauth_synthetic_unused_token",
        },
    )
    assert second_review.status_code == 409
    assert second_review.json()["code"] == "admin.role_change_review_conflict"
