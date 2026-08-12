from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.community import (
    CommunityBoardCode,
    CommunityComment,
    CommunityContentStatus,
    CommunityNotification,
    CommunityNotificationKind,
    CommunityNotificationSource,
    CommunityPost,
    CommunityPostRevision,
    CommunityReport,
    CommunityReportStatus,
)
from password_detective.db.models.user import User, UserStatus
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.community.schemas import (
    CommunityAuthor,
    CommunityBoard,
    CommunityBoardListResponse,
    CommunityCommentCreateRequest,
    CommunityCommentListResponse,
    CommunityCommentResponse,
    CommunityCommentUpdateRequest,
    CommunityHomeResponse,
    CommunityNotificationListResponse,
    CommunityNotificationReadResponse,
    CommunityNotificationResponse,
    CommunityPostCreateRequest,
    CommunityPostDetail,
    CommunityPostListResponse,
    CommunityPostSummary,
    CommunityPostUpdateRequest,
    CommunityReportCreateRequest,
    CommunityReportResponse,
)

_MENTION_PATTERN = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_]{3,32})")
_MAX_MENTIONS_PER_CONTENT = 10


_BOARD_CATALOG: tuple[tuple[CommunityBoardCode, str, str], ...] = (
    (CommunityBoardCode.GENERAL, "社区广场", "交流安全恢复经验、工具使用方式与协作建议。"),
    (CommunityBoardCode.RECOVERY_GUIDES, "恢复指南", "分享合法授权场景下的恢复流程与排障记录。"),
    (CommunityBoardCode.VERIFICATION, "验证协作", "讨论指纹、候选结果与验证证据，不发布真实密码。"),
    (CommunityBoardCode.SECURITY, "安全与隐私", "交流账号保护、数据最小化与隐私实践。"),
)


def list_boards(db: Session) -> CommunityBoardListResponse:
    counts = dict(
        db.execute(
            select(CommunityPost.board_code, func.count(CommunityPost.id))
            .where(CommunityPost.status == CommunityContentStatus.PUBLISHED)
            .group_by(CommunityPost.board_code)
        ).all()
    )
    return CommunityBoardListResponse(
        items=[
            CommunityBoard(
                code=code,
                name=name,
                description=description,
                post_count=counts.get(code, 0),
            )
            for code, name, description in _BOARD_CATALOG
        ]
    )


