from __future__ import annotations

import base64
from datetime import UTC, datetime

from sqlalchemy import select

from password_detective.db.models.community import CommunityPost
from password_detective.db.models.community_image import CommunityImageStatus, CommunityPostImage
from password_detective.db.models.user import User

PASSWORD = "SyntheticImagesPass123!"
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _register_login(client, suffix: str) -> tuple[dict[str, str], str]:
    payload = {
        "username": f"image_{suffix}",
        "email": f"image-{suffix}@synthetic.example.com",
        "password": PASSWORD,
    }
    registered = client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201
    user_id = registered.json()["id"]
    with client.app.state.database.session_factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        user.email_verified_at = datetime.now(UTC)
        db.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={"login": payload["username"], "password": PASSWORD},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, user_id


def test_post_image_upload_is_disabled_by_default(client):
    headers, _ = _register_login(client, "disabled")
    response = client.post(
        "/api/v1/community/images",
        headers={**headers, "Content-Type": "image/png"},
        content=PNG_1X1,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "community.image_upload_disabled"


def test_admin_can_enable_image_upload_and_bind_only_owned_clean_image(client):
    owner_headers, owner_id = _register_login(client, "owner")
    other_headers, _ = _register_login(client, "other")
    config = client.put(
        "/api/v1/admin/community/image-upload-config",
        json={"enabled": True, "max_bytes": 5_242_880, "max_pixels": 20_000_000, "max_per_post": 4},
        headers=owner_headers,
    )
    assert config.status_code == 403

    with client.app.state.database.session_factory() as db:
        user = db.get(User, owner_id)
        assert user is not None
        user.role = "admin"
        db.commit()
    enabled = client.put(
        "/api/v1/admin/community/image-upload-config",
        json={"enabled": True, "max_bytes": 5_242_880, "max_pixels": 20_000_000, "max_per_post": 4},
        headers=owner_headers,
    )
    assert enabled.status_code == 200, enabled.text

    uploaded = client.post(
        "/api/v1/community/images",
        headers={**owner_headers, "Content-Type": "image/png"},
        content=PNG_1X1,
    )
    assert uploaded.status_code == 201, uploaded.text
    image = uploaded.json()
    assert image["content_type"] == "image/png"

    cross_account = client.post(
        "/api/v1/community/posts",
        headers={**other_headers, "Idempotency-Key": "image-cross-account-0001"},
        json={
            "board_code": "general",
            "title": "合成图片权限验证主题",
            "content": "这是用于验证主题图片所有权边界的合成社区内容。",
            "rules_accepted": True,
            "attachment_ids": [image["id"]],
        },
    )
    assert cross_account.status_code == 422
    assert cross_account.json()["code"] == "community.image_attachment_invalid"

    created = client.post(
        "/api/v1/community/posts",
        headers={**owner_headers, "Idempotency-Key": "image-owner-post-0001"},
        json={
            "board_code": "general",
            "title": "合成图片绑定验证主题",
            "content": "这是用于验证主题图片绑定和公开访问边界的合成社区内容。",
            "rules_accepted": True,
            "attachment_ids": [image["id"]],
        },
    )
    assert created.status_code == 201, created.text
    post = created.json()
    assert len(post["attachments"]) == 1
    content = client.get(post["attachments"][0]["url"])
    assert content.status_code == 200
    assert content.headers["content-type"] == "image/png"
    assert content.headers["x-content-type-options"] == "nosniff"
    assert content.content == PNG_1X1

    with client.app.state.database.session_factory() as db:
        stored = db.get(CommunityPostImage, image["id"])
        assert stored is not None
        assert stored.status == CommunityImageStatus.ATTACHED
    assert stored.post_id == post["id"]
    assert db.scalar(select(CommunityPost).where(CommunityPost.id == post["id"])) is not None

    listed = client.get("/api/v1/admin/community/images", headers=owner_headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["post_id"] == post["id"]
    assert listed.json()["items"][0]["owner_username"] == "image_owner"
    assert "asset_name" not in listed.text
    assert "sha256" not in listed.text

    removed = client.post(
        f"/api/v1/admin/community/images/{image['id']}/remove",
        headers=owner_headers,
    )
    assert removed.status_code == 200, removed.text
    removed_list = client.get(
        "/api/v1/admin/community/images?status=removed",
        headers=owner_headers,
    )
    assert removed_list.status_code == 200
    assert removed_list.json()["total"] == 1


def test_image_metadata_is_rejected(client):
    headers, user_id = _register_login(client, "metadata")
    with client.app.state.database.session_factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        user.role = "admin"
        db.commit()
    enabled = client.put(
        "/api/v1/admin/community/image-upload-config",
        json={"enabled": True, "max_bytes": 5_242_880, "max_pixels": 20_000_000, "max_per_post": 4},
        headers=headers,
    )
    assert enabled.status_code == 200
    metadata_png = PNG_1X1[:33] + b"tEXt" + PNG_1X1[37:]
    response = client.post(
        "/api/v1/community/images",
        headers={**headers, "Content-Type": "image/png"},
        content=metadata_png,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "community.image_signature_invalid"
