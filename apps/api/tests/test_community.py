from __future__ import annotations

import pyotp
from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.community import (
    CommunityComment,
    CommunityCommentLike,
    CommunityContentStatus,
    CommunityNotificationOutbox,
    CommunityNotificationOutboxStatus,
    CommunityPost,
    CommunityPostBookmark,
    CommunityPostLike,
    CommunityPostRevision,
    CommunityReport,
    CommunityReportStatus,
)
from password_detective.db.models.user import User, UserRole
from password_detective.modules.community.notification_service import (
    dispatch_pending_notification_events,
)
from password_detective.modules.community.notification_stream import (
    list_delivered_events,
)


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


def test_author_comment_delete_updates_reply_count_once(client):
    author = register_and_login(
        client,
        username="reply_projection_author",
        email="reply-projection-author@example.com",
    )
    created = client.post(
        "/api/v1/community/posts",
        json=post_payload(),
        headers=headers(author, "community-reply-projection-post-001"),
    ).json()
    replied = client.post(
        f"/api/v1/community/posts/{created['id']}/comments",
        json={
            "content": "这是一条用于验证回复数投影的合成评论。",
            "parent_id": None,
            "rules_accepted": True,
        },
        headers=headers(author, "community-reply-projection-comment-001"),
    ).json()
    comment = replied["comments"][0]
    assert replied["reply_count"] == 1

    deleted = client.delete(
        f"/api/v1/community/comments/{comment['id']}?expected_version=1",
        headers=headers(author, "community-reply-projection-delete-001"),
    )
    assert deleted.status_code == 200
    assert deleted.json()["reply_count"] == 0
    assert deleted.json()["comments"][0]["content"].startswith("该回复已由作者删除")

    duplicate = client.delete(
        f"/api/v1/community/comments/{comment['id']}?expected_version=2",
        headers=headers(author, "community-reply-projection-delete-002"),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "community.comment_already_deleted"
    detail = client.get(f"/api/v1/community/posts/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["reply_count"] == 0


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


def test_moderating_author_deleted_comment_does_not_double_decrement(client):
    author = register_and_login(
        client,
        username="deleted_comment_author",
        email="deleted-comment-author@example.com",
    )
    created = client.post(
        "/api/v1/community/posts",
        json=post_payload(),
        headers=headers(author, "community-deleted-comment-post-001"),
    ).json()
    comment = client.post(
        f"/api/v1/community/posts/{created['id']}/comments",
        json={
            "content": "这是一条先由作者删除、再进入治理流程的合成评论。",
            "parent_id": None,
            "rules_accepted": True,
        },
        headers=headers(author, "community-deleted-comment-create-001"),
    ).json()["comments"][0]
    deleted = client.delete(
        f"/api/v1/community/comments/{comment['id']}?expected_version=1",
        headers=headers(author, "community-deleted-comment-delete-001"),
    )
    assert deleted.status_code == 200
    assert deleted.json()["reply_count"] == 0

    reporter = register_and_login(
        client,
        username="deleted_comment_reporter",
        email="deleted-comment-reporter@example.com",
    )
    report = client.post(
        "/api/v1/community/reports",
        json={
            "post_id": created["id"],
            "comment_id": comment["id"],
            "reason": "privacy",
            "details": "该合成占位回复仍需完成治理状态闭环，但不得重复扣减回复数。",
        },
        headers=headers(reporter, "community-deleted-comment-report-001"),
    ).json()
    resolved = client.post(
        f"/api/v1/admin/community/reports/{report['id']}/resolve",
        json={
            "decision": "remove_and_lock",
            "note": "移除作者已删除的占位回复，并验证回复数投影保持不变。",
        },
        headers={
            **admin_headers(client),
            "Idempotency-Key": "community-deleted-comment-resolve-001",
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["post"]["reply_count"] == 0


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


def test_mentions_create_deduplicated_recipient_notifications(client):
    author = register_and_login(
        client,
        username="mention_author",
        email="mention-author@example.com",
    )
    mentioned = register_and_login(
        client,
        username="mention_target",
        email="mention-target@example.com",
    )
    payload = {
        **post_payload(),
        "title": "邀请 @mention_target 复核合成恢复记录",
        "content": (
            "请 @mention_target 与 @MENTION_TARGET 复核授权范围和哈希校验步骤，"
            "同时忽略未知用户 @missing_user 和作者自己 @mention_author。"
        ),
    }
    created = client.post(
        "/api/v1/community/posts",
        json=payload,
        headers=headers(author, "community-mention-post-001"),
    )
    assert created.status_code == 201

    target_list = client.get(
        "/api/v1/community/notifications",
        headers={"Authorization": f"Bearer {mentioned['access_token']}"},
    )
    assert target_list.status_code == 200
    body = target_list.json()
    assert body["unread_count"] == 1
    assert len(body["items"]) == 1
    notification = body["items"][0]
    assert notification["kind"] == "mention"
    assert notification["source_type"] == "post"
    assert notification["post_id"] == created.json()["id"]
    assert notification["comment_id"] is None
    assert notification["actor"]["username"] == "mention_author"
    assert "@mention_target" in notification["preview"]

    author_list = client.get(
        "/api/v1/community/notifications",
        headers={"Authorization": f"Bearer {author['access_token']}"},
    )
    assert author_list.status_code == 200
    assert author_list.json()["items"] == []

    marked = client.post(
        f"/api/v1/community/notifications/{notification['id']}/read",
        headers=headers(mentioned, "community-mention-read-001"),
    )
    assert marked.status_code == 200
    assert marked.json()["unread_count"] == 0

    replay = client.post(
        f"/api/v1/community/notifications/{notification['id']}/read",
        headers=headers(mentioned, "community-mention-read-001"),
    )
    assert replay.status_code == 200
    assert replay.json() == marked.json()


def test_comment_mentions_and_read_all_are_scoped_to_recipient(client):
    author = register_and_login(
        client,
        username="notify_author",
        email="notify-author@example.com",
    )
    recipient = register_and_login(
        client,
        username="notify_target",
        email="notify-target@example.com",
    )
    outsider = register_and_login(
        client,
        username="notify_outsider",
        email="notify-outsider@example.com",
    )
    created = client.post(
        "/api/v1/community/posts",
        json={
            **post_payload(),
            "content": "请 @notify_target 审阅这份合成测试恢复记录，并确认授权和回滚步骤完整。",
        },
        headers=headers(author, "community-mention-post-002"),
    ).json()
    commented = client.post(
        f"/api/v1/community/posts/{created['id']}/comments",
        json={
            "content": "再次请 @notify_target 检查评论中的最小化数据说明。",
            "rules_accepted": True,
        },
        headers=headers(author, "community-mention-comment-001"),
    )
    assert commented.status_code == 201

    unread = client.get(
        "/api/v1/community/notifications?unread_only=true&limit=1",
        headers={"Authorization": f"Bearer {recipient['access_token']}"},
    )
    assert unread.status_code == 200
    assert unread.json()["unread_count"] == 2
    assert unread.json()["has_more"] is True
    assert unread.json()["items"][0]["source_type"] == "comment"

    foreign_read = client.post(
        f"/api/v1/community/notifications/{unread.json()['items'][0]['id']}/read",
        headers=headers(outsider, "community-mention-foreign-read-001"),
    )
    assert foreign_read.status_code == 404
    assert foreign_read.json()["code"] == "community.notification_not_found"

    read_all = client.post(
        "/api/v1/community/notifications/read-all",
        headers=headers(recipient, "community-mention-read-all-001"),
    )
    assert read_all.status_code == 200
    assert read_all.json()["unread_count"] == 0
    remaining = client.get(
        "/api/v1/community/notifications?unread_only=true",
        headers={"Authorization": f"Bearer {recipient['access_token']}"},
    )
    assert remaining.status_code == 200
    assert remaining.json()["items"] == []

def test_post_and_comment_likes_are_idempotent_and_project_counts(client):
    author = register_and_login(
        client,
        username="interaction_author",
        email="interaction-author@example.com",
    )
    viewer = register_and_login(
        client,
        username="interaction_viewer",
        email="interaction-viewer@example.com",
    )
    post = client.post(
        "/api/v1/community/posts",
        json=post_payload(),
        headers=headers(author, "community-interaction-post-001"),
    ).json()
    detail = client.post(
        f"/api/v1/community/posts/{post['id']}/comments",
        json={
            "content": "这是一条用于测试点赞投影的合成回复。",
            "rules_accepted": True,
        },
        headers=headers(author, "community-interaction-comment-001"),
    ).json()
    comment_id = detail["comments"][0]["id"]

    liked_post = client.put(
        f"/api/v1/community/posts/{post['id']}/like",
        headers=headers(viewer, "community-post-like-001"),
    )
    assert liked_post.status_code == 200
    assert liked_post.json()["like_count"] == 1
    assert liked_post.json()["viewer_has_liked"] is True

    replay = client.put(
        f"/api/v1/community/posts/{post['id']}/like",
        headers=headers(viewer, "community-post-like-001"),
    )
    assert replay.status_code == 200
    assert replay.json() == liked_post.json()

    liked_comment = client.put(
        f"/api/v1/community/comments/{comment_id}/like",
        headers=headers(viewer, "community-comment-like-001"),
    )
    assert liked_comment.status_code == 200
    assert liked_comment.json() == {
        "comment_id": comment_id,
        "like_count": 1,
        "viewer_has_liked": True,
    }

    like_notifications = client.get(
        "/api/v1/community/notifications?kind=like_summary",
        headers={"Authorization": f"Bearer {author['access_token']}"},
    )
    assert like_notifications.status_code == 200
    assert {item["source_type"] for item in like_notifications.json()["items"]} == {
        "post",
        "comment",
    }
    assert {item["source_id"] for item in like_notifications.json()["items"]} == {
        post["id"],
        comment_id,
    }

    anonymous_detail = client.get(f"/api/v1/community/posts/{post['id']}")
    assert anonymous_detail.status_code == 200
    assert anonymous_detail.json()["like_count"] == 1
    assert anonymous_detail.json()["viewer_has_liked"] is False
    assert anonymous_detail.json()["comments"][0]["like_count"] == 1
    assert anonymous_detail.json()["comments"][0]["viewer_has_liked"] is False

    viewer_detail = client.get(
        f"/api/v1/community/posts/{post['id']}",
        headers={"Authorization": f"Bearer {viewer['access_token']}"},
    )
    assert viewer_detail.status_code == 200
    assert viewer_detail.json()["viewer_has_liked"] is True
    assert viewer_detail.json()["comments"][0]["viewer_has_liked"] is True

    unliked_post = client.delete(
        f"/api/v1/community/posts/{post['id']}/like",
        headers=headers(viewer, "community-post-unlike-001"),
    )
    assert unliked_post.status_code == 200
    assert unliked_post.json()["like_count"] == 0
    assert unliked_post.json()["viewer_has_liked"] is False

    unliked_comment = client.delete(
        f"/api/v1/community/comments/{comment_id}/like",
        headers=headers(viewer, "community-comment-unlike-001"),
    )
    assert unliked_comment.status_code == 200
    assert unliked_comment.json()["like_count"] == 0
    assert unliked_comment.json()["viewer_has_liked"] is False

    with client.app.state.database.session_factory() as db:
        assert db.scalar(select(CommunityPostLike)) is None
        assert db.scalar(select(CommunityCommentLike)) is None


def test_like_summary_notifications_aggregate_reopen_and_honor_preferences(client):
    author = register_and_login(
        client, username="like_notice_author", email="like-notice-author@example.com"
    )
    first = register_and_login(
        client, username="like_notice_first", email="like-notice-first@example.com"
    )
    second = register_and_login(
        client, username="like_notice_second", email="like-notice-second@example.com"
    )
    post = client.post(
        "/api/v1/community/posts",
        json=post_payload(),
        headers=headers(author, "like-notice-post"),
    ).json()

    assert client.put(
        f"/api/v1/community/posts/{post['id']}/like",
        headers=headers(first, "like-notice-first-like"),
    ).status_code == 200
    notifications = client.get(
        "/api/v1/community/notifications?kind=like_summary",
        headers={"Authorization": f"Bearer {author['access_token']}"},
    )
    assert notifications.status_code == 200
    assert len(notifications.json()["items"]) == 1
    notification = notifications.json()["items"][0]
    assert notification["source_type"] == "post"
    assert notification["source_id"] == post["id"]
    assert notification["actor"]["username"] == "like_notice_first"
    assert "共 1 个赞" in notification["preview"]

    marked = client.post(
        f"/api/v1/community/notifications/{notification['id']}/read",
        headers=headers(author, "like-notice-read"),
    )
    assert marked.status_code == 200
    assert marked.json()["unread_count"] == 0

    assert client.put(
        f"/api/v1/community/posts/{post['id']}/like",
        headers=headers(second, "like-notice-second-like"),
    ).status_code == 200
    reopened = client.get(
        "/api/v1/community/notifications?kind=like_summary&unread_only=true",
        headers={"Authorization": f"Bearer {author['access_token']}"},
    ).json()["items"]
    assert len(reopened) == 1
    assert reopened[0]["id"] == notification["id"]
    assert reopened[0]["actor"]["username"] == "like_notice_second"
    assert "共 2 个赞" in reopened[0]["preview"]

    assert client.delete(
        f"/api/v1/community/posts/{post['id']}/like",
        headers=headers(second, "like-notice-second-unlike"),
    ).status_code == 200
    reduced = client.get(
        "/api/v1/community/notifications?kind=like_summary",
        headers={"Authorization": f"Bearer {author['access_token']}"},
    ).json()["items"]
    assert len(reduced) == 1
    assert reduced[0]["actor"]["username"] == "like_notice_first"
    assert "共 1 个赞" in reduced[0]["preview"]

    assert client.delete(
        f"/api/v1/community/posts/{post['id']}/like",
        headers=headers(first, "like-notice-first-unlike"),
    ).status_code == 200
    cleared = client.get(
        "/api/v1/community/notifications?kind=like_summary",
        headers={"Authorization": f"Bearer {author['access_token']}"},
    )
    assert cleared.json()["items"] == []

    preference = client.put(
        "/api/v1/community/notifications/preferences",
        json={
            "items": [
                {
                    "kind": "like_summary",
                    "in_app_enabled": False,
                    "email_digest_enabled": False,
                }
            ]
        },
        headers={"Authorization": f"Bearer {author['access_token']}"},
    )
    assert preference.status_code == 200
    assert client.put(
        f"/api/v1/community/posts/{post['id']}/like",
        headers=headers(first, "like-notice-disabled-like"),
    ).status_code == 200
    disabled = client.get(
        "/api/v1/community/notifications?kind=like_summary",
        headers={"Authorization": f"Bearer {author['access_token']}"},
    )
    assert disabled.json()["items"] == []



def test_bookmarks_are_private_paginated_and_allow_removed_cleanup(client):
    author = register_and_login(
        client,
        username="bookmark_author",
        email="bookmark-author@example.com",
    )
    owner = register_and_login(
        client,
        username="bookmark_owner",
        email="bookmark-owner@example.com",
    )
    outsider = register_and_login(
        client,
        username="bookmark_outsider",
        email="bookmark-outsider@example.com",
    )
    first = client.post(
        "/api/v1/community/posts",
        json={**post_payload(), "title": "第一份合成收藏主题"},
        headers=headers(author, "community-bookmark-post-001"),
    ).json()
    second = client.post(
        "/api/v1/community/posts",
        json={**post_payload(), "title": "第二份合成收藏主题"},
        headers=headers(author, "community-bookmark-post-002"),
    ).json()

    for index, post in enumerate((first, second), start=1):
        bookmarked = client.put(
            f"/api/v1/community/posts/{post['id']}/bookmark",
            headers=headers(owner, f"community-bookmark-create-00{index}"),
        )
        assert bookmarked.status_code == 200
        assert bookmarked.json()["viewer_has_bookmarked"] is True

    owner_page = client.get(
        "/api/v1/community/bookmarks?limit=1",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert owner_page.status_code == 200
    assert len(owner_page.json()["items"]) == 1
    assert owner_page.json()["has_more"] is True
    assert owner_page.json()["next_cursor"]

    second_page = client.get(
        f"/api/v1/community/bookmarks?limit=1&cursor={owner_page.json()['next_cursor']}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert second_page.status_code == 200
    assert len(second_page.json()["items"]) == 1
    assert second_page.json()["has_more"] is False

    outsider_page = client.get(
        "/api/v1/community/bookmarks",
        headers={"Authorization": f"Bearer {outsider['access_token']}"},
    )
    assert outsider_page.status_code == 200
    assert outsider_page.json()["items"] == []

    with client.app.state.database.session_factory() as db:
        removed = db.get(CommunityPost, first["id"])
        assert removed is not None
        removed.status = CommunityContentStatus.REMOVED
        db.commit()

    removed_bookmarks = client.get(
        "/api/v1/community/bookmarks?limit=10",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert removed_bookmarks.status_code == 200
    removed_item = next(
        item for item in removed_bookmarks.json()["items"] if item["post_id"] == first["id"]
    )
    assert removed_item["post"] is None

    cannot_add_removed = client.put(
        f"/api/v1/community/posts/{first['id']}/bookmark",
        headers=headers(outsider, "community-bookmark-removed-add-001"),
    )
    assert cannot_add_removed.status_code == 404

    cleanup = client.delete(
        f"/api/v1/community/posts/{first['id']}/bookmark",
        headers=headers(owner, "community-bookmark-removed-delete-001"),
    )
    assert cleanup.status_code == 200
    assert cleanup.json()["viewer_has_bookmarked"] is False

    with client.app.state.database.session_factory() as db:
        assert db.scalar(
            select(CommunityPostBookmark).where(
                CommunityPostBookmark.user_id == db.scalar(
                    select(User.id).where(User.username == "bookmark_owner")
                ),
                CommunityPostBookmark.post_id == first["id"],
            )
        ) is None



def test_activity_feeds_and_reply_follow_notifications(client):
    author = register_and_login(
        client, username="activity_author", email="activity-author@example.com"
    )
    follower = register_and_login(
        client, username="activity_follower", email="activity-follower@example.com"
    )

    followed = client.put(
        "/api/v1/community/users/activity_author/follow",
        headers=headers(follower, "activity-follow-001"),
    )
    assert followed.status_code == 200

    post = client.post(
        "/api/v1/community/posts",
        json={**post_payload(), "title": "社区动态合成验证主题"},
        headers=headers(author, "activity-post-001"),
    )
    assert post.status_code == 201
    post_id = post.json()["id"]

    comment = client.post(
        f"/api/v1/community/posts/{post_id}/comments",
        json={"content": "这是用于验证回复通知的合成评论。", "rules_accepted": True},
        headers=headers(follower, "activity-comment-001"),
    )
    assert comment.status_code == 201

    latest = client.get("/api/v1/community/activity?feed=latest&limit=10")
    assert latest.status_code == 200
    latest_kinds = [item["kind"] for item in latest.json()["items"]]
    assert "post_published" in latest_kinds
    assert "comment_published" in latest_kinds
    assert "user_followed" in latest_kinds

    following = client.get(
        "/api/v1/community/activity?feed=following&limit=10",
        headers={"Authorization": f"Bearer {follower['access_token']}"},
    )
    assert following.status_code == 200
    assert all(
        item["actor"]["username"] == "activity_author"
        for item in following.json()["items"]
    )
    assert any(item["kind"] == "post_published" for item in following.json()["items"])

    anonymous_following = client.get("/api/v1/community/activity?feed=following")
    assert anonymous_following.status_code == 401

    author_notifications = client.get(
        "/api/v1/community/notifications?kind=reply",
        headers={"Authorization": f"Bearer {author['access_token']}"},
    )
    assert author_notifications.status_code == 200
    assert [item["kind"] for item in author_notifications.json()["items"]] == ["reply"]
    assert author_notifications.json()["items"][0]["post_id"] == post_id

    follow_notifications = client.get(
        "/api/v1/community/notifications?kind=follow",
        headers={"Authorization": f"Bearer {author['access_token']}"},
    )
    assert follow_notifications.status_code == 200
    assert follow_notifications.json()["items"][0]["post_id"] is None
    assert (
        follow_notifications.json()["items"][0]["actor"]["username"]
        == "activity_follower"
    )


def test_activity_and_notification_preferences_only_affect_future_events(client):
    target = register_and_login(
        client, username="preference_target", email="preference-target@example.com"
    )
    actor = register_and_login(
        client, username="preference_actor", email="preference-actor@example.com"
    )

    preferences = client.get(
        "/api/v1/community/notifications/preferences",
        headers={"Authorization": f"Bearer {target['access_token']}"},
    )
    assert preferences.status_code == 200
    assert {item["kind"] for item in preferences.json()["items"]} >= {
        "mention",
        "reply",
        "follow",
    }

    updated = client.put(
        "/api/v1/community/notifications/preferences",
        json={
            "items": [
                {
                    "kind": "follow",
                    "in_app_enabled": False,
                    "email_digest_enabled": True,
                }
            ]
        },
        headers={"Authorization": f"Bearer {target['access_token']}"},
    )
    assert updated.status_code == 200
    follow_preference = next(
        item for item in updated.json()["items"] if item["kind"] == "follow"
    )
    assert follow_preference == {
        "kind": "follow",
        "in_app_enabled": False,
        "email_digest_enabled": True,
    }

    activity_preferences = client.put(
        "/api/v1/community/activity/preferences",
        json={"share_group_joins": False, "share_follows": False},
        headers={"Authorization": f"Bearer {actor['access_token']}"},
    )
    assert activity_preferences.status_code == 200
    assert activity_preferences.json()["share_follows"] is False

    followed = client.put(
        "/api/v1/community/users/preference_target/follow",
        headers=headers(actor, "preference-follow-001"),
    )
    assert followed.status_code == 200

    target_notifications = client.get(
        "/api/v1/community/notifications?kind=follow",
        headers={"Authorization": f"Bearer {target['access_token']}"},
    )
    assert target_notifications.status_code == 200
    assert target_notifications.json()["items"] == []

    latest = client.get("/api/v1/community/activity?feed=latest&limit=20")
    assert latest.status_code == 200
    assert not any(
        item["kind"] == "user_followed"
        and item["actor"]["username"] == "preference_actor"
        for item in latest.json()["items"]
    )


def test_notification_outbox_dispatch_and_replay_cursor(client):
    recipient = register_and_login(
        client,
        username="stream_recipient",
        email="stream-recipient@example.com",
    )
    actor = register_and_login(
        client,
        username="stream_actor",
        email="stream-actor@example.com",
    )
    payload = post_payload()
    payload["content"] += " @stream_recipient"
    created = client.post(
        "/api/v1/community/posts",
        json=payload,
        headers=headers(actor, "community-stream-post-001"),
    )
    assert created.status_code == 201

    with client.app.state.database.session_factory() as db:
        event = db.scalar(select(CommunityNotificationOutbox))
        assert event is not None
        assert event.status == CommunityNotificationOutboxStatus.PENDING
        assert event.attempts == 0
        assert event.dedupe_key.endswith(":v1")

        dispatched = dispatch_pending_notification_events(db)
        assert dispatched == {
            "processed": 1,
            "delivered": 1,
            "retried": 0,
            "failed": 0,
        }
        batch = list_delivered_events(
            db, recipient_id=recipient["user"]["id"], after_event_id=None
        )
        assert len(batch.items) == 1
        assert batch.items[0].notification.actor.username == "stream_actor"
        assert batch.items[0].notification.post_id == created.json()["id"]
        assert batch.items[0].unread_count == 1

        replay = list_delivered_events(
            db,
            recipient_id=recipient["user"]["id"],
            after_event_id=batch.last_event_id,
        )
        assert replay.items == []
        assert replay.last_event_id == batch.last_event_id

        invalid_cursor = list_delivered_events(
            db,
            recipient_id=recipient["user"]["id"],
            after_event_id="missing-event-id",
        )
        assert invalid_cursor.items == []
        assert invalid_cursor.last_event_id == batch.last_event_id

        isolated = list_delivered_events(
            db,
            recipient_id=actor["user"]["id"],
            after_event_id=batch.last_event_id,
        )
        assert isolated.items == []
        assert isolated.last_event_id is None

        post = db.get(CommunityPost, created.json()["id"])
        assert post is not None
        post.status = CommunityContentStatus.REMOVED
        db.commit()
        hidden_after_removal = list_delivered_events(
            db, recipient_id=recipient["user"]["id"], after_event_id=None
        )
        assert hidden_after_removal.items == []

        assert dispatch_pending_notification_events(db)["processed"] == 0
