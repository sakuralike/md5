from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

EXPECTED_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "cache-control": "no-store",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
}


@pytest.mark.parametrize(
    ("method", "path", "expected_status"),
    [
        ("GET", "/api/v1/health/live", 200),
        ("GET", "/api/v1/admin/users", 401),
        ("POST", "/api/v1/health/live", 405),
    ],
)
def test_api_responses_apply_security_headers(
    client: TestClient,
    method: str,
    path: str,
    expected_status: int,
) -> None:
    response = client.request(method, path)

    assert response.status_code == expected_status
    for name, value in EXPECTED_SECURITY_HEADERS.items():
        assert response.headers[name] == value
    assert response.headers["x-request-id"].startswith("req_")


def test_cors_preflight_allows_configured_origin_and_rejects_untrusted_origin(
    client: TestClient,
) -> None:
    preflight_headers = {
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization,X-Request-ID",
    }

    allowed = client.options(
        "/api/v1/me/profile",
        headers={"Origin": "http://testserver", **preflight_headers},
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://testserver"

    rejected = client.options(
        "/api/v1/me/profile",
        headers={"Origin": "https://untrusted.example", **preflight_headers},
    )
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers


def test_json_body_limit_rejects_content_length_and_chunked_bypass(client: TestClient) -> None:
    oversized = b'{"probe":"' + (b"a" * 1_048_576) + b'"}'

    content_length_response = client.post(
        "/api/v1/auth/login",
        content=oversized,
        headers={"Content-Type": "application/json"},
    )
    assert content_length_response.status_code == 413
    assert content_length_response.json()["code"] == "request.body_too_large"
    assert content_length_response.json()["details"] == {"max_bytes": 1_048_576}
    assert content_length_response.headers["x-request-id"].startswith("req_")

    def body_chunks() -> Iterator[bytes]:
        yield b'{"probe":"'
        yield b"b" * 1_048_576
        yield b'"}'

    chunked_response = client.post(
        "/api/v1/auth/login",
        content=body_chunks(),
        headers={"Content-Type": "application/json"},
    )
    assert chunked_response.status_code == 413
    assert chunked_response.json()["code"] == "request.body_too_large"


def test_negative_probes_do_not_reflect_xss_or_credentials(client: TestClient) -> None:
    xss_canary = "<script>wp4_probe()</script>"
    xss_response = client.get("/api/v1/health/live", params={"probe": xss_canary})
    assert xss_response.status_code == 200
    assert xss_canary not in xss_response.text

    password_canary = "Synthetic-WP4-Password-Canary!"
    token_canary = "wp4.synthetic.token.canary"
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "login": f"missing-{token_canary}",
            "password": password_canary,
        },
    )
    assert login_response.status_code == 401
    assert password_canary not in login_response.text
    assert token_canary not in login_response.text


def test_anonymous_principal_cannot_cross_user_or_admin_boundaries(client: TestClient) -> None:
    probes = (
        ("GET", "/api/v1/me/profile"),
        ("POST", "/api/v1/me/privacy/exports"),
        ("GET", "/api/v1/admin/users"),
        ("GET", "/api/v1/admin/audit-logs"),
    )
    for method, path in probes:
        response = client.request(method, path)
        assert response.status_code == 401
        assert response.json()["code"] == "auth.authentication_required"


def test_authenticated_object_boundaries_and_browser_cookie_csrf(
    client: TestClient,
) -> None:
    suffix = uuid4().hex[:10]
    users = [
        {
            "username": f"wp4_owner_{suffix}",
            "email": f"wp4-owner-{suffix}@example.com",
            "password": "SyntheticDastPass123!",
        },
        {
            "username": f"wp4_other_{suffix}",
            "email": f"wp4-other-{suffix}@example.com",
            "password": "SyntheticDastPass123!",
        },
    ]
    tokens: list[str] = []
    for user in users:
        assert client.post("/api/v1/auth/register", json=user).status_code == 201
        login = client.post(
            "/api/v1/auth/login",
            json={"login": user["username"], "password": user["password"]},
        )
        assert login.status_code == 200
        tokens.append(login.json()["access_token"])

    owner_headers = {"Authorization": f"Bearer {tokens[0]}"}
    other_headers = {"Authorization": f"Bearer {tokens[1]}"}
    export = client.post(
        "/api/v1/me/privacy/exports",
        headers={**owner_headers, "Idempotency-Key": f"wp4-export-{suffix}"},
    )
    assert export.status_code == 202
    export_id = export.json()["id"]

    foreign_export = client.get(
        f"/api/v1/me/privacy/exports/{export_id}", headers=other_headers
    )
    assert foreign_export.status_code == 404
    assert foreign_export.json()["code"] == "privacy.export_not_found"

    owner_sessions = client.get("/api/v1/me/security/sessions", headers=owner_headers)
    assert owner_sessions.status_code == 200
    family_id = owner_sessions.json()[0]["id"]
    foreign_revoke = client.delete(
        f"/api/v1/me/security/sessions/{family_id}", headers=other_headers
    )
    assert foreign_revoke.status_code == 404
    assert foreign_revoke.json()["code"] == "auth.session_not_found"

    browser_login = client.post(
        "/api/v1/web/auth/login",
        json={"login": users[0]["username"], "password": users[0]["password"]},
        headers={"Origin": "http://testserver"},
    )
    assert browser_login.status_code == 200
    cookie = browser_login.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()
    assert "Path=/api/v1/web/auth" in cookie

    rejected = client.post(
        "/api/v1/web/auth/refresh", headers={"Origin": "https://untrusted.example"}
    )
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "request.invalid_origin"
