from __future__ import annotations

import pyotp
from sqlalchemy import select

from password_detective.db.models.user import User, UserRole

PASSWORD = "SyntheticSearchAdminPass123!"


def admin_headers(client) -> dict[str, str]:
    registration = {
        "username": "search_admin",
        "email": "search-admin@synthetic.example.com",
        "password": PASSWORD,
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()

    initial_login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": PASSWORD},
    )
    assert initial_login.status_code == 200, initial_login.text
    initial_headers = {"Authorization": f"Bearer {initial_login.json()['access_token']}"}
    setup = client.post("/api/v1/admin/totp/setup", headers=initial_headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    confirmed = client.post(
        "/api/v1/admin/totp/confirm",
        headers=initial_headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert confirmed.status_code == 200, confirmed.text
    authenticated = client.post(
        "/api/v1/auth/login",
        json={
            "login": registration["username"],
            "password": PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert authenticated.status_code == 200, authenticated.text
    return {"Authorization": f"Bearer {authenticated.json()['access_token']}"}


def test_search_health_is_admin_only_and_contains_no_query_history(client):
    assert client.get("/api/v1/admin/community/search/health").status_code == 401

    response = client.get(
        "/api/v1/admin/community/search/health",
        headers=admin_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) >= {
        "generated_at",
        "provider",
        "pending_count",
        "failed_count",
        "last_rebuild",
    }
    assert "items" not in body
    assert "queries" not in body
    assert "documents" not in body
    assert "query" not in str(body).lower()
    assert "content" not in str(body).lower()