def list_posts(
    db: Session,
    *,
    board_code: CommunityBoardCode | None,
    page: int,
    page_size: int,
) -> CommunityPostListResponse:
    conditions = [CommunityPost.status == CommunityContentStatus.PUBLISHED]
    if board_code is not None:
        conditions.append(CommunityPost.board_code == board_code)
    total = db.scalar(select(func.count(CommunityPost.id)).where(*conditions)) or 0
    posts = db.scalars(
        select(CommunityPost)
        .where(*conditions)
        .order_by(CommunityPost.is_pinned.desc(), CommunityPost.last_activity_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    authors = _load_authors(db, [post.author_id for post in posts])
    return CommunityPostListResponse(
        items=[_post_summary(post, authors[post.author_id]) for post in posts],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_post(db: Session, post_id: str) -> CommunityPostDetail:
    post = _get_published_post(db, post_id)
    comments = _list_comment_models(db, post.id, cursor=None, limit=50)[0]
    authors = _load_authors(
        db,
        [post.author_id, *(comment.author_id for comment in comments)],
    )
    return _post_detail(post, authors, comments)


def list_home(
    db: Session,
    *,
    board_code: CommunityBoardCode | None,
    page_size: int,
) -> CommunityHomeResponse:
    return CommunityHomeResponse(
        boards=list_boards(db).items,
        posts=list_posts(db, board_code=board_code, page=1, page_size=page_size),
    )


def list_comments(
    db: Session,
    *,
    post_id: str,
    cursor: str | None,
    limit: int,
) -> CommunityCommentListResponse:
    post = _get_published_post(db, post_id)
    comments, next_cursor = _list_comment_models(db, post.id, cursor=cursor, limit=limit)
    authors = _load_authors(db, [comment.author_id for comment in comments])
    return CommunityCommentListResponse(
        items=[_comment_response(comment, authors[comment.author_id]) for comment in comments],
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
    )


def create_post(
    db: Session,
    *,
    payload: CommunityPostCreateRequest,
    principal: Principal,
) -> CommunityPostDetail:
    _require_publish_access(principal, payload.rules_accepted)
    post = CommunityPost(
        board_code=payload.board_code,
        author_id=principal.user.id,
        title=payload.title,
        content=payload.content,
    )
    db.add(post)
    db.flush()
    _sync_mention_notifications(
        db,
        text=f"{post.title}\n{post.content}",
        actor_id=principal.user.id,
        source_type=CommunityNotificationSource.POST,
        source_id=post.id,
        post_id=post.id,
        comment_id=None,
    )
    db.commit()
    db.refresh(post)
    return get_post(db, post.id)



def update_post(
    db: Session,
    *,
    post_id: str,
    payload: CommunityPostUpdateRequest,
    principal: Principal,
    context: ClientContext,
) -> CommunityPostDetail:
    _require_publish_access(principal, payload.rules_accepted)
    post = _get_published_post(db, post_id)
    _require_author(post.author_id, principal.user.id)
    _require_version(post.version, payload.expected_version)
    now = utc_now()
    db.add(
        CommunityPostRevision(
            post_id=post.id,
            editor_id=principal.user.id,
            version=post.version,
            title_snapshot=post.title,
            content_snapshot=post.content,
            reason="author_edit",
        )
    )
    post.title = payload.title
    post.content = payload.content
    previous_version = post.version
    post.version += 1
    post.edited_at = now
    post.last_activity_at = now
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.post.update",
        target_type="community_post",
        target_id=post.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"previous_version": previous_version, "current_version": post.version},
    )
    _sync_mention_notifications(
        db,
        text=f"{post.title}\n{post.content}",
        actor_id=principal.user.id,
        source_type=CommunityNotificationSource.POST,
        source_id=post.id,
        post_id=post.id,
        comment_id=None,
    )
    db.commit()
    return get_post(db, post.id)


def delete_post(
    db: Session,
    *,
    post_id: str,
    expected_version: int,
    principal: Principal,
    context: ClientContext,
) -> CommunityPostDetail:
    post = _get_published_post(db, post_id)
    _require_author(post.author_id, principal.user.id)
    _require_version(post.version, expected_version)
    now = utc_now()
    db.add(
        CommunityPostRevision(
            post_id=post.id,
            editor_id=principal.user.id,
            version=post.version,
            title_snapshot=post.title,
            content_snapshot=post.content,
            reason="author_delete",
        )
    )
    post.title = "[主题已由作者删除]"
    post.content = "该主题已由作者删除，原文不再公开展示。"
    post.deleted_by_author_at = now
    post.edited_at = now
    previous_version = post.version
    post.version += 1
    post.last_activity_at = now
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.post.delete_by_author",
        target_type="community_post",
        target_id=post.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"previous_version": previous_version, "current_version": post.version},
    )
    db.commit()
    return get_post(db, post.id)


def create_comment(
    db: Session,
    *,
    post_id: str,
    payload: CommunityCommentCreateRequest,
    principal: Principal,
) -> CommunityPostDetail:
    _require_publish_access(principal, payload.rules_accepted)
    post = db.scalar(
        select(CommunityPost).where(
            CommunityPost.id == post_id,
            CommunityPost.status == CommunityContentStatus.PUBLISHED,
        )
    )
    if post is None:
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
    if post.is_locked:
        raise AppError("community.post_locked", "该主题已锁定，暂不能回复", status_code=409)
    parent = (
        db.scalar(
            select(CommunityComment).where(
                CommunityComment.id == payload.parent_id,
                CommunityComment.post_id == post.id,
                CommunityComment.status == CommunityContentStatus.PUBLISHED,
            )
        )
        if payload.parent_id is not None
        else None
    )
    if payload.parent_id is not None and parent is None:
        raise AppError(
            "community.comment_parent_not_found",
            "被回复的评论不存在",
            status_code=404,
        )
    now = utc_now()
    comment = CommunityComment(
        post_id=post.id,
        author_id=principal.user.id,
        parent_id=payload.parent_id,
        root_id=(parent.root_id or parent.id) if parent is not None else None,
        reply_to_user_id=parent.author_id if parent is not None else None,
        content=payload.content,
    )
    db.add(comment)
    db.flush()
    _sync_mention_notifications(
        db,
        text=comment.content,
        actor_id=principal.user.id,
        source_type=CommunityNotificationSource.COMMENT,
        source_id=comment.id,
        post_id=post.id,
        comment_id=comment.id,
    )
    post.reply_count += 1
    post.last_activity_at = now
    db.commit()
    return get_post(db, post.id)



