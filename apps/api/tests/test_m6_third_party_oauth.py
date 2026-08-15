from __future__ import annotations

import base64
import hashlib
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from password_detective.core.security import hash_opaque_token
from password_detective.core.time import utc_now
from password_detective.db.models.third_party_oauth import OAuthAuthorizationCode


def _admin_headers(client) -> dict[str, str]:
    registration = {
        "username": "oauth_admin",
        "email": "oauth-admin@synthetic.example.com",
        "password": "SyntheticOauthAdmin123!",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    from password_detective.db.models.user import User, UserRole

    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _approved_app(client) -> tuple[str, str, dict[str, str]]:
    admin_headers = _admin_headers(client)
    created = client.post(
        "/api/v1/admin/third-party-apps",
        headers=admin_headers,
        json={
            "name": "Synthetic OAuth Desktop",
            "developer_name": "Synthetic Developer",
            "redirect_uris": ["http://127.0.0.1:49152/callback"],
            "scopes": ["profile:read", "hash:read"],
        },
    )
    assert created.status_code == 201
    app = created.json()
    approved = client.post(
        f"/api/v1/admin/third-party-apps/{app['id']}/approve",
        headers=admin_headers,
    )
    assert approved.status_code == 200
    return app["client_id"], app["redirect_uris"][0], admin_headers


def _login_user(client) -> dict[str, str]:
    registration = {
        "username": "oauth_user",
        "email": "oauth-user@synthetic.example.com",
        "password": "SyntheticOauthUser123!",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


def _authorize(
    client, *, client_id: str, redirect_uri: str, headers: dict[str, str], verifier: str
):
    return client.get(
        "/api/v1/third-party/oauth/authorize",
        headers=headers,
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "scope": "profile:read hash:read",
            "state": "synthetic-state-123456",
        },
        follow_redirects=False,
    )


def test_authorization_code_requires_matching_pkce_and_is_single_use(client) -> None:
    client_id, redirect_uri, _ = _approved_app(client)
    user_headers = _login_user(client)
    verifier = "synthetic-verifier-123456789-abcdefghijklmnopqrstuvwxyz"
    issued = _authorize(
        client,
        client_id=client_id,
        redirect_uri=redirect_uri,
        headers=user_headers,
        verifier=verifier,
    )
    assert issued.status_code == 302
    location = issued.headers["location"]
    query = parse_qs(urlparse(location).query)
    assert query["state"] == ["synthetic-state-123456"]
    code = query["code"][0]

    token = client.post(
        "/api/v1/third-party/oauth/token",
        json={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
    )
    assert token.status_code == 200
    payload = token.json()
    assert payload["token_type"] == "Bearer"
    assert payload["scope"] == "profile:read hash:read"
    assert payload["refresh_token"]

    replay = client.post(
        "/api/v1/third-party/oauth/token",
        json={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
    )
    assert replay.status_code == 400
    assert replay.json()["code"] == "third_party_oauth.invalid_grant"


def test_third_party_access_token_requires_scope_and_refresh_rotation(client) -> None:
    client_id, redirect_uri, _ = _approved_app(client)
    user_headers = _login_user(client)
    verifier = "synthetic-verifier-987654321-abcdefghijklmnopqrstuvwxyz"
    issued = _authorize(
        client,
        client_id=client_id,
        redirect_uri=redirect_uri,
        headers=user_headers,
        verifier=verifier,
    )
    code = parse_qs(urlparse(issued.headers["location"]).query)["code"][0]
    token = client.post(
        "/api/v1/third-party/oauth/token",
        json={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
    )
    assert token.status_code == 200
    access_token = token.json()["access_token"]
    probe = client.get(
        "/api/v1/third-party/oauth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert probe.status_code == 200
    assert probe.json()["client_id"] == client_id
    assert probe.json()["scopes"] == ["profile:read", "hash:read"]

    refreshed = client.post(
        "/api/v1/third-party/oauth/token",
        json={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": token.json()["refresh_token"],
        },
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != token.json()["refresh_token"]

    reused = client.post(
        "/api/v1/third-party/oauth/token",
        json={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": token.json()["refresh_token"],
        },
    )
    assert reused.status_code == 400
    assert reused.json()["code"] == "third_party_oauth.refresh_token_reused"
    family_access = client.get(
        "/api/v1/third-party/oauth/me",
        headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
    )
    assert family_access.status_code == 401


def test_oauth_rejects_unapproved_app_and_non_s256_pkce(client) -> None:
    admin_headers = _admin_headers(client)
    created = client.post(
        "/api/v1/admin/third-party-apps",
        headers=admin_headers,
        json={
            "name": "Synthetic Draft OAuth",
            "developer_name": "Synthetic Developer",
            "redirect_uris": ["http://127.0.0.1:49153/callback"],
            "scopes": ["profile:read"],
        },
    )
    assert created.status_code == 201
    user_headers = _login_user(client)
    response = client.get(
        "/api/v1/third-party/oauth/authorize",
        headers=user_headers,
        params={
            "response_type": "code",
            "client_id": created.json()["client_id"],
            "redirect_uri": created.json()["redirect_uris"][0],
            "code_challenge": _challenge("synthetic-verifier-abcdefghijklmnopqrstuvwxyz"),
            "code_challenge_method": "plain",
            "scope": "profile:read",
            "state": "synthetic-state-123456",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "third_party_oauth.invalid_request"


def test_profile_probe_requires_profile_read_scope(client) -> None:
    admin_headers = _admin_headers(client)
    created = client.post(
        "/api/v1/admin/third-party-apps",
        headers=admin_headers,
        json={
            "name": "Synthetic Hash Only Desktop",
            "developer_name": "Synthetic Developer",
            "redirect_uris": ["http://127.0.0.1:49154/callback"],
            "scopes": ["hash:read"],
        },
    )
    assert created.status_code == 201
    app = created.json()
    assert (
        client.post(
            f"/api/v1/admin/third-party-apps/{app['id']}/approve", headers=admin_headers
        ).status_code
        == 200
    )
    user_headers = _login_user(client)
    verifier = "synthetic-verifier-scope-abcdefghijklmnopqrstuvwxyz"
    issued = client.get(
        "/api/v1/third-party/oauth/authorize",
        headers=user_headers,
        params={
            "response_type": "code",
            "client_id": app["client_id"],
            "redirect_uri": app["redirect_uris"][0],
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "scope": "hash:read",
            "state": "synthetic-state-scope",
        },
        follow_redirects=False,
    )
    code = parse_qs(urlparse(issued.headers["location"]).query)["code"][0]
    token = client.post(
        "/api/v1/third-party/oauth/token",
        json={
            "grant_type": "authorization_code",
            "client_id": app["client_id"],
            "code": code,
            "redirect_uri": app["redirect_uris"][0],
            "code_verifier": verifier,
        },
    )
    assert token.status_code == 200
    response = client.get(
        "/api/v1/third-party/oauth/me",
        headers={"Authorization": f"Bearer {token.json()['access_token']}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "third_party_oauth.insufficient_scope"


def test_authorization_code_rejects_wrong_verifier_and_expired_code(client) -> None:
    client_id, redirect_uri, _ = _approved_app(client)
    user_headers = _login_user(client)
    verifier = "synthetic-verifier-expiry-abcdefghijklmnopqrstuvwxyz"
    issued = _authorize(
        client,
        client_id=client_id,
        redirect_uri=redirect_uri,
        headers=user_headers,
        verifier=verifier,
    )
    code = parse_qs(urlparse(issued.headers["location"]).query)["code"][0]
    wrong = client.post(
        "/api/v1/third-party/oauth/token",
        json={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": "wrong-verifier-value-abcdefghijklmnopqrstuvwxyz",
        },
    )
    assert wrong.status_code == 400
    assert wrong.json()["code"] == "third_party_oauth.invalid_grant"

    with client.app.state.database.session_factory() as db:
        row = db.scalar(
            select(OAuthAuthorizationCode).where(
                OAuthAuthorizationCode.code_hash == hash_opaque_token(code)
            )
        )
        assert row is not None
        row.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    expired = client.post(
        "/api/v1/third-party/oauth/token",
        json={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
    )
    assert expired.status_code == 400
    assert expired.json()["code"] == "third_party_oauth.invalid_grant"


def test_suspended_app_invalidates_existing_third_party_access_token(client) -> None:
    client_id, redirect_uri, admin_headers = _approved_app(client)
    user_headers = _login_user(client)
    verifier = "synthetic-verifier-suspend-abcdefghijklmnopqrstuvwxyz"
    issued = _authorize(
        client,
        client_id=client_id,
        redirect_uri=redirect_uri,
        headers=user_headers,
        verifier=verifier,
    )
    code = parse_qs(urlparse(issued.headers["location"]).query)["code"][0]
    token = client.post(
        "/api/v1/third-party/oauth/token",
        json={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
    )
    assert token.status_code == 200
    with client.app.state.database.session_factory() as db:
        from password_detective.db.models.third_party_app import ThirdPartyApp

        app = db.scalar(select(ThirdPartyApp).where(ThirdPartyApp.client_id == client_id))
        assert app is not None
        app_id = app.id
    suspended = client.post(
        f"/api/v1/admin/third-party-apps/{app_id}/suspend",
        headers=admin_headers,
    )
    assert suspended.status_code == 200
    response = client.get(
        "/api/v1/third-party/oauth/me",
        headers={"Authorization": f"Bearer {token.json()['access_token']}"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "third_party_oauth.session_unavailable"


def test_consent_page_lists_and_revokes_authorized_application(client) -> None:
    client_id, redirect_uri, _ = _approved_app(client)
    user_headers = _login_user(client)
    verifier = "synthetic-verifier-consent-abcdefghijklmnopqrstuvwxyz"
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
        "scope": "profile:read hash:read",
        "state": "synthetic-state-consent",
    }

    details = client.get(
        "/api/v1/third-party/oauth/consent",
        headers=user_headers,
        params=params,
    )
    assert details.status_code == 200
    assert details.json()["app_name"] == "Synthetic OAuth Desktop"
    assert details.json()["requested_scopes"] == ["profile:read", "hash:read"]
    assert details.json()["previously_authorized"] is False

    approved = client.post(
        "/api/v1/third-party/oauth/consent",
        headers=user_headers,
        json={**params, "decision": "approve"},
    )
    assert approved.status_code == 200
    query = parse_qs(urlparse(approved.json()["redirect_url"]).query)
    assert query["state"] == ["synthetic-state-consent"]
    code = query["code"][0]

    token = client.post(
        "/api/v1/third-party/oauth/token",
        json={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
    )
    assert token.status_code == 200

    applications = client.get(
        "/api/v1/third-party/oauth/authorized-applications",
        headers=user_headers,
    )
    assert applications.status_code == 200
    assert len(applications.json()["items"]) == 1
    application = applications.json()["items"][0]
    assert application["client_id"] == client_id
    assert application["scopes"] == ["profile:read", "hash:read"]

    revoked = client.delete(
        f"/api/v1/third-party/oauth/authorized-applications/{application['app_id']}",
        headers=user_headers,
    )
    assert revoked.status_code == 204
    assert client.get(
        "/api/v1/third-party/oauth/authorized-applications",
        headers=user_headers,
    ).json()["items"] == []

    revoked_access = client.get(
        "/api/v1/third-party/oauth/me",
        headers={"Authorization": f"Bearer {token.json()['access_token']}"},
    )
    assert revoked_access.status_code == 401
    assert revoked_access.json()["code"] == "third_party_oauth.session_unavailable"
