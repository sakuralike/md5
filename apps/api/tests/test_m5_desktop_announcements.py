from __future__ import annotations

from datetime import timedelta

from password_detective.core.time import utc_now
from password_detective.db.models.desktop_announcement import DesktopAnnouncement
from password_detective.db.models.user import User, UserRole


def _admin_headers(client) -> dict[str, str]:
    registration = {
        "username": "announcement_admin",
        "email": "announcement-admin@synthetic.example.com",
        "password": "SyntheticAnnouncementAdmin123!",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    with client.app.state.database.session_factory() as db:
        user = db.query(User).filter(User.username == registration["username"]).one()
        user.role = UserRole.ADMIN
        db.commit()
    return headers


def _announcement_payload() -> dict[str, object]:
    return {
        "title": "桌面端公告：验证规则更新",
        "content": "合成公告正文，不包含真实密码或令牌。",
        "content_type": "text",
        "image_urls": ["https://synthetic.example/notice.png"],
        "action_label": "查看说明",
        "action_url": "https://synthetic.example/guide",
        "sort_order": 10,
        "starts_at": (utc_now() - timedelta(minutes=1)).isoformat(),
        "ends_at": (utc_now() + timedelta(hours=1)).isoformat(),
    }


def test_desktop_announcement_crud_publish_public_and_archive(client):
    headers = _admin_headers(client)
    created = client.post(
        "/api/v1/admin/desktop-announcements", headers=headers, json=_announcement_payload()
    )
    assert created.status_code == 201
    announcement_id = created.json()["id"]
    assert client.get("/api/v1/desktop/announcements").json()["items"] == []

    published = client.post(
        f"/api/v1/admin/desktop-announcements/{announcement_id}/publish", headers=headers
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    public = client.get("/api/v1/desktop/announcements")
    assert public.status_code == 200
    assert public.headers["cache-control"] == "public, max-age=30"
    assert public.json()["items"][0]["title"] == "桌面端公告：验证规则更新"

    updated = client.put(
        f"/api/v1/admin/desktop-announcements/{announcement_id}",
        headers=headers,
        json={**_announcement_payload(), "title": "更新后的合成公告"},
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 3

    archived = client.post(
        f"/api/v1/admin/desktop-announcements/{announcement_id}/archive", headers=headers
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert client.get("/api/v1/desktop/announcements").json()["items"] == []

    with client.app.state.database.session_factory() as db:
        stored = db.get(DesktopAnnouncement, announcement_id)
        assert stored is not None
        assert stored.status.value == "archived"


def test_desktop_announcement_allows_image_link_without_action_label(client):
    headers = _admin_headers(client)
    payload = _announcement_payload()
    payload["action_label"] = None
    created = client.post(
        "/api/v1/admin/desktop-announcements", headers=headers, json=payload
    )
    assert created.status_code == 201
    assert created.json()["action_label"] is None
    assert created.json()["action_url"] == "https://synthetic.example/guide"


def test_desktop_announcement_rejects_invalid_window_and_action_url(client):
    headers = _admin_headers(client)
    payload = _announcement_payload()
    payload["action_url"] = "javascript:alert(1)"
    invalid_url = client.post("/api/v1/admin/desktop-announcements", headers=headers, json=payload)
    assert invalid_url.status_code == 422

    payload = _announcement_payload()
    payload["starts_at"], payload["ends_at"] = payload["ends_at"], payload["starts_at"]
    invalid_window = client.post(
        "/api/v1/admin/desktop-announcements", headers=headers, json=payload
    )
    assert invalid_window.status_code == 422

def test_desktop_announcement_image_upload_and_public_fetch(client):
    headers = _admin_headers(client)
    image = b"\x89PNG\r\n\x1a\nsynthetic-image"
    uploaded = client.post(
        "/api/v1/admin/desktop-announcements/images",
        headers={**headers, "Content-Type": "image/png"},
        content=image,
    )
    assert uploaded.status_code == 201
    payload = uploaded.json()
    assert payload["url"].startswith("/api/v1/desktop/announcements/assets/")
    assert payload["content_type"] == "image/png"
    assert payload["size_bytes"] == len(image)

    created_payload = _announcement_payload()
    created_payload["image_urls"] = [payload["url"]]
    created = client.post(
        "/api/v1/admin/desktop-announcements", headers=headers, json=created_payload
    )
    assert created.status_code == 201
    assert created.json()["image_urls"] == [payload["url"]]

    fetched = client.get(payload["url"])
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "image/png"
    assert fetched.content == image


def test_desktop_announcement_image_upload_rejects_mismatched_signature(client):
    headers = _admin_headers(client)
    response = client.post(
        "/api/v1/admin/desktop-announcements/images",
        headers={**headers, "Content-Type": "image/jpeg"},
        content=b"not-a-jpeg",
    )
    assert response.status_code == 422
