from __future__ import annotations

import base64
import hashlib
from datetime import timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from password_detective.core.time import utc_now


def _register_and_login(client, suffix: str) -> dict[str, str]:
    username = f"tp_content_{suffix}_{uuid4().hex[:8]}"[:32]
    payload = {
        "username": username,
        "email": f"{username}@synthetic.example.com",
        "password": "SyntheticThirdPartyContent123!",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": payload["username"], "password": payload["password"]},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _admin_headers(client) -> dict[str, str]:
    headers = _register_and_login(client, "admin")
    from password_detective.db.models.user import User, UserRole

    with client.app.state.database.session_factory() as db:
        user = db.query(User).filter(User.username.like("tp_content_admin_%")).one()
        user.role = UserRole.ADMIN
        db.commit()
    return headers


def _pkce(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


def _approved_app(client, admin_headers: dict[str, str], *, suffix: str, scopes: list[str]):
    created = client.post(
        "/api/v1/admin/third-party-apps",
        headers=admin_headers,
        json={
            "name": f"Synthetic Content Reader {suffix}",
            "developer_name": "Synthetic Developer",
            "redirect_uris": [f"http://127.0.0.1:{49600 + len(suffix)}/callback"],
            "scopes": scopes,
        },
    )
    assert created.status_code == 201
    approved = client.post(
        f"/api/v1/admin/third-party-apps/{created.json()['id']}/approve",
        headers=admin_headers,
    )
    assert approved.status_code == 200
    return approved.json()


def _token(client, app: dict[str, object], user_headers: dict[str, str], *, scopes: str):
    verifier = f"synthetic-content-reader-{uuid4().hex}-abcdefghijklmnopqrstuvwxyz"
    redirect_uri = str(app["redirect_uris"][0])
    authorized = client.get(
        "/api/v1/third-party/oauth/authorize",
        headers=user_headers,
        params={
            "response_type": "code",
            "client_id": app["client_id"],
            "redirect_uri": redirect_uri,
            "code_challenge": _pkce(verifier),
            "code_challenge_method": "S256",
            "scope": scopes,
            "state": f"synthetic-state-{uuid4().hex}",
        },
        follow_redirects=False,
    )
    assert authorized.status_code == 302
    code = parse_qs(urlparse(authorized.headers["location"]).query)["code"][0]
    exchanged = client.post(
        "/api/v1/third-party/oauth/token",
        json={
            "grant_type": "authorization_code",
            "client_id": app["client_id"],
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
    )
    assert exchanged.status_code == 200
    return {"Authorization": f"Bearer {exchanged.json()['access_token']}"}


def _announcement_payload() -> dict[str, object]:
    return {
        "title": "第三方桌面合成公告",
        "content": "第三方桌面端只读公告正文。",
        "content_type": "text",
        "image_urls": ["https://synthetic.example/announcement.png"],
        "action_label": "查看说明",
        "action_url": "https://synthetic.example/guide",
        "starts_at": (utc_now() - timedelta(minutes=1)).isoformat(),
        "ends_at": (utc_now() + timedelta(hours=1)).isoformat(),
    }


def _publish_announcement(client, admin_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/admin/desktop-announcements",
        headers=admin_headers,
        json=_announcement_payload(),
    )
    assert created.status_code == 201
    published = client.post(
        f"/api/v1/admin/desktop-announcements/{created.json()['id']}/publish",
        headers=admin_headers,
    )
    assert published.status_code == 200


def _release_payload(artifact: bytes) -> dict[str, object]:
    return {
        "channel": "stable",
        "platform": "windows",
        "architecture": "x64",
        "version": "0.9.0",
        "minimum_supported_version": "0.1.0",
        "mandatory": False,
        "release_notes": "第三方桌面端合成更新说明。",
        "artifact_filename": "password-detective-0.9.0-x64.msix",
        "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
        "artifact_size_bytes": len(artifact),
        "content_type": "application/msix",
        "distribution_authorized": True,
        "legal_declaration": "该合成制品具备合法分发授权且仅用于测试。",
    }


def _publish_release(client, admin_headers: dict[str, str]) -> None:
    artifact = b"synthetic-third-party-update-artifact"
    created = client.post(
        "/api/v1/admin/desktop-releases",
        headers=admin_headers,
        json=_release_payload(artifact),
    )
    assert created.status_code == 201
    release_id = created.json()["id"]
    uploaded = client.put(
        f"/api/v1/admin/desktop-releases/{release_id}/artifact",
        headers={**admin_headers, "Content-Type": "application/octet-stream"},
        content=artifact,
    )
    assert uploaded.status_code == 200
    published = client.post(
        f"/api/v1/admin/desktop-releases/{release_id}/publish",
        headers=admin_headers,
    )
    assert published.status_code == 200


def test_third_party_announcements_use_dedicated_scope_and_safe_projection(client) -> None:
    admin_headers = _admin_headers(client)
    user_headers = _register_and_login(client, "announcement")
    app = _approved_app(client, admin_headers, suffix="announcement", scopes=["announcements:read"])
    access = _token(client, app, user_headers, scopes="announcements:read")
    _publish_announcement(client, admin_headers)

    response = client.get("/api/v1/third-party/announcements", headers=access)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert body["items"][0]["title"] == "第三方桌面合成公告"
    assert "revision" not in body["items"][0]
    assert "archived_at" not in body["items"][0]
    assert client.get("/api/v1/third-party/announcements").status_code == 401


def test_third_party_updates_use_dedicated_scope_and_cannot_cross_scope(client) -> None:
    admin_headers = _admin_headers(client)
    user_headers = _register_and_login(client, "update")
    announcement_app = _approved_app(
        client, admin_headers, suffix="announcement-scope", scopes=["announcements:read"]
    )
    update_app = _approved_app(
        client, admin_headers, suffix="update-scope", scopes=["updates:read"]
    )
    announcement_access = _token(
        client, announcement_app, user_headers, scopes="announcements:read"
    )
    update_access = _token(client, update_app, user_headers, scopes="updates:read")
    _publish_release(client, admin_headers)

    response = client.get(
        "/api/v1/third-party/updates/check",
        headers=update_access,
        params={"current_version": "0.1.0", "channel": "stable", "architecture": "x64"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert body["update_available"] is True
    assert body["latest_version"] == "0.9.0"
    assert "distribution_authorized" not in body
    assert (
        client.get(
            "/api/v1/third-party/updates/check",
            headers=announcement_access,
            params={"current_version": "0.1.0", "architecture": "x64"},
        ).json()["code"]
        == "third_party_oauth.insufficient_scope"
    )
    assert client.get("/api/v1/third-party/announcements", headers=update_access).json()[
        "code"
    ] == ("third_party_oauth.insufficient_scope")
