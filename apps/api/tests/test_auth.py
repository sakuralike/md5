from __future__ import annotations

import pyotp
from sqlalchemy import select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.user import User
from password_detective.db.models.user_session import UserSession

REGISTER_PAYLOAD = {
    "username": "detective_one",
    "email": "detective@example.com",
    "password": "SyntheticPass123!",
}


def register(client, payload=REGISTER_PAYLOAD):
    return client.post("/api/v1/auth/register", json=payload)


def login(
    client,
    login_name=REGISTER_PAYLOAD["username"],
    password=REGISTER_PAYLOAD["password"],
    **extra,
):
    return client.post(
        "/api/v1/auth/login",
        json={"login": login_name, "password": password, **extra},
    )


def auth_headers(tokens, *, idempotency_key=None):
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def test_register_hashes_password_and_rejects_duplicate(client):
    response = register(client)
    assert response.status_code == 201
    assert response.json()["username"] == "detective_one"
    assert "password" not in response.json()

    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == "detective_one"))
        assert user is not None
        assert user.account_password_hash != REGISTER_PAYLOAD["password"]
        assert user.account_password_hash.startswith("$argon2id$")

    duplicate = register(client)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "auth.account_conflict"


def test_login_refresh_rotation_and_reuse_detection(client):
    assert register(client).status_code == 201
    login_response = login(client)
    assert login_response.status_code == 200
    first = login_response.json()
    assert first["token_type"] == "bearer"

    with client.app.state.database.session_factory() as db:
        session = db.scalar(select(UserSession))
        assert session is not None
        assert session.refresh_token_hash != first["refresh_token"]
        family_id = session.family_id

    refresh_response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert refresh_response.status_code == 200
    second = refresh_response.json()
    assert second["refresh_token"] != first["refresh_token"]

    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert reuse.status_code == 401
    assert reuse.json()["code"] == "auth.refresh_token_reused"

    profile = client.get(
        "/api/v1/me/profile", headers={"Authorization": f"Bearer {second['access_token']}"}
    )
    assert profile.status_code == 401
    assert profile.json()["code"] == "auth.session_revoked"

    with client.app.state.database.session_factory() as db:
        active = db.scalars(
            select(UserSession).where(
                UserSession.family_id == family_id, UserSession.revoked_at.is_(None)
            )
        ).all()
        assert active == []


def test_profile_update_is_idempotent_and_conflict_safe(client):
    assert register(client).status_code == 201
    tokens = login(client).json()
    headers = auth_headers(tokens, idempotency_key="profile-update-key-001")
    response = client.patch(
        "/api/v1/me/profile", json={"username": "detective_updated"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["username"] == "detective_updated"

    replay = client.patch(
        "/api/v1/me/profile", json={"username": "detective_updated"}, headers=headers
    )
    assert replay.status_code == 200
    assert replay.json()["username"] == "detective_updated"

    conflict = client.patch(
        "/api/v1/me/profile",
        json={"username": "another_name"},
        headers={**auth_headers(tokens), "Idempotency-Key": "profile-update-key-001"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "request.idempotency_conflict"

    with client.app.state.database.session_factory() as db:
        actions = db.scalars(
            select(AuditLog).where(AuditLog.action == "auth.profile.updated")
        ).all()
        assert len(actions) == 1


def test_password_change_revokes_other_sessions_and_rejects_reuse(client):
    assert register(client).status_code == 201
    current = login(client).json()
    other = login(client).json()
    response = client.post(
        "/api/v1/me/security/password/change",
        json={
            "current_password": REGISTER_PAYLOAD["password"],
            "new_password": "SyntheticNext456!",
        },
        headers=auth_headers(current, idempotency_key="password-change-key-001"),
    )
    assert response.status_code == 200

    current_profile = client.get("/api/v1/me/profile", headers=auth_headers(current))
    other_profile = client.get("/api/v1/me/profile", headers=auth_headers(other))
    assert current_profile.status_code == 200
    assert other_profile.status_code == 401
    assert other_profile.json()["code"] == "auth.session_revoked"

    old_login = login(client)
    assert old_login.status_code == 401
    new_login = login(client, password="SyntheticNext456!")
    assert new_login.status_code == 200

    with client.app.state.database.session_factory() as db:
        actions = db.scalars(
            select(AuditLog).where(AuditLog.action == "auth.password.changed")
        ).all()
        assert len(actions) == 1


def test_user_totp_setup_confirm_login_and_disable(client):
    assert register(client).status_code == 201
    tokens = login(client).json()
    headers = auth_headers(tokens)

    setup = client.post("/api/v1/me/security/totp/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    code = pyotp.TOTP(secret).now()
    confirm_headers = auth_headers(tokens, idempotency_key="totp-confirm-key-001")
    confirm = client.post(
        "/api/v1/me/security/totp/confirm", json={"code": code}, headers=confirm_headers
    )
    assert confirm.status_code == 200
    replay = client.post(
        "/api/v1/me/security/totp/confirm", json={"code": code}, headers=confirm_headers
    )
    assert replay.status_code == 200

    profile = client.get("/api/v1/me/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["totp_enabled"] is True

    missing_code = login(client)
    assert missing_code.status_code == 401
    assert missing_code.json()["code"] == "auth.totp_required"
    valid_login = login(client, totp_code=pyotp.TOTP(secret).now())
    assert valid_login.status_code == 200
    assert valid_login.json()["mfa_verified"] is True

    password_without_totp = client.post(
        "/api/v1/me/security/password/change",
        json={
            "current_password": REGISTER_PAYLOAD["password"],
            "new_password": "SyntheticNext456!",
        },
        headers=auth_headers(tokens, idempotency_key="password-without-totp-001"),
    )
    assert password_without_totp.status_code == 401
    assert password_without_totp.json()["code"] == "auth.totp_required"

    disable = client.request(
        "DELETE",
        "/api/v1/me/security/totp",
        json={"code": pyotp.TOTP(secret).now()},
        headers=auth_headers(tokens, idempotency_key="totp-disable-key-001"),
    )
    assert disable.status_code == 200
    assert login(client).status_code == 200


def test_invalid_login_does_not_reveal_account_details(client):
    assert register(client).status_code == 201
    wrong = client.post(
        "/api/v1/auth/login",
        json={"login": "detective_one", "password": "WrongSynthetic123!"},
    )
    missing = client.post(
        "/api/v1/auth/login",
        json={"login": "missing_user", "password": "WrongSynthetic123!"},
    )
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["message"] == missing.json()["message"]


def test_profile_sessions_and_logout(client):
    assert register(client).status_code == 201
    tokens = login(client).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    profile = client.get("/api/v1/me/profile", headers=headers)
    sessions = client.get("/api/v1/me/security/sessions", headers=headers)
    assert profile.status_code == 200
    assert sessions.status_code == 200
    assert len(sessions.json()) == 1
    assert sessions.json()[0]["current"] is True

    logout = client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 200
    denied = client.get("/api/v1/me/profile", headers=headers)
    assert denied.status_code == 401


def test_validation_error_uses_standard_shape(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "x", "email": "bad", "password": "short"},
    )
    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "request.validation_failed"
    assert body["request_id"].startswith("req_")
    assert "errors" in body["details"]


def test_regular_user_cannot_access_admin_api(client):
    assert register(client).status_code == 201
    tokens = login(client).json()
    response = client.get(
        "/api/v1/admin/access-check",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "auth.forbidden"
