from __future__ import annotations

from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.community import CommunityPublicProfile
from password_detective.db.models.user import User

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0dIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _register_login(client, username: str) -> dict[str, str]:
    payload = {
        "username": username,
        "email": f"{username}@example.com",
        "password": "SyntheticAvatarPass123!",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        user.email_verified_at = utc_now()
        db.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"login": username, "password": payload["password"]},
    )
    assert response.status_code == 200
    return response.json()


def _headers(tokens: dict[str, str], key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Idempotency-Key": f"{key}-synthetic-key",
    }


def test_avatar_upload_uses_safe_public_projection_and_generated_fallback(client) -> None:
    tokens = _register_login(client, "avatar_owner")
    anonymous = client.post(
        "/api/v1/community/me/avatar",
        content=PNG_1X1,
        headers={"Content-Type": "image/png"},
    )
    assert anonymous.status_code == 401

    invalid = client.post(
        "/api/v1/community/me/avatar",
        content=b"not-a-png",
        headers={**_headers(tokens, "avatar-invalid"), "Content-Type": "image/png"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "community.avatar_signature_invalid"

    uploaded = client.post(
        "/api/v1/community/me/avatar",
        content=PNG_1X1,
        headers={**_headers(tokens, "avatar-upload"), "Content-Type": "image/png"},
    )
    assert uploaded.status_code == 201, uploaded.text
    uploaded_body = uploaded.json()
    assert uploaded_body["avatar_kind"] == "upload"
    assert uploaded_body["avatar_url"].startswith("/api/v1/site/assets/avatars/")

    image = client.get(uploaded_body["avatar_url"])
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")
    assert image.content == PNG_1X1
    assert client.get("/api/v1/site/assets/avatars/../../user.db").status_code == 404

    gravatar = client.patch(
        "/api/v1/community/me/profile",
        json={
            "display_name": "合成头像用户",
            "bio": "仅展示安全头像投影",
            "avatar_kind": "gravatar",
            "gravatar_enabled": True,
        },
        headers=_headers(tokens, "avatar-gravatar"),
    )
    assert gravatar.status_code == 200, gravatar.text
    assert gravatar.json()["avatar_kind"] == "gravatar"
    assert gravatar.json()["avatar_url"].startswith("https://www.gravatar.com/avatar/")

    generated = client.patch(
        "/api/v1/community/me/profile",
        json={
            "display_name": "合成头像用户",
            "bio": "仅展示安全头像投影",
            "avatar_kind": "generated",
            "gravatar_enabled": False,
        },
        headers=_headers(tokens, "avatar-generated"),
    )
    assert generated.status_code == 200
    assert generated.json()["avatar_kind"] == "generated"
    assert generated.json()["avatar_url"] is None

    public = client.get("/api/v1/community/users/avatar_owner")
    assert public.status_code == 200
    assert public.json()["avatar_kind"] == "generated"
    assert public.json()["avatar_url"] is None
    assert "email" not in public.json()

    with client.app.state.database.session_factory() as db:
        profile = db.get(CommunityPublicProfile, tokens["user"]["id"])
        assert profile is not None
        assert profile.avatar_kind.value == "generated"
        action_names = set(
            db.scalars(
                select(AuditLog.action).where(AuditLog.target_id == tokens["user"]["id"])
            ).all()
        )
    assert "community.avatar.uploaded" in action_names
    assert "community.profile.updated" in action_names
