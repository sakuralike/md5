from __future__ import annotations

import os
from uuid import uuid4

import fakeredis
import pyotp
import pytest
from redis import Redis
from sqlalchemy import func, select

from password_detective.core.errors import AppError
from password_detective.core.notifications import MemoryNotificationGateway
from password_detective.core.rate_limit import RedisRateLimiter
from password_detective.db.models.account_action_token import AccountActionToken, AccountTokenKind
from password_detective.db.models.idempotency_record import IdempotencyRecord
from password_detective.db.models.user import User, UserRole

REGISTER_PAYLOAD = {
    "username": "gate_detective",
    "email": "gate@example.com",
    "password": "SyntheticPass123!",
}


def _register(client):
    return client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)


def _login(client, password: str = REGISTER_PAYLOAD["password"], totp_code: str | None = None):
    payload = {"login": REGISTER_PAYLOAD["username"], "password": password}
    if totp_code is not None:
        payload["totp_code"] = totp_code
    return client.post("/api/v1/auth/login", json=payload)


def test_redis_rate_limit_is_shared_between_instances():
    server = fakeredis.FakeServer()
    first = RedisRateLimiter(
        fakeredis.FakeRedis(server=server, decode_responses=True), namespace="shared-test"
    )
    second = RedisRateLimiter(
        fakeredis.FakeRedis(server=server, decode_responses=True), namespace="shared-test"
    )

    first.check("login:203.0.113.0/24", limit=2, window_seconds=60)
    second.check("login:203.0.113.0/24", limit=2, window_seconds=60)
    with pytest.raises(AppError) as exc_info:
        first.check("login:203.0.113.0/24", limit=2, window_seconds=60)

    assert exc_info.value.code == "rate_limit.exceeded"
    assert exc_info.value.details["retry_after_seconds"] >= 1


def test_login_endpoint_uses_redis_rate_limit(client):
    for _ in range(10):
        response = client.post(
            "/api/v1/auth/login",
            json={"login": "missing_account", "password": "SyntheticWrong123!"},
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/v1/auth/login",
        json={"login": "missing_account", "password": "SyntheticWrong123!"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "rate_limit.exceeded"
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.json()["details"]["retry_after_seconds"] >= 1


def test_browser_refresh_token_uses_httponly_cookie(client):
    assert _register(client).status_code == 201
    login = client.post(
        "/api/v1/web/auth/login",
        json={
            "login": REGISTER_PAYLOAD["username"],
            "password": REGISTER_PAYLOAD["password"],
        },
        headers={"Origin": "http://testserver"},
    )
    assert login.status_code == 200
    assert "refresh_token" not in login.json()
    cookie = login.headers["set-cookie"]
    assert "pd_web_refresh=" in cookie
    assert "HttpOnly" in cookie
    assert "Path=/api/v1/web/auth" in cookie

    refreshed = client.post(
        "/api/v1/web/auth/refresh",
        headers={"Origin": "http://testserver"},
    )
    assert refreshed.status_code == 200
    assert "refresh_token" not in refreshed.json()
    assert refreshed.json()["access_token"] != login.json()["access_token"]

    rejected_origin = client.post(
        "/api/v1/web/auth/refresh",
        headers={"Origin": "https://untrusted.example"},
    )
    assert rejected_origin.status_code == 403
    assert rejected_origin.json()["code"] == "request.invalid_origin"

    logged_out = client.post(
        "/api/v1/web/auth/logout",
        headers={"Origin": "http://testserver"},
    )
    assert logged_out.status_code == 200
    assert "pd_web_refresh=" in logged_out.headers["set-cookie"]
    assert "Max-Age=0" in logged_out.headers["set-cookie"]

    rejected_after_logout = client.post(
        "/api/v1/web/auth/refresh",
        headers={"Origin": "http://testserver"},
    )
    assert rejected_after_logout.status_code == 401


def test_regular_user_cannot_create_admin_browser_session(client):
    assert _register(client).status_code == 201
    denied = client.post(
        "/api/v1/admin/auth/login",
        json={
            "login": REGISTER_PAYLOAD["username"],
            "password": REGISTER_PAYLOAD["password"],
        },
        headers={"Origin": "http://testserver"},
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "auth.forbidden"
    assert "pd_admin_refresh=" not in denied.headers.get("set-cookie", "")


def test_email_verification_and_password_reset_flow(
    client, notifications: MemoryNotificationGateway
):
    registered = _register(client)
    assert registered.status_code == 201
    assert registered.json()["email_verified"] is False

    verification_token = notifications.latest_token(
        kind=AccountTokenKind.EMAIL_VERIFICATION.value,
        recipient=REGISTER_PAYLOAD["email"],
    )
    verified = client.post("/api/v1/auth/email/verify", json={"token": verification_token})
    assert verified.status_code == 200
    reused = client.post("/api/v1/auth/email/verify", json={"token": verification_token})
    assert reused.status_code == 400

    login = _login(client)
    assert login.status_code == 200
    access_token = login.json()["access_token"]
    profile = client.get("/api/v1/me/profile", headers={"Authorization": f"Bearer {access_token}"})
    assert profile.json()["email_verified"] is True

    key = "forgot-password-000001"
    forgot = client.post(
        "/api/v1/auth/password/forgot",
        json={"email": REGISTER_PAYLOAD["email"]},
        headers={"Idempotency-Key": key},
    )
    repeated = client.post(
        "/api/v1/auth/password/forgot",
        json={"email": REGISTER_PAYLOAD["email"]},
        headers={"Idempotency-Key": key},
    )
    assert forgot.status_code == repeated.status_code == 200
    assert forgot.json() == repeated.json()

    reset_messages = [
        message
        for message in notifications.messages
        if message.kind == AccountTokenKind.PASSWORD_RESET.value
    ]
    assert len(reset_messages) == 1
    reset = client.post(
        "/api/v1/auth/password/reset",
        json={"token": reset_messages[0].token, "new_password": "NewSyntheticPass456!"},
    )
    assert reset.status_code == 200

    revoked_profile = client.get(
        "/api/v1/me/profile", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert revoked_profile.status_code == 401
    assert _login(client).status_code == 401
    assert _login(client, password="NewSyntheticPass456!").status_code == 200

    with client.app.state.database.session_factory() as db:
        idempotency_count = db.scalar(select(func.count()).select_from(IdempotencyRecord))
        reset_token_count = db.scalar(
            select(func.count())
            .select_from(AccountActionToken)
            .where(AccountActionToken.kind == AccountTokenKind.PASSWORD_RESET)
        )
        assert idempotency_count == 1
        assert reset_token_count == 1


def test_idempotency_key_conflict_is_rejected(client):
    key = "forgot-password-000002"
    first = client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "first@example.com"},
        headers={"Idempotency-Key": key},
    )
    conflict = client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "second@example.com"},
        headers={"Idempotency-Key": key},
    )
    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "request.idempotency_conflict"


