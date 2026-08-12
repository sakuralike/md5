from __future__ import annotations

import pyotp
from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.community import (
    CommunityComment,
    CommunityContentStatus,
    CommunityPost,
    CommunityPostRevision,
    CommunityReport,
    CommunityReportStatus,
)
from password_detective.db.models.user import User, UserRole


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


def admin_headers(client) -> dict[str, str]:
    registration = {
        "username": "community_admin",
        "email": "community-admin@synthetic.example.com",
        "password": "SyntheticCommunityAdmin123!",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    initial_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        user.email_verified_at = utc_now()
        db.commit()
    setup = client.post("/api/v1/admin/totp/setup", headers=initial_headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    confirmed = client.post(
        "/api/v1/admin/totp/confirm",
        headers=initial_headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert confirmed.status_code == 200
    authenticated = client.post(
        "/api/v1/auth/login",
        json={
            "login": registration["username"],
            "password": registration["password"],
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert authenticated.status_code == 200
    return {"Authorization": f"Bearer {authenticated.json()['access_token']}"}


def test_verified_user_can_report_content_once(client):
    author = register_and_login(
        client,
        username="reported_author",
        email="reported-author@example.com",
    )
    created = client.post(
        "/api/v1/community/posts",
        json=post_payload(),
        headers=headers(author, "community-report-post-create-001"),
    ).json()
    reporter = register_and_login(
        client,
        username="content_reporter",
        email="content-reporter@example.com",
    )
    payload = {
        "post_id": created["id"],
        "comment_id": None,
        "reason": "unsafe",
        "details": "该主题可能诱导用户发布真实凭据，请管理员复核上下文。",
    }
    created_report = client.post(
        "/api/v1/community/reports",
        json=payload,
        headers=headers(reporter, "community-report-create-001"),
    )
    assert created_report.status_code == 201
    assert created_report.json()["status"] == "open"

    replay = client.post(
        "/api/v1/community/reports",
        json=payload,
        headers=headers(reporter, "community-report-create-001"),
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == created_report.json()["id"]

    duplicate = client.post(
        "/api/v1/community/reports",
        json=payload,
        headers=headers(reporter, "community-report-create-002"),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "community.report_already_open"


def test_admin_resolves_comment_report_and_locks_post(client):
    author = register_and_login(
        client,
        username="moderated_author",
        email="moderated-author@example.com",
    )
    created = client.post(
        "/api/v1/community/posts",
        json=post_payload(),
        headers=headers(author, "community-moderation-post-create-001"),
    ).json()
    comment = client.post(
        f"/api/v1/community/posts/{created['id']}/comments",
        json={
            "content": "这是一条用于审核流程的合成评论内容。",
            "parent_id": None,
            "rules_accepted": True,
        },
        headers=headers(author, "community-moderation-comment-create-001"),
    ).json()["comments"][0]
    reporter = register_and_login(
        client,
        username="moderation_reporter",
        email="moderation-reporter@example.com",
    )
    report = client.post(
        "/api/v1/community/reports",
        json={
            "post_id": created["id"],
            "comment_id": comment["id"],
            "reason": "privacy",
            "details": "该合成评论模拟包含不应公开的隐私数据，需要移除并锁定主题。",
        },
        headers=headers(reporter, "community-comment-report-create-001"),
    ).json()

    admin = admin_headers(client)
    queue = client.get("/api/v1/admin/community/reports?status=open", headers=admin)
    assert queue.status_code == 200
    assert queue.json()["total"] == 1
    assert queue.json()["items"][0]["target_type"] == "comment"

    mutation_headers = {**admin, "Idempotency-Key": "community-report-resolve-001"}
    resolved = client.post(
        f"/api/v1/admin/community/reports/{report['id']}/resolve",
        json={
            "decision": "remove_and_lock",
            "note": "确认内容不符合隐私最小化要求，移除评论并锁定主题。",
        },
        headers=mutation_headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["report"]["status"] == "resolved"
    assert resolved.json()["post"]["is_locked"] is True
    assert resolved.json()["post"]["reply_count"] == 0

    replay = client.post(
        f"/api/v1/admin/community/reports/{report['id']}/resolve",
        json={
            "decision": "remove_and_lock",
            "note": "确认内容不符合隐私最小化要求，移除评论并锁定主题。",
        },
        headers=mutation_headers,
    )
    assert replay.status_code == 200
    assert replay.json()["audit_id"] == resolved.json()["audit_id"]

    detail = client.get(f"/api/v1/community/posts/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["comments"] == []
    with client.app.state.database.session_factory() as db:
        stored_report = db.get(CommunityReport, report["id"])
        stored_comment = db.get(CommunityComment, comment["id"])
        assert stored_report is not None
        assert stored_report.status == CommunityReportStatus.RESOLVED
        assert stored_comment is not None
        assert stored_comment.status == CommunityContentStatus.REMOVED
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "community.report.resolve",
                AuditLog.target_id == report["id"],
            )
        )
        assert audit is not None


def test_admin_can_pin_remove_and_restore_post(client):
    author = register_and_login(
        client,
        username="post_governance_author",
        email="post-governance-author@example.com",
    )
    created = client.post(
        "/api/v1/community/posts",
        json=post_payload(),
        headers=headers(author, "community-governance-post-create-001"),
    ).json()
    admin = admin_headers(client)

    def moderate(action: str, key: str):
        return client.post(
            f"/api/v1/admin/community/posts/{created['id']}/moderate",
            json={"action": action, "note": f"执行 {action} 合成治理动作。"},
            headers={**admin, "Idempotency-Key": key},
        )

    pinned = moderate("pin", "community-post-moderate-001")
    assert pinned.status_code == 200
    assert pinned.json()["post"]["is_pinned"] is True

    removed = moderate("remove", "community-post-moderate-002")
    assert removed.status_code == 200
    assert removed.json()["post"]["status"] == "removed"
    assert client.get(f"/api/v1/community/posts/{created['id']}").status_code == 404

    restored = moderate("restore", "community-post-moderate-003")
    assert restored.status_code == 200
    assert restored.json()["post"]["status"] == "published"
    assert client.get(f"/api/v1/community/posts/{created['id']}").status_code == 200



def test_author_post_lifecycle_uses_versions_revisions_and_placeholder_delete(client):
    author = register_and_login(
        client,
        username="lifecycle_author",
        email="lifecycle-author@example.com",
    )
    created = client.post(
        "/api/v1/community/posts",
        json=post_payload(),
        headers=headers(author, "community-lifecycle-create-001"),
    ).json()

    updated = client.patch(
        f"/api/v1/community/posts/{created['id']}",
        json={
            **post_payload(),
            "title": "更新后的合成测试恢复排障记录",
            "content": "这是更新后的合成测试内容，只描述授权范围、校验步骤和可回滚的安全处理方式。",
            "expected_version": 1,
        },
        headers=headers(author, "community-lifecycle-update-001"),
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["edited_at"] is not None

    stale = client.patch(
        f"/api/v1/community/posts/{created['id']}",
        json={
            **post_payload(),
            "expected_version": 1,
        },
        headers=headers(author, "community-lifecycle-update-002"),
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "community.edit_conflict"

    with client.app.state.database.session_factory() as db:
        revision = db.scalar(
            select(CommunityPostRevision).where(
                CommunityPostRevision.post_id == created["id"],
                CommunityPostRevision.version == 1,
            )
        )
        assert revision is not None
        assert revision.title_snapshot == post_payload()["title"]

    deleted = client.delete(
        f"/api/v1/community/posts/{created['id']}?expected_version=2",
        headers=headers(author, "community-lifecycle-delete-001"),
    )
    assert deleted.status_code == 200
    assert deleted.json()["version"] == 3
    assert deleted.json()["title"] == "[主题已由作者删除]"
    assert client.get(f"/api/v1/community/posts/{created['id']}").json()["content"].startswith(
        "该主题已由作者删除"
    )


def test_comment_cursor_and_nested_reply_metadata(client):
    author = register_and_login(
        client,
        username="cursor_author",
        email="cursor-author@example.com",
    )
    created = client.post(
        "/api/v1/community/posts",
        json=post_payload(),
        headers=headers(author, "community-cursor-post-001"),
    ).json()
    first = client.post(
        f"/api/v1/community/posts/{created['id']}/comments",
        json={"content": "第一条合成评论用于验证游标顺序。", "rules_accepted": True},
        headers=headers(author, "community-cursor-comment-001"),
    ).json()["comments"][0]
    second = client.post(
        f"/api/v1/community/posts/{created['id']}/comments",
        json={
            "content": "第二条回复用于验证嵌套关系和游标分页。",
            "parent_id": first["id"],
            "rules_accepted": True,
        },
        headers=headers(author, "community-cursor-comment-002"),
    ).json()["comments"][-1]
    assert second["root_id"] == first["id"]
    assert second["reply_to_user_id"] == first["author"]["user_id"]

    page_one = client.get(f"/api/v1/community/posts/{created['id']}/comments?limit=1")
    assert page_one.status_code == 200
    assert page_one.json()["has_more"] is True
    assert page_one.json()["items"][0]["id"] == first["id"]
    page_two = client.get(
        f"/api/v1/community/posts/{created['id']}/comments",
        params={"limit": 1, "cursor": page_one.json()["next_cursor"]},
    )
    assert page_two.status_code == 200
    assert page_two.json()["items"][0]["id"] == second["id"]
    assert page_two.json()["has_more"] is False


def test_community_home_returns_boards_and_post_summary(client):
    response = client.get("/api/v1/community/home?page_size=5")
    assert response.status_code == 200
    assert len(response.json()["boards"]) == 4
    assert response.json()["posts"]["page_size"] == 5
