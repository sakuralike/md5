from __future__ import annotations

from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.community import CommunityBoard, CommunityBoardStatus
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
    assert response.status_code == 201
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        user.email_verified_at = utc_now()
        db.commit()
    login = client.post("/api/v1/auth/login", json={"login": username, "password": password})
    assert login.status_code == 200
    return login.json()


def _headers(tokens: dict[str, str], key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Idempotency-Key": key,
    }


def _create_group(client, tokens: dict[str, str], *, slug: str, visibility: str) -> dict:
    response = client.post(
        "/api/v1/community/groups",
        headers=_headers(tokens, f"seo-group-{slug}"),
        json={
            "slug": slug,
            "name": "合成 SEO 研究组",
            "description": "用于验证公开资格和受控 SEO 投影的合成群组。",
            "visibility": visibility,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_post(client, tokens: dict[str, str], *, group_slug: str | None = None) -> dict:
    response = client.post(
        "/api/v1/community/posts",
        headers=_headers(tokens, f"seo-post-key-{group_slug or 'root'}"),
        json={
            "board_code": "general",
            "group_slug": group_slug,
            "title": "合成公开主题的 SEO 投影验证",
            "content": "本主题只使用合成数据，验证公开资格、稳定路径与 SPA 安全 noindex 回退。",
            "rules_accepted": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _expected_public_seo(*, title: str, description: str, canonical_path: str) -> dict:
    return {
        "eligible": True,
        "indexable": False,
        "title": title,
        "description": description,
        "keywords": [],
        "canonical_path": canonical_path,
        "og_image_url": None,
    }


def _expected_private_seo() -> dict:
    return {
        "eligible": False,
        "indexable": False,
        "title": None,
        "description": None,
        "keywords": [],
        "canonical_path": None,
        "og_image_url": None,
    }


def test_public_post_and_group_expose_safe_future_seo_projection(client) -> None:
    owner = _register_and_login(client, "seo_public_owner")
    group = _create_group(client, owner, slug="seo-public-lab", visibility="public")
    post = _create_post(client, owner, group_slug=group["slug"])

    post_detail = client.get(f"/api/v1/community/posts/{post['id']}")
    assert post_detail.status_code == 200
    assert post_detail.json()["seo"] == _expected_public_seo(
        title="合成公开主题的 SEO 投影验证",
        description="本主题只使用合成数据，验证公开资格、稳定路径与 SPA 安全 noindex 回退。",
        canonical_path=f"/community/posts/{post['id']}",
    )

    group_detail = client.get("/api/v1/community/groups/seo-public-lab")
    assert group_detail.status_code == 200
    assert group_detail.json()["seo"] == _expected_public_seo(
        title="合成 SEO 研究组",
        description="用于验证公开资格和受控 SEO 投影的合成群组。",
        canonical_path="/community/groups/seo-public-lab",
    )

    profile = client.get("/api/v1/community/users/seo_public_owner")
    assert profile.status_code == 200
    assert "seo" not in profile.json()


def test_approval_group_and_inactive_board_never_emit_discoverable_metadata(client) -> None:
    owner = _register_and_login(client, "seo_restricted_owner")
    approval_group = _create_group(client, owner, slug="seo-approval-lab", visibility="approval")
    approval_detail = client.get(f"/api/v1/community/groups/{approval_group['slug']}")
    assert approval_detail.status_code == 200
    assert approval_detail.json()["seo"] == _expected_private_seo()

    post = _create_post(client, owner)
    with client.app.state.database.session_factory() as db:
        board = db.scalar(select(CommunityBoard).where(CommunityBoard.code == "general"))
        assert board is not None
        board.status = CommunityBoardStatus.INACTIVE
        db.commit()

    detail = client.get(
        f"/api/v1/community/posts/{post['id']}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert detail.status_code == 200
    assert detail.json()["seo"] == _expected_private_seo()