def test_admin_totp_is_optional_until_enabled_and_enforced_afterward(client):
    assert _register(client).status_code == 201
    initial_login = _login(client)
    assert initial_login.status_code == 200
    initial_token = initial_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {initial_token}"}

    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == REGISTER_PAYLOAD["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()

    before_setup = client.get("/api/v1/admin/access-check", headers=headers)
    assert before_setup.status_code == 200
    assert before_setup.json()["mfa"] == "not_verified"

    setup = client.post("/api/v1/admin/totp/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    code = pyotp.TOTP(secret).now()
    confirmed = client.post("/api/v1/admin/totp/confirm", json={"code": code}, headers=headers)
    assert confirmed.status_code == 200

    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == REGISTER_PAYLOAD["username"]))
        assert user is not None
        assert user.totp_secret_ciphertext is not None
        assert secret not in user.totp_secret_ciphertext

    stale_access = client.get("/api/v1/admin/access-check", headers=headers)
    assert stale_access.status_code == 403
    assert stale_access.json()["code"] == "auth.totp_required"
    assert _login(client).json()["code"] == "auth.totp_required"

    authenticated = _login(client, totp_code=pyotp.TOTP(secret).now())
    assert authenticated.status_code == 200
    assert authenticated.json()["mfa_verified"] is True
    admin_headers = {"Authorization": f"Bearer {authenticated.json()['access_token']}"}
    allowed = client.get("/api/v1/admin/access-check", headers=admin_headers)
    assert allowed.status_code == 200
    assert allowed.json()["mfa"] == "verified"

    refreshed = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": authenticated.json()["refresh_token"]},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["mfa_verified"] is True

    browser_login = client.post(
        "/api/v1/admin/auth/login",
        json={
            "login": REGISTER_PAYLOAD["username"],
            "password": REGISTER_PAYLOAD["password"],
            "totp_code": pyotp.TOTP(secret).now(),
        },
        headers={"Origin": "http://testserver"},
    )
    assert browser_login.status_code == 200
    assert "refresh_token" not in browser_login.json()
    assert "pd_admin_refresh=" in browser_login.headers["set-cookie"]

    browser_refresh = client.post(
        "/api/v1/admin/auth/refresh",
        headers={"Origin": "http://testserver"},
    )
    assert browser_refresh.status_code == 200
    assert browser_refresh.json()["mfa_verified"] is True

    browser_logout = client.post(
        "/api/v1/admin/auth/logout",
        headers={"Origin": "http://testserver"},
    )
    assert browser_logout.status_code == 200
    assert "Max-Age=0" in browser_logout.headers["set-cookie"]
    assert (
        client.post(
            "/api/v1/admin/auth/refresh",
            headers={"Origin": "http://testserver"},
        ).status_code
        == 401
    )


@pytest.mark.skipif(
    os.getenv("RUN_REDIS_INTEGRATION") != "1",
    reason="需要显式启用真实 Redis 集成测试",
)
def test_real_redis_distributed_rate_limit():
    url = os.getenv("REDIS_URL", "redis://localhost:6379/15")
    namespace = f"integration:{uuid4()}"
    first_client = Redis.from_url(url, decode_responses=True)
    second_client = Redis.from_url(url, decode_responses=True)
    first = RedisRateLimiter(first_client, namespace=namespace)
    second = RedisRateLimiter(second_client, namespace=namespace)
    try:
        first.check("shared", limit=1, window_seconds=30)
        with pytest.raises(AppError) as exc_info:
            second.check("shared", limit=1, window_seconds=30)
        assert exc_info.value.code == "rate_limit.exceeded"
    finally:
        keys = list(first_client.scan_iter(f"{namespace}:*"))
        if keys:
            first_client.delete(*keys)
        first.close()
        second.close()
