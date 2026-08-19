from __future__ import annotations

import pyotp
from sqlalchemy import func, select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.reauthentication_grant import ReauthenticationGrant
from password_detective.db.models.user import User, UserRole, UserStatus
from password_detective.db.models.user_session import UserSession

PASSWORD = "SyntheticAdminActionsPass123!"


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], dict[str, str], str]:
    registration = {
        "username": f"actions_{suffix}",
        "email": f"actions-{suffix}@synthetic.example.com",
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
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return registration, headers, user_id


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
    headers = {"Authorization": f"Bearer {authenticated.json()['access_token']}"}
    return headers, user_id, secret


def _reauthenticate(client, headers: dict[str, str], secret: str) -> str:
    response = client.post(
        "/api/v1/admin/auth/reauthenticate",
        headers=headers,
        json={
            "current_password": PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["purpose"] == "admin_user_governance"
    return response.json()["reauth_token"]


def test_admin_user_governance_reauthentication_is_admin_only(client):
    admin_headers, _, admin_secret = _privileged_session(
        client,
        suffix="reauth_admin",
        role=UserRole.ADMIN,
    )
    moderator_headers, _, moderator_secret = _privileged_session(
        client,
        suffix="reauth_moderator",
        role=UserRole.MODERATOR,
    )

    forbidden = client.post(
        "/api/v1/admin/auth/reauthenticate",
        headers=moderator_headers,
        json={
            "current_password": PASSWORD,
            "totp_code": pyotp.TOTP(moderator_secret).now(),
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "auth.forbidden"

    wrong_password = client.post(
        "/api/v1/admin/auth/reauthenticate",
        headers=admin_headers,
        json={
            "current_password": "SyntheticWrongPass123!",
            "totp_code": pyotp.TOTP(admin_secret).now(),
        },
    )
    assert wrong_password.status_code == 400
    assert wrong_password.json()["code"] == "auth.invalid_current_password"

    token = _reauthenticate(client, admin_headers, admin_secret)
    assert token.startswith("reauth_")


def test_admin_can_edit_non_privileged_user_profile_with_idempotent_audit(client):
    _, _, target_id = _register_and_login(client, "profile_target")
    admin_headers, admin_id, admin_secret = _privileged_session(
        client,
        suffix="profile_admin",
        role=UserRole.ADMIN,
    )
    detail = client.get(f"/api/v1/admin/users/{target_id}", headers=admin_headers)
    assert detail.status_code == 200
    reauth_token = _reauthenticate(client, admin_headers, admin_secret)
    payload = {
        "expected_updated_at": detail.json()["updated_at"],
        "email": "profile-corrected@synthetic.example.com",
        "email_verified": True,
        "reason_code": "profile_correction",
        "reauth_token": reauth_token,
    }
    headers = {**admin_headers, "Idempotency-Key": "n2-profile-update-0001"}
    updated = client.patch(
        f"/api/v1/admin/users/{target_id}",
        headers=headers,
        json=payload,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["user_id"] == target_id
    assert body["email_verified"] is True
    assert "profile-corrected@" not in updated.text

    replay = client.patch(
        f"/api/v1/admin/users/{target_id}",
        headers=headers,
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json() == body

    self_detail = client.get(f"/api/v1/admin/users/{admin_id}", headers=admin_headers)
    assert self_detail.status_code == 200
    self_reauth = _reauthenticate(client, admin_headers, admin_secret)
    forbidden = client.patch(
        f"/api/v1/admin/users/{admin_id}",
        headers={**admin_headers, "Idempotency-Key": "n2-profile-self-0001"},
        json={
            "expected_updated_at": self_detail.json()["updated_at"],
            "email_verified": True,
            "reason_code": "compliance_review",
            "reauth_token": self_reauth,
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "admin.user_self_governance_forbidden"

    with client.app.state.database.session_factory() as db:
        target = db.get(User, target_id)
        assert target is not None
        assert target.email == "profile-corrected@synthetic.example.com"
        assert target.email_verified
        audits = db.scalars(
            select(AuditLog).where(
                AuditLog.action == "admin.user.profile_updated",
                AuditLog.target_id == target_id,
            )
        ).all()
        assert len(audits) == 1
        assert audits[0].details["changed_fields"] == ["email", "email_verified"]
        assert "profile-corrected" not in str(audits[0].details)


def test_admin_can_disable_and_restore_user_with_idempotent_audit(client):
    _, target_headers, target_id = _register_and_login(client, "status_target")
    _, _, replay_target_id = _register_and_login(client, "status_replay_target")
    admin_headers, _, admin_secret = _privileged_session(
        client,
        suffix="status_admin",
        role=UserRole.ADMIN,
    )
    reauth_token = _reauthenticate(client, admin_headers, admin_secret)
    payload = {
        "expected_status": "active",
        "status": "disabled",
        "reason_code": "security_risk",
        "reauth_token": reauth_token,
    }

    missing_key = client.patch(
        f"/api/v1/admin/users/{target_id}/status",
        headers=admin_headers,
        json=payload,
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["code"] == "request.invalid_idempotency_key"

    action_headers = {**admin_headers, "Idempotency-Key": "n2-status-disable-0001"}
    disabled = client.patch(
        f"/api/v1/admin/users/{target_id}/status",
        headers=action_headers,
        json=payload,
    )
    assert disabled.status_code == 200
    disabled_body = disabled.json()
    assert disabled_body["previous_status"] == "active"
    assert disabled_body["current_status"] == "disabled"
    assert disabled_body["revoked_session_count"] >= 1

    replay = client.patch(
        f"/api/v1/admin/users/{target_id}/status",
        headers=action_headers,
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json() == disabled_body

    consumed_replay = client.patch(
        f"/api/v1/admin/users/{replay_target_id}/status",
        headers={**admin_headers, "Idempotency-Key": "n2-status-disable-0002"},
        json=payload,
    )
    assert consumed_replay.status_code == 401
    assert consumed_replay.json()["code"] == "auth.invalid_reauthentication_token"

    with client.app.state.database.session_factory() as db:
        target = db.get(User, target_id)
        assert target is not None
        assert target.status == UserStatus.DISABLED
        active_sessions = db.scalar(
            select(func.count())
            .select_from(UserSession)
            .where(
                UserSession.user_id == target_id,
                UserSession.revoked_at.is_(None),
            )
        )
        assert active_sessions == 0
        audit_logs = db.scalars(
            select(AuditLog).where(
                AuditLog.action == "admin.user.status_changed",
                AuditLog.target_id == target_id,
            )
        ).all()
        assert len(audit_logs) == 1
        assert audit_logs[0].details == {
            "previous_status": "active",
            "current_status": "disabled",
            "reason_code": "security_risk",
            "revoked_session_count": disabled_body["revoked_session_count"],
        }
        assert reauth_token not in str(audit_logs[0].details)
        grant = db.scalar(
            select(ReauthenticationGrant).where(
                ReauthenticationGrant.user_id == audit_logs[0].actor_id,
                ReauthenticationGrant.consumed_at.is_not(None),
            )
        )
        assert grant is not None

    target_access = client.get("/api/v1/me/profile", headers=target_headers)
    assert target_access.status_code == 403
    assert target_access.json()["code"] == "auth.account_unavailable"

    restore_token = _reauthenticate(client, admin_headers, admin_secret)
    restored = client.patch(
        f"/api/v1/admin/users/{target_id}/status",
        headers={**admin_headers, "Idempotency-Key": "n2-status-restore-0001"},
        json={
            "expected_status": "disabled",
            "status": "active",
            "reason_code": "appeal_approved",
            "reauth_token": restore_token,
        },
    )
    assert restored.status_code == 200
    assert restored.json()["current_status"] == "active"
    assert restored.json()["revoked_session_count"] == 0


def test_admin_user_status_conflict_and_object_guards_do_not_consume_grant(client):
    _, _, target_id = _register_and_login(client, "guard_target")
    admin_headers, admin_id, admin_secret = _privileged_session(
        client,
        suffix="guard_admin",
        role=UserRole.ADMIN,
    )
    reauth_token = _reauthenticate(client, admin_headers, admin_secret)
    base_payload = {
        "expected_status": "disabled",
        "status": "active",
        "reason_code": "appeal_approved",
        "reauth_token": reauth_token,
    }

    self_action = client.patch(
        f"/api/v1/admin/users/{admin_id}/status",
        headers={**admin_headers, "Idempotency-Key": "n2-status-self-guard-01"},
        json=base_payload,
    )
    assert self_action.status_code == 403
    assert self_action.json()["code"] == "admin.user_self_governance_forbidden"

    conflict = client.patch(
        f"/api/v1/admin/users/{target_id}/status",
        headers={**admin_headers, "Idempotency-Key": "n2-status-conflict-0001"},
        json=base_payload,
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "admin.user_status_conflict"

    success = client.patch(
        f"/api/v1/admin/users/{target_id}/status",
        headers={**admin_headers, "Idempotency-Key": "n2-status-after-guard-01"},
        json={
            **base_payload,
            "expected_status": "active",
            "status": "disabled",
            "reason_code": "manual_review",
        },
    )
    assert success.status_code == 200


def test_admin_can_revoke_user_sessions_with_concurrency_guard(client):
    _, target_headers, target_id = _register_and_login(client, "sessions_target")
    admin_headers, _, admin_secret = _privileged_session(
        client,
        suffix="sessions_admin",
        role=UserRole.ADMIN,
    )
    detail = client.get(f"/api/v1/admin/users/{target_id}", headers=admin_headers)
    assert detail.status_code == 200
    active_session_count = detail.json()["active_session_count"]
    assert active_session_count >= 1

    conflict_token = _reauthenticate(client, admin_headers, admin_secret)
    conflict = client.post(
        f"/api/v1/admin/users/{target_id}/sessions/revoke",
        headers={**admin_headers, "Idempotency-Key": "n2-sessions-conflict-01"},
        json={
            "expected_active_session_count": active_session_count + 1,
            "reason_code": "incident_response",
            "reauth_token": conflict_token,
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "admin.user_session_conflict"

    revoked = client.post(
        f"/api/v1/admin/users/{target_id}/sessions/revoke",
        headers={**admin_headers, "Idempotency-Key": "n2-sessions-revoke-0001"},
        json={
            "expected_active_session_count": active_session_count,
            "reason_code": "incident_response",
            "reauth_token": conflict_token,
        },
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_session_count"] == active_session_count
    target_access = client.get("/api/v1/me/profile", headers=target_headers)
    assert target_access.status_code == 401
    assert target_access.json()["code"] == "auth.session_revoked"

    with client.app.state.database.session_factory() as db:
        active_sessions = db.scalar(
            select(func.count())
            .select_from(UserSession)
            .where(
                UserSession.user_id == target_id,
                UserSession.revoked_at.is_(None),
            )
        )
        assert active_sessions == 0
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "admin.user.sessions_revoked",
                AuditLog.target_id == target_id,
            )
        )
        assert audit is not None
        assert audit.details["reason_code"] == "incident_response"
        assert audit.details["revoked_session_count"] == active_session_count