def update_comment(
    db: Session,
    *,
    comment_id: str,
    payload: CommunityCommentUpdateRequest,
    principal: Principal,
    context: ClientContext,
) -> CommunityPostDetail:
    _require_publish_access(principal, payload.rules_accepted)
    comment = _get_published_comment(db, comment_id)
    _require_author(comment.author_id, principal.user.id)
    _require_version(comment.version, payload.expected_version)
    comment.content = payload.content
    previous_version = comment.version
    comment.version += 1
    comment.edited_at = utc_now()
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.comment.update",
        target_type="community_comment",
        target_id=comment.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"previous_version": previous_version, "current_version": comment.version},
    )
    _sync_mention_notifications(
        db,
        text=comment.content,
        actor_id=principal.user.id,
        source_type=CommunityNotificationSource.COMMENT,
        source_id=comment.id,
        post_id=comment.post_id,
        comment_id=comment.id,
    )
    db.commit()
    return get_post(db, comment.post_id)


def delete_comment(
    db: Session,
    *,
    comment_id: str,
    expected_version: int,
    principal: Principal,
    context: ClientContext,
) -> CommunityPostDetail:
    comment = _get_published_comment(db, comment_id)
    _require_author(comment.author_id, principal.user.id)
    _require_version(comment.version, expected_version)
    if comment.deleted_by_author_at is not None:
        raise AppError(
            "community.comment_already_deleted",
            "该回复已由作者删除",
            status_code=409,
        )
    post = db.get(CommunityPost, comment.post_id)
    if post is None:
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
    comment.content = "该回复已由作者删除，原文不再公开展示。"
    comment.deleted_by_author_at = utc_now()
    previous_version = comment.version
    comment.version += 1
    comment.edited_at = comment.deleted_by_author_at
    post.reply_count = max(0, post.reply_count - 1)
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.comment.delete_by_author",
        target_type="community_comment",
        target_id=comment.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"previous_version": previous_version, "current_version": comment.version},
    )
    db.commit()
    return get_post(db, comment.post_id)


