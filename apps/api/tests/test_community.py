from __future__ import annotations

from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.community import CommunityPost
from password_detective.db.models.user import User


def register_and_login(client, *, username: str, email: str, verified: bool = True) -> dict:
    payload = {
        "username": username,
        "email": email,
        "password": "SyntheticPass123!",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    if verified:
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


def headers(tokens: dict, key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Idempotency-Key": key,
    }


def post_payload() -> dict:
    return {
        "board_code": "recovery_guides",
        "title": "合成测试压缩包的恢复排障记录",
        "content": "这里只讨论获得授权的合成测试数据，并记录本地验证、失败回滚和隐私保护步骤。",
        "rules_accepted": True,
    }


def test_public_board_catalog_and_empty_post_list(client):
    boards = client.get("/api/v1/community/boards")
    assert boards.status_code == 200
    assert [item["code"] for item in boards.json()["items"]] == [
        "general",
        "recovery_guides",
        "verification",
        "security",
    ]
    assert all(item["post_count"] == 0 for item in boards.json()["items"])

    posts = client.get("/api/v1/community/posts")
    assert posts.status_code == 200
    assert posts.json() == {"items": [], "page": 1, "page_size": 20, "total": 0}


def test_verified_user_can_create_and_replay_post(client):
    tokens = register_and_login(
        client,
        username="community_author",
        email="community-author@example.com",
    )
    request_headers = headers(tokens, "community-post-create-001")
    created = client.post(
        "/api/v1/community/posts",
        json=post_payload(),
        headers=request_headers,
    )
    assert created.status_code == 201
    assert created.json()["author"]["username"] == "community_author"
    assert created.json()["comments"] == []

    replay = client.post(
        "/api/v1/community/posts",
        json=post_payload(),
        headers=request_headers,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == created.json()["id"]

    listing = client.get("/api/v1/community/posts?board_code=recovery_guides")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == created.json()["id"]


def test_verified_user_can_reply_and_locked_posts_reject_replies(client):
    author = register_and_login(
        client,
        username="topic_author",
        email="topic-author@example.com",
    )
    created = client.post(
        "/api/v1/community/posts",
        json=post_payload(),
        headers=headers(author, "community-post-create-002"),
    ).json()

    commenter = register_and_login(
        client,
        username="topic_commenter",
        email="topic-commenter@example.com",
    )
    comment_payload = {
        "content": "建议补充校验文件哈希和清理临时文件的步骤。",
        "parent_id": None,
        "rules_accepted": True,
    }
    comment_headers = headers(commenter, "community-comment-create-001")
    replied = client.post(
        f"/api/v1/community/posts/{created['id']}/comments",
        json=comment_payload,
        headers=comment_headers,
    )
    assert replied.status_code == 201
    assert replied.json()["reply_count"] == 1
    assert replied.json()["comments"][0]["author"]["username"] == "topic_commenter"

    replay = client.post(
        f"/api/v1/community/posts/{created['id']}/comments",
        json=comment_payload,
        headers=comment_headers,
    )
    assert replay.status_code == 201
    assert replay.json()["reply_count"] == 1

    with client.app.state.database.session_factory() as db:
        post = db.get(CommunityPost, created["id"])
        assert post is not None
        post.is_locked = True
        db.commit()

    locked = client.post(
        f"/api/v1/community/posts/{created['id']}/comments",
        json=comment_payload,
        headers=headers(commenter, "community-comment-create-002"),
    )
    assert locked.status_code == 409
    assert locked.json()["code"] == "community.post_locked"


def test_publish_requires_verified_email_and_rules_acceptance(client):
    unverified = register_and_login(
        client,
        username="unverified_author",
        email="unverified-author@example.com",
        verified=False,
    )
    rejected = client.post(
        "/api/v1/community/posts",
        json=post_payload(),
        headers=headers(unverified, "community-post-create-003"),
    )
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "community.email_verification_required"

    verified = register_and_login(
        client,
        username="rules_author",
        email="rules-author@example.com",
    )
    payload = {**post_payload(), "rules_accepted": False}
    rules = client.post(
        "/api/v1/community/posts",
        json=payload,
        headers=headers(verified, "community-post-create-004"),
    )
    assert rules.status_code == 422
    assert rules.json()["code"] == "community.rules_not_accepted"
