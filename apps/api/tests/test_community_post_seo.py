from __future__ import annotations

from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.user import User


def _register_and_login(client, username: str) -> dict[str, str]:
    password = "SyntheticPass123!"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
        },
    )
    assert response.status_code == 201, response.text
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        user.email_verified_at = utc_now()
        db.commit()
    login = client.post("/api/v1/auth/login", json={"login": username, "password": password})
    assert login.status_code == 200, login.text
    return login.json()


def _auth_headers(tokens: dict[str, str], key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Idempotency-Key": key,
    }


def _create_post(client, tokens: dict[str, str]) -> dict:
    response = client.post(
        "/api/v1/community/posts",
        headers=_auth_headers(tokens, "post-seo-create-001"),
        json={
            "board_code": "general",
            "title": "合成帖子 SEO 字段测试主题",
            "content": "这是用于验证内容级 SEO 字段保存、投影和并发控制的合成正文。",
            "rules_accepted": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_post_seo_patch_persists_custom_fields_and_projects_them(client) -> None:
    tokens = _register_and_login(client, "post_seo_owner")
    post = _create_post(client, tokens)

    response = client.patch(
        f"/api/v1/community/posts/{post['id']}/seo",
        headers=_auth_headers(tokens, "post-seo-update-001"),
        json={
            "seo_title": "合成 SEO 标题",
            "seo_description": "合成 SEO 描述，只用于自动化验收。",
            "seo_keywords": ["合成", "SEO", "合成"],
            "seo_canonical_path": f"/community/posts/{post['id']}",
            "og_image_url": "https://example.com/synthetic-og.png",
            "expected_seo_version": 1,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["seo_version"] == 2
    assert body["seo_title"] == "合成 SEO 标题"
    assert body["seo_keywords"] == ["合成", "SEO"]
    assert body["seo"]["title"] == "合成 SEO 标题"
    assert body["seo"]["description"] == "合成 SEO 描述，只用于自动化验收。"
    assert body["seo"]["keywords"] == ["合成", "SEO"]
    assert body["seo"]["canonical_path"] == f"/community/posts/{post['id']}"
    assert body["seo"]["og_image_url"] == "https://example.com/synthetic-og.png"


def test_post_seo_patch_rejects_stale_version_and_unsafe_values(client) -> None:
    tokens = _register_and_login(client, "post_seo_validation")
    post = _create_post(client, tokens)

    initial = client.patch(
        f"/api/v1/community/posts/{post['id']}/seo",
        headers=_auth_headers(tokens, "post-seo-initial-001"),
        json={"seo_title": "初始标题", "expected_seo_version": 1},
    )
    assert initial.status_code == 200, initial.text

    stale = client.patch(
        f"/api/v1/community/posts/{post['id']}/seo",
        headers=_auth_headers(tokens, "post-seo-stale-001"),
        json={"seo_title": "新标题", "expected_seo_version": 1},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "community.edit_conflict"

    unsafe = client.patch(
        f"/api/v1/community/posts/{post['id']}/seo",
        headers=_auth_headers(tokens, "post-seo-unsafe-001"),
        json={
            "seo_title": "<script>alert(1)</script>",
            "seo_canonical_path": "https://evil.example/steal",
            "expected_seo_version": 1,
        },
    )
    assert unsafe.status_code == 422


def test_post_seo_patch_is_idempotent_and_forbidden_to_other_user(client) -> None:
    owner = _register_and_login(client, "post_seo_idempotent_owner")
    other = _register_and_login(client, "post_seo_other_user")
    post = _create_post(client, owner)
    payload = {"seo_title": "幂等标题", "expected_seo_version": 1}

    first = client.patch(
        f"/api/v1/community/posts/{post['id']}/seo",
        headers=_auth_headers(owner, "post-seo-idempotent-001"),
        json=payload,
    )
    second = client.patch(
        f"/api/v1/community/posts/{post['id']}/seo",
        headers=_auth_headers(owner, "post-seo-idempotent-001"),
        json=payload,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()

    forbidden = client.patch(
        f"/api/v1/community/posts/{post['id']}/seo",
        headers=_auth_headers(other, "post-seo-forbidden-001"),
        json={"seo_title": "越权标题", "expected_seo_version": 2},
    )
    assert forbidden.status_code == 403