def create_report(
    db: Session,
    *,
    payload: CommunityReportCreateRequest,
    principal: Principal,
) -> CommunityReportResponse:
    if not principal.user.email_verified:
        raise AppError(
            "community.email_verification_required",
            "提交社区举报前需要完成邮箱验证",
            status_code=403,
        )
    post = db.scalar(
        select(CommunityPost).where(
            CommunityPost.id == payload.post_id,
            CommunityPost.status == CommunityContentStatus.PUBLISHED,
        )
    )
    if post is None:
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
    if payload.comment_id is not None:
        comment = db.scalar(
            select(CommunityComment).where(
                CommunityComment.id == payload.comment_id,
                CommunityComment.post_id == post.id,
                CommunityComment.status == CommunityContentStatus.PUBLISHED,
            )
        )
        if comment is None:
            raise AppError(
                "community.comment_not_found",
                "被举报的评论不存在",
                status_code=404,
            )
    duplicate_conditions = [
        CommunityReport.reporter_id == principal.user.id,
        CommunityReport.post_id == post.id,
        CommunityReport.status == CommunityReportStatus.OPEN,
    ]
    if payload.comment_id is None:
        duplicate_conditions.append(CommunityReport.comment_id.is_(None))
    else:
        duplicate_conditions.append(CommunityReport.comment_id == payload.comment_id)
    duplicate = db.scalar(select(CommunityReport).where(*duplicate_conditions))
    if duplicate is not None:
        raise AppError(
            "community.report_already_open",
            "你已提交过该内容的待处理举报",
            status_code=409,
        )
    report = CommunityReport(
        reporter_id=principal.user.id,
        post_id=post.id,
        comment_id=payload.comment_id,
        reason=payload.reason,
        details=payload.details,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return CommunityReportResponse(
        id=report.id,
        post_id=report.post_id,
        comment_id=report.comment_id,
        reason=report.reason,
        status=report.status,
        created_at=report.created_at,
    )



def list_notifications(
    db: Session,
    *,
    principal: Principal,
    cursor: str | None,
    limit: int,
    unread_only: bool,
) -> CommunityNotificationListResponse:
    conditions = [CommunityNotification.recipient_id == principal.user.id]
    if unread_only:
        conditions.append(CommunityNotification.read_at.is_(None))
    if cursor is not None:
        created_at, record_id = _decode_cursor(cursor)
        conditions.append(
            or_(
                CommunityNotification.created_at < created_at,
                (CommunityNotification.created_at == created_at)
                & (CommunityNotification.id < record_id),
            )
        )
    notifications = db.scalars(
        select(CommunityNotification)
        .where(*conditions)
        .order_by(CommunityNotification.created_at.desc(), CommunityNotification.id.desc())
        .limit(limit + 1)
    ).all()
    has_more = len(notifications) > limit
    items = notifications[:limit]
    actors = _load_authors(db, [item.actor_id for item in items])
    unread_count = db.scalar(
        select(func.count(CommunityNotification.id)).where(
            CommunityNotification.recipient_id == principal.user.id,
            CommunityNotification.read_at.is_(None),
        )
    ) or 0
    next_cursor = _encode_cursor(items[-1].created_at, items[-1].id) if has_more and items else None
    return CommunityNotificationListResponse(
        items=[_notification_response(item, actors[item.actor_id]) for item in items],
        unread_count=unread_count,
        next_cursor=next_cursor,
        has_more=has_more,
    )


def mark_notification_read(
    db: Session,
    *,
    notification_id: str,
    principal: Principal,
) -> CommunityNotificationReadResponse:
    notification = db.scalar(
        select(CommunityNotification).where(
            CommunityNotification.id == notification_id,
            CommunityNotification.recipient_id == principal.user.id,
        )
    )
    if notification is None:
        raise AppError("community.notification_not_found", "社区通知不存在", status_code=404)
    if notification.read_at is None:
        notification.read_at = utc_now()
    db.commit()
    return CommunityNotificationReadResponse(
        message="通知已标记为已读",
        unread_count=_unread_notification_count(db, principal.user.id),
    )


def mark_all_notifications_read(
    db: Session,
    *,
    principal: Principal,
) -> CommunityNotificationReadResponse:
    notifications = db.scalars(
        select(CommunityNotification).where(
            CommunityNotification.recipient_id == principal.user.id,
            CommunityNotification.read_at.is_(None),
        )
    ).all()
    now = utc_now()
    for notification in notifications:
        notification.read_at = now
    db.commit()
    return CommunityNotificationReadResponse(message="社区通知已全部标记为已读", unread_count=0)


def _sync_mention_notifications(
    db: Session,
    *,
    text: str,
    actor_id: str,
    source_type: CommunityNotificationSource,
    source_id: str,
    post_id: str,
    comment_id: str | None,
) -> None:
    usernames: list[str] = []
    seen: set[str] = set()
    for match in _MENTION_PATTERN.finditer(text):
        username = match.group(1).lower()
        if username in seen:
            continue
        seen.add(username)
        usernames.append(username)
        if len(usernames) >= _MAX_MENTIONS_PER_CONTENT:
            break
    if not usernames:
        return
    recipients = db.scalars(
        select(User).where(
            func.lower(User.username).in_(usernames),
            User.status == UserStatus.ACTIVE,
            User.id != actor_id,
        )
    ).all()
    if not recipients:
        return
    existing = set(
        db.scalars(
            select(CommunityNotification.recipient_id).where(
                CommunityNotification.kind == CommunityNotificationKind.MENTION,
                CommunityNotification.source_type == source_type,
                CommunityNotification.source_id == source_id,
                CommunityNotification.recipient_id.in_([user.id for user in recipients]),
            )
        ).all()
    )
    preview = _notification_preview(text)
    for recipient in recipients:
        if recipient.id in existing:
            continue
        db.add(
            CommunityNotification(
                recipient_id=recipient.id,
                actor_id=actor_id,
                kind=CommunityNotificationKind.MENTION,
                source_type=source_type,
                source_id=source_id,
                post_id=post_id,
                comment_id=comment_id,
                preview=preview,
            )
        )


def _notification_preview(text: str) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= 180 else f"{compact[:177]}..."


def _notification_response(
    notification: CommunityNotification,
    actor: CommunityAuthor,
) -> CommunityNotificationResponse:
    return CommunityNotificationResponse(
        id=notification.id,
        kind=notification.kind,
        source_type=notification.source_type,
        source_id=notification.source_id,
        post_id=notification.post_id,
        comment_id=notification.comment_id,
        preview=notification.preview,
        actor=actor,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


def _unread_notification_count(db: Session, user_id: str) -> int:
    return db.scalar(
        select(func.count(CommunityNotification.id)).where(
            CommunityNotification.recipient_id == user_id,
            CommunityNotification.read_at.is_(None),
        )
    ) or 0


def _require_publish_access(principal: Principal, rules_accepted: bool) -> None:
    if not principal.user.email_verified:
        raise AppError(
            "community.email_verification_required",
            "发布社区内容前需要完成邮箱验证",
            status_code=403,
        )
    if not rules_accepted:
        raise AppError(
            "community.rules_not_accepted",
            "请先同意社区规则",
            status_code=422,
        )


def _load_authors(db: Session, author_ids: list[str]) -> dict[str, CommunityAuthor]:
    unique_ids = set(author_ids)
    if not unique_ids:
        return {}
    users = db.scalars(select(User).where(User.id.in_(unique_ids))).all()
    return {
        user.id: CommunityAuthor(user_id=user.id, username=user.username, role=user.role)
        for user in users
    }


def _post_summary(post: CommunityPost, author: CommunityAuthor) -> CommunityPostSummary:
    compact = " ".join(post.content.split())
    preview = compact if len(compact) <= 180 else f"{compact[:177]}..."
    return CommunityPostSummary(
        id=post.id,
        board_code=post.board_code,
        title=post.title,
        content_preview=preview,
        author=author,
        is_pinned=post.is_pinned,
        is_locked=post.is_locked,
        reply_count=post.reply_count,
        version=post.version,
        edited_at=post.edited_at,
        last_activity_at=post.last_activity_at,
        created_at=post.created_at,
    )


def _comment_response(
    comment: CommunityComment, author: CommunityAuthor
) -> CommunityCommentResponse:
    return CommunityCommentResponse(
        id=comment.id,
        parent_id=comment.parent_id,
        root_id=comment.root_id,
        reply_to_user_id=comment.reply_to_user_id,
        content=comment.content,
        version=comment.version,
        edited_at=comment.edited_at,
        author=author,
        created_at=comment.created_at,
    )



def _get_published_post(db: Session, post_id: str) -> CommunityPost:
    post = db.scalar(
        select(CommunityPost).where(
            CommunityPost.id == post_id,
            CommunityPost.status == CommunityContentStatus.PUBLISHED,
        )
    )
    if post is None:
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
    return post


def _get_published_comment(db: Session, comment_id: str) -> CommunityComment:
    comment = db.scalar(
        select(CommunityComment).where(
            CommunityComment.id == comment_id,
            CommunityComment.status == CommunityContentStatus.PUBLISHED,
        )
    )
    if comment is None:
        raise AppError("community.comment_not_found", "社区回复不存在", status_code=404)
    return comment


def _require_author(author_id: str, user_id: str) -> None:
    if author_id != user_id:
        raise AppError("community.author_only", "只有作者可以修改或删除该内容", status_code=403)


def _require_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise AppError(
            "community.edit_conflict",
            "内容已被更新，请刷新后再编辑",
            status_code=409,
            details={"expected_version": expected, "current_version": actual},
        )


def _encode_cursor(created_at: datetime, record_id: str) -> str:
    payload = {"created_at": created_at.isoformat(), "id": record_id}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        record_id = str(payload["id"])
        if not record_id:
            raise ValueError
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return created_at, record_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError("community.invalid_cursor", "分页游标无效", status_code=422) from exc


def _list_comment_models(
    db: Session,
    post_id: str,
    *,
    cursor: str | None,
    limit: int,
) -> tuple[list[CommunityComment], str | None]:
    conditions = [
        CommunityComment.post_id == post_id,
        CommunityComment.status == CommunityContentStatus.PUBLISHED,
    ]
    if cursor is not None:
        created_at, record_id = _decode_cursor(cursor)
        conditions.append(
            or_(
                CommunityComment.created_at > created_at,
                (CommunityComment.created_at == created_at)
                & (CommunityComment.id > record_id),
            )
        )
    comments = db.scalars(
        select(CommunityComment)
        .where(*conditions)
        .order_by(CommunityComment.created_at.asc(), CommunityComment.id.asc())
        .limit(limit + 1)
    ).all()
    has_more = len(comments) > limit
    items = comments[:limit]
    next_cursor = _encode_cursor(items[-1].created_at, items[-1].id) if has_more and items else None
    return items, next_cursor


def _post_detail(
    post: CommunityPost,
    authors: dict[str, CommunityAuthor],
    comments: list[CommunityComment],
) -> CommunityPostDetail:
    return CommunityPostDetail(
        id=post.id,
        board_code=post.board_code,
        title=post.title,
        content=post.content,
        author=authors[post.author_id],
        is_pinned=post.is_pinned,
        is_locked=post.is_locked,
        reply_count=post.reply_count,
        version=post.version,
        edited_at=post.edited_at,
        last_activity_at=post.last_activity_at,
        created_at=post.created_at,
        comments=[_comment_response(comment, authors[comment.author_id]) for comment in comments],
    )
