from __future__ import annotations

from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.user import User


def _register_and_login(client, username: str) -> dict[str, str]:
    password = "SyntheticPass123!"
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": password},
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


def _headers(tokens: dict[str, str], key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Idempotency-Key": key,
    }


def _create_group(client, tokens: dict[str, str], slug: str = "group-seo-lab") -> dict:
    response = client.post(
        "/api/v1/community/groups",
        headers=_headers(tokens, f"group-seo-create-{slug}"),
        json={
            "slug": slug,
            "name": "合成群组 SEO 实验室",
            "description": "仅用于群组 SEO 字段自动化验收。",
            "visibility": "public",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_group_owner_can_update_safe_seo_fields(client) -> None:
    owner = _register_and_login(client, "group_seo_owner")
    group = _create_group(client, owner)

    response = client.patch(
        f"/api/v1/community/groups/{group['slug']}/seo",
        headers=_headers(owner, "group-seo-update-001"),
        json={
            "seo_title": "合成群组搜索标题",
            "seo_description": "合成群组搜索摘要。",
            "seo_keywords": ["合成", "群组", "合成"],
            "seo_canonical_path": f"/community/groups/{group['slug']}",
            "og_image_url": "/assets/community/group-share.png",
            "expected_seo_version": 1,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["seo_version"] == 2
    assert body["seo_title"] == "合成群组搜索标题"
    assert body["seo_keywords"] == ["合成", "群组"]
    assert body["seo"]["title"] == "合成群组搜索标题"
    assert body["seo"]["canonical_path"] == f"/community/groups/{group['slug']}"
    assert body["seo"]["indexable"] is False


def test_group_seo_update_is_idempotent_and_rejects_conflict(client) -> None:
    owner = _register_and_login(client, "group_seo_conflict_owner")
    group = _create_group(client, owner, slug="group-seo-conflict")
    payload = {"seo_title": "幂等群组标题", "expected_seo_version": 1}

    first = client.patch(
        f"/api/v1/community/groups/{group['slug']}/seo",
        headers=_headers(owner, "group-seo-idempotent-001"),
        json=payload,
    )
    replay = client.patch(
        f"/api/v1/community/groups/{group['slug']}/seo",
        headers=_headers(owner, "group-seo-idempotent-001"),
        json=payload,
    )
    stale = client.patch(
        f"/api/v1/community/groups/{group['slug']}/seo",
        headers=_headers(owner, "group-seo-stale-001"),
        json={"seo_title": "过期标题", "expected_seo_version": 1},
    )

    assert first.status_code == 200
    assert replay.json() == first.json()
    assert stale.status_code == 409
    assert stale.json()["code"] == "community.edit_conflict"


def test_group_seo_update_rejects_non_owner_and_unsafe_values(client) -> None:
    owner = _register_and_login(client, "group_seo_guard_owner")
    other = _register_and_login(client, "group_seo_guard_other")
    group = _create_group(client, owner, slug="group-seo-guard")

    forbidden = client.patch(
        f"/api/v1/community/groups/{group['slug']}/seo",
        headers=_headers(other, "group-seo-forbidden-001"),
        json={"seo_title": "越权标题", "expected_seo_version": 1},
    )
    unsafe = client.patch(
        f"/api/v1/community/groups/{group['slug']}/seo",
        headers=_headers(owner, "group-seo-unsafe-001"),
        json={
            "seo_title": "<script>alert(1)</script>",
            "seo_canonical_path": "https://invalid.example/group",
            "expected_seo_version": 1,
        },
    )

    assert forbidden.status_code == 403
    assert unsafe.status_code == 422
