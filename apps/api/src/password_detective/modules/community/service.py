from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.community import (
    CommunityAvatarKind,
    CommunityBoard,
    CommunityBoardStatus,
    CommunityComment,
    CommunityCommentLike,
    CommunityContentStatus,
    CommunityInteractionPolicy,
    CommunityNotification,
    CommunityNotificationKind,
    CommunityNotificationPreference,
    CommunityNotificationSource,
    CommunityPost,
    CommunityPostBookmark,
    CommunityPostLike,
    CommunityPostRevision,
    CommunityPublicProfile,
    CommunityRelationVisibility,
    CommunityReport,
    CommunityReportStatus,
    CommunityUserBlock,
    CommunityUserFollow,
    CommunityUserMute,
)
from password_detective.db.models.user import User, UserStatus
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.community.activity_service import (
    record_comment_published,
    record_post_published,
    record_user_followed,
)
from password_detective.modules.community.boards import get_board_by_code, require_board_post_access
from password_detective.modules.community.group_service import (
    can_user_view_post,
    group_slug_for_post,
    increment_group_post_count,
    post_visibility_condition,
    require_group_post_access,
    require_post_visible,
    visible_group_model,
)
from password_detective.modules.community.notification_service import (
    create_notification,
    notification_preview,
    sync_like_summary,
)
from password_detective.modules.community.schemas import (
    CommunityAuthor,
    CommunityBoardListResponse,
    CommunityBookmarkItem,
    CommunityBookmarkListResponse,
    CommunityCommentCreateRequest,
    CommunityCommentLikeResponse,
    CommunityCommentListResponse,
    CommunityCommentResponse,
    CommunityCommentUpdateRequest,
    CommunityHomeResponse,
    CommunityMuteRequest,
    CommunityNotificationListResponse,
    CommunityNotificationPreferenceItem,
    CommunityNotificationPreferencesResponse,
    CommunityNotificationPreferencesUpdateRequest,
    CommunityNotificationReadResponse,
    CommunityNotificationResponse,
    CommunityOwnProfileResponse,
    CommunityPostCreateRequest,
    CommunityPostDetail,
    CommunityPostInteractionResponse,
    CommunityPostListResponse,
    CommunityPostSummary,
    CommunityPostUpdateRequest,
    CommunityPrivacyUpdateRequest,
    CommunityProfileStats,
    CommunityProfileUpdateRequest,
    CommunityPublicCommentSummary,
    CommunityPublicLevel,
    CommunityPublicProfileResponse,
    CommunityRelationListResponse,
    CommunityRelationshipMutationResponse,
    CommunityRelationshipState,
    CommunityRelationUser,
    CommunityReportCreateRequest,
    CommunityReportResponse,
)
from password_detective.modules.community.schemas import (
    CommunityBoard as CommunityBoardSchema,
)

_MENTION_PATTERN = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_]{3,32})")
_MAX_MENTIONS_PER_CONTENT = 10


def list_boards(db: Session) -> CommunityBoardListResponse:
    from password_detective.modules.community.boards import ensure_seed_boards

    ensure_seed_boards(db)
    counts = dict(
        db.execute(
            select(CommunityPost.board_id, func.count(CommunityPost.id))
            .where(CommunityPost.status == CommunityContentStatus.PUBLISHED)
            .group_by(CommunityPost.board_id)
        ).all()
    )
    boards = db.scalars(
        select(CommunityBoard)
        .where(CommunityBoard.status == CommunityBoardStatus.ACTIVE)
        .order_by(CommunityBoard.sort_order.asc(), CommunityBoard.created_at.asc())
    ).all()
    return CommunityBoardListResponse(
        items=[
            CommunityBoardSchema(
                code=board.code,
                name=board.name,
                description=board.description,
                sort_order=board.sort_order,
                minimum_role=board.minimum_role,
                status=board.status,
                is_read_only=board.is_read_only,
                post_count=counts.get(board.id, 0),
            )
            for board in boards
        ]
    )


def list_posts(
    db: Session,
    *,
    board_code: str | None,
    group_slug: str | None,
    page: int,
    page_size: int,
    principal: Principal | None = None,
) -> CommunityPostListResponse:
    viewer_id = principal.user.id if principal is not None else None
    conditions = [
        CommunityPost.status == CommunityContentStatus.PUBLISHED,
        post_visibility_condition(viewer_id),
    ]
    hidden_author_ids = _hidden_author_ids(db, principal.user.id if principal is not None else None)
    if hidden_author_ids:
        conditions.append(CommunityPost.author_id.not_in(hidden_author_ids))
    if board_code is not None:
        conditions.append(CommunityPost.board_code == board_code)
    if group_slug is not None:
        group = visible_group_model(db, slug=group_slug, principal=principal)
        conditions.append(CommunityPost.group_id == group.id)
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
        items=[_post_summary(db, post, authors[post.author_id]) for post in posts],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_post(
    db: Session,
    post_id: str,
    *,
    principal: Principal | None = None,
) -> CommunityPostDetail:
    post = _get_published_post(db, post_id)
    require_post_visible(db, post, principal)
    viewer_id = principal.user.id if principal is not None else None
    if post.author_id in _hidden_author_ids(db, viewer_id):
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
    comments = _list_comment_models(
        db,
        post.id,
        cursor=None,
        limit=50,
        hidden_author_ids=_hidden_author_ids(db, viewer_id),
    )[0]
    authors = _load_authors(
        db,
        [post.author_id, *(comment.author_id for comment in comments)],
    )
    liked_comment_ids = _liked_comment_ids(db, viewer_id, comments)
    return _post_detail(
        db,
        post,
        authors,
        comments,
        viewer_has_liked=_has_post_like(db, viewer_id, post.id),
        viewer_has_bookmarked=_has_post_bookmark(db, viewer_id, post.id),
        liked_comment_ids=liked_comment_ids,
    )


def list_home(
    db: Session,
    *,
    board_code: str | None,
    page_size: int,
    principal: Principal | None = None,
) -> CommunityHomeResponse:
    return CommunityHomeResponse(
        boards=list_boards(db).items,
        posts=list_posts(
            db,
            board_code=board_code,
            group_slug=None,
            page=1,
            page_size=page_size,
            principal=principal,
        ),
    )


def list_comments(
    db: Session,
    *,
    post_id: str,
    cursor: str | None,
    limit: int,
    principal: Principal | None = None,
) -> CommunityCommentListResponse:
    post = _get_published_post(db, post_id)
    require_post_visible(db, post, principal)
    viewer_id = principal.user.id if principal is not None else None
    hidden_author_ids = _hidden_author_ids(db, viewer_id)
    if post.author_id in hidden_author_ids:
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
    comments, next_cursor = _list_comment_models(
        db,
        post.id,
        cursor=cursor,
        limit=limit,
        hidden_author_ids=hidden_author_ids,
    )
    authors = _load_authors(db, [comment.author_id for comment in comments])
    liked_comment_ids = _liked_comment_ids(db, viewer_id, comments)
    return CommunityCommentListResponse(
        items=[
            _comment_response(
                comment,
                authors[comment.author_id],
                viewer_has_liked=comment.id in liked_comment_ids,
            )
            for comment in comments
        ],
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
    board = get_board_by_code(db, payload.board_code)
    require_board_post_access(board, principal.user.role)
    group = require_group_post_access(db, payload.group_slug, principal)
    post = CommunityPost(
        board_id=board.id,
        board_code=board.code,
        group_id=group.id if group is not None else None,
        author_id=principal.user.id,
        title=payload.title,
        content=payload.content,
    )
    db.add(post)
    db.flush()
    increment_group_post_count(db, post.group_id, 1)
    record_post_published(db, post)
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
    return get_post(db, post.id, principal=principal)


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
    require_post_visible(db, post, principal)
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
    return get_post(db, post.id, principal=principal)


def delete_post(
    db: Session,
    *,
    post_id: str,
    expected_version: int,
    principal: Principal,
    context: ClientContext,
) -> CommunityPostDetail:
    post = _get_published_post(db, post_id)
    require_post_visible(db, post, principal)
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
    return get_post(db, post.id, principal=principal)


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
    record_comment_published(db, comment, post)
    _sync_mention_notifications(
        db,
        text=comment.content,
        actor_id=principal.user.id,
        source_type=CommunityNotificationSource.COMMENT,
        source_id=comment.id,
        post_id=post.id,
        comment_id=comment.id,
    )
    reply_recipient_id = parent.author_id if parent is not None else post.author_id
    create_notification(
        db,
        recipient_id=reply_recipient_id,
        actor_id=principal.user.id,
        kind=CommunityNotificationKind.REPLY,
        source_type=CommunityNotificationSource.COMMENT,
        source_id=comment.id,
        post_id=post.id,
        comment_id=comment.id,
        preview=comment.content,
    )
    post.reply_count += 1
    post.last_activity_at = now
    db.commit()
    return get_post(db, post.id, principal=principal)


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
    return get_post(db, comment.post_id, principal=principal)


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
    return get_post(db, comment.post_id, principal=principal)


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
    require_post_visible(db, post, principal)
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


def set_post_like(
    db: Session,
    *,
    post_id: str,
    principal: Principal,
    liked: bool,
) -> CommunityPostInteractionResponse:
    post = db.get(CommunityPost, post_id)
    if post is None:
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
    existing = db.scalar(
        select(CommunityPostLike).where(
            CommunityPostLike.user_id == principal.user.id,
            CommunityPostLike.post_id == post.id,
        )
    )
    changed = False
    if liked:
        require_post_visible(db, post, principal)
        if post.status != CommunityContentStatus.PUBLISHED:
            raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
        if existing is None:
            db.add(CommunityPostLike(user_id=principal.user.id, post_id=post.id))
            db.flush()
            changed = True
    elif existing is not None:
        db.delete(existing)
        db.flush()
        changed = True
    post.like_count = _count_post_likes(db, post.id)
    if changed and principal.user.id != post.author_id:
        _sync_post_like_notification(db, post, refresh_unread=liked)
    db.commit()
    return _post_interaction_response(db, post, principal.user.id)


def set_comment_like(
    db: Session,
    *,
    comment_id: str,
    principal: Principal,
    liked: bool,
) -> CommunityCommentLikeResponse:
    comment = db.get(CommunityComment, comment_id)
    if comment is None:
        raise AppError("community.comment_not_found", "社区回复不存在", status_code=404)
    post = db.get(CommunityPost, comment.post_id)
    existing = db.scalar(
        select(CommunityCommentLike).where(
            CommunityCommentLike.user_id == principal.user.id,
            CommunityCommentLike.comment_id == comment.id,
        )
    )
    changed = False
    if liked:
        require_post_visible(db, post, principal)
        if (
            comment.status != CommunityContentStatus.PUBLISHED
            or post is None
            or post.status != CommunityContentStatus.PUBLISHED
        ):
            raise AppError("community.comment_not_found", "社区回复不存在", status_code=404)
        if existing is None:
            db.add(CommunityCommentLike(user_id=principal.user.id, comment_id=comment.id))
            db.flush()
            changed = True
    elif existing is not None:
        db.delete(existing)
        db.flush()
        changed = True
    comment.like_count = _count_comment_likes(db, comment.id)
    if changed and principal.user.id != comment.author_id:
        _sync_comment_like_notification(db, comment, refresh_unread=liked)
    db.commit()
    return CommunityCommentLikeResponse(
        comment_id=comment.id,
        like_count=comment.like_count,
        viewer_has_liked=liked,
    )


def set_post_bookmark(
    db: Session,
    *,
    post_id: str,
    principal: Principal,
    bookmarked: bool,
) -> CommunityPostInteractionResponse:
    post = db.get(CommunityPost, post_id)
    if post is None:
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
    existing = db.scalar(
        select(CommunityPostBookmark).where(
            CommunityPostBookmark.user_id == principal.user.id,
            CommunityPostBookmark.post_id == post.id,
        )
    )
    if bookmarked:
        require_post_visible(db, post, principal)
        if post.status != CommunityContentStatus.PUBLISHED:
            raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
        if existing is None:
            db.add(CommunityPostBookmark(user_id=principal.user.id, post_id=post.id))
    elif existing is not None:
        db.delete(existing)
    db.commit()
    return _post_interaction_response(db, post, principal.user.id)


def list_bookmarks(
    db: Session,
    *,
    principal: Principal,
    cursor: str | None,
    limit: int,
) -> CommunityBookmarkListResponse:
    conditions = [CommunityPostBookmark.user_id == principal.user.id]
    hidden_author_ids = _hidden_author_ids(db, principal.user.id)
    if cursor is not None:
        created_at, record_id = _decode_cursor(cursor)
        conditions.append(
            or_(
                CommunityPostBookmark.created_at < created_at,
                (CommunityPostBookmark.created_at == created_at)
                & (CommunityPostBookmark.id < record_id),
            )
        )
    bookmarks = db.scalars(
        select(CommunityPostBookmark)
        .where(*conditions)
        .order_by(CommunityPostBookmark.created_at.desc(), CommunityPostBookmark.id.desc())
        .limit(limit + 1)
    ).all()
    has_more = len(bookmarks) > limit
    items = bookmarks[:limit]
    post_ids = [bookmark.post_id for bookmark in items]
    posts = (
        db.scalars(
            select(CommunityPost).where(
                CommunityPost.id.in_(post_ids),
                CommunityPost.status == CommunityContentStatus.PUBLISHED,
                post_visibility_condition(principal.user.id),
                CommunityPost.author_id.not_in(hidden_author_ids),
            )
        ).all()
        if post_ids
        else []
    )
    post_by_id = {post.id: post for post in posts}
    authors = _load_authors(db, [post.author_id for post in posts])
    next_cursor = _encode_cursor(items[-1].created_at, items[-1].id) if has_more and items else None
    return CommunityBookmarkListResponse(
        items=[
            CommunityBookmarkItem(
                post_id=bookmark.post_id,
                bookmarked_at=bookmark.created_at,
                post=(
                    _post_summary(
                        db,
                        post_by_id[bookmark.post_id],
                        authors[post_by_id[bookmark.post_id].author_id],
                    )
                    if bookmark.post_id in post_by_id
                    else None
                ),
            )
            for bookmark in items
        ],
        next_cursor=next_cursor,
        has_more=has_more,
    )


def list_notifications(
    db: Session,
    *,
    principal: Principal,
    cursor: str | None,
    limit: int,
    unread_only: bool,
    kind: CommunityNotificationKind | None = None,
) -> CommunityNotificationListResponse:
    conditions = [
        CommunityNotification.recipient_id == principal.user.id,
        _notification_visibility_condition(principal.user.id),
    ]
    if unread_only:
        conditions.append(CommunityNotification.read_at.is_(None))
    if kind is not None:
        conditions.append(CommunityNotification.kind == kind)
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
    unread_count = (
        db.scalar(
            select(func.count(CommunityNotification.id)).where(
                CommunityNotification.recipient_id == principal.user.id,
                CommunityNotification.read_at.is_(None),
                _notification_visibility_condition(principal.user.id),
            )
        )
        or 0
    )
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
    if notification is None or not _notification_is_visible(db, notification, principal.user.id):
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
            _notification_visibility_condition(principal.user.id),
        )
    ).all()
    now = utc_now()
    for notification in notifications:
        notification.read_at = now
    db.commit()
    return CommunityNotificationReadResponse(message="社区通知已全部标记为已读", unread_count=0)


def _hidden_author_ids(db: Session, viewer_id: str | None) -> set[str]:
    if viewer_id is None:
        return set()
    now = utc_now()
    muted_ids = set(
        db.scalars(
            select(CommunityUserMute.muted_user_id).where(
                CommunityUserMute.user_id == viewer_id,
                or_(
                    CommunityUserMute.expires_at.is_(None),
                    CommunityUserMute.expires_at > now,
                ),
            )
        ).all()
    )
    block_rows = db.execute(
        select(CommunityUserBlock.blocker_id, CommunityUserBlock.blocked_id).where(
            or_(
                CommunityUserBlock.blocker_id == viewer_id,
                CommunityUserBlock.blocked_id == viewer_id,
            )
        )
    ).all()
    blocked_ids = {
        blocked_id if blocker_id == viewer_id else blocker_id
        for blocker_id, blocked_id in block_rows
    }
    return muted_ids | blocked_ids


def get_public_profile(
    db: Session,
    *,
    username: str,
    principal: Principal | None = None,
) -> CommunityPublicProfileResponse:
    user = _get_active_user_by_username(db, username)
    viewer_id = principal.user.id if principal is not None else None
    profile = _profile_or_default(db, user)
    relationship = _relationship_state(db, viewer_id=viewer_id, target_id=user.id)
    can_show_content = not (
        relationship.viewer_is_blocking
        or relationship.viewer_is_blocked
        or relationship.viewer_is_muting
    )
    recent_posts: list[CommunityPostSummary] = []
    recent_comments: list[CommunityPublicCommentSummary] = []
    if can_show_content:
        posts = db.scalars(
            select(CommunityPost)
            .where(
                CommunityPost.author_id == user.id,
                CommunityPost.status == CommunityContentStatus.PUBLISHED,
                post_visibility_condition(viewer_id),
            )
            .order_by(CommunityPost.created_at.desc(), CommunityPost.id.desc())
            .limit(10)
        ).all()
        author = _author_from_user(user)
        recent_posts = [_post_summary(db, post, author) for post in posts]
        comments = db.execute(
            select(CommunityComment, CommunityPost.title)
            .join(CommunityPost, CommunityPost.id == CommunityComment.post_id)
            .where(
                CommunityComment.author_id == user.id,
                CommunityComment.status == CommunityContentStatus.PUBLISHED,
                CommunityPost.status == CommunityContentStatus.PUBLISHED,
                post_visibility_condition(viewer_id),
            )
            .order_by(CommunityComment.created_at.desc(), CommunityComment.id.desc())
            .limit(10)
        ).all()
        recent_comments = [
            CommunityPublicCommentSummary(
                id=comment.id,
                post_id=comment.post_id,
                post_title=post_title,
                content_preview=_compact_preview(comment.content, limit=180),
                like_count=comment.like_count,
                created_at=comment.created_at,
            )
            for comment, post_title in comments
        ]
    return _public_profile_response(
        db,
        user=user,
        profile=profile,
        relationship=relationship,
        recent_posts=recent_posts,
        recent_comments=recent_comments,
    )


def get_own_profile(db: Session, *, principal: Principal) -> CommunityOwnProfileResponse:
    user = principal.user
    profile = _profile_or_default(db, user)
    response = _public_profile_response(
        db,
        user=user,
        profile=profile,
        relationship=_relationship_state(db, viewer_id=user.id, target_id=user.id),
        recent_posts=[],
        recent_comments=[],
    )
    return CommunityOwnProfileResponse(
        **response.model_dump(),
        follower_visibility=profile.follower_visibility,
        following_visibility=profile.following_visibility,
        message_policy=profile.message_policy,
        mention_policy=profile.mention_policy,
        gravatar_enabled=profile.gravatar_enabled,
    )


def update_public_profile(
    db: Session,
    *,
    payload: CommunityProfileUpdateRequest,
    principal: Principal,
    context: ClientContext,
) -> CommunityOwnProfileResponse:
    profile = _ensure_profile(db, principal.user)
    profile.display_name = payload.display_name
    profile.bio = payload.bio
    if payload.avatar_kind == CommunityAvatarKind.UPLOAD and not profile.avatar_url:
        raise AppError(
            "community.avatar_upload_required", "请先上传头像图片后再选择上传头像", status_code=422
        )
    if payload.avatar_kind == CommunityAvatarKind.GRAVATAR and not payload.gravatar_enabled:
        raise AppError(
            "community.gravatar_not_enabled",
            "启用 Gravatar 前需要确认公开头像服务",
            status_code=422,
        )
    profile.avatar_kind = payload.avatar_kind
    profile.gravatar_enabled = payload.gravatar_enabled
    if payload.regenerate_avatar:
        profile.avatar_seed = _new_avatar_seed()
        profile.avatar_kind = CommunityAvatarKind.GENERATED
        profile.avatar_url = None
        profile.gravatar_enabled = False
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.profile.updated",
        target_type="community_public_profile",
        target_id=principal.user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "fields": [
                "display_name",
                "bio",
                "avatar_kind",
                "gravatar_enabled",
                *(["avatar_seed"] if payload.regenerate_avatar else []),
            ]
        },
    )
    db.commit()
    return get_own_profile(db, principal=principal)


def set_uploaded_avatar(
    db: Session,
    *,
    avatar_url: str,
    principal: Principal,
    context: ClientContext,
) -> CommunityOwnProfileResponse:
    profile = _ensure_profile(db, principal.user)
    profile.avatar_kind = CommunityAvatarKind.UPLOAD
    profile.avatar_url = avatar_url
    profile.gravatar_enabled = False
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.avatar.uploaded",
        target_type="community_public_profile",
        target_id=principal.user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"avatar_kind": CommunityAvatarKind.UPLOAD.value},
    )
    db.commit()
    return get_own_profile(db, principal=principal)


def update_privacy_preferences(
    db: Session,
    *,
    payload: CommunityPrivacyUpdateRequest,
    principal: Principal,
    context: ClientContext,
) -> CommunityOwnProfileResponse:
    profile = _ensure_profile(db, principal.user)
    profile.follower_visibility = payload.follower_visibility
    profile.following_visibility = payload.following_visibility
    profile.message_policy = payload.message_policy
    profile.mention_policy = payload.mention_policy
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.privacy.updated",
        target_type="community_public_profile",
        target_id=principal.user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "fields": [
                "follower_visibility",
                "following_visibility",
                "message_policy",
                "mention_policy",
            ]
        },
    )
    db.commit()
    return get_own_profile(db, principal=principal)


def set_follow(
    db: Session,
    *,
    username: str,
    followed: bool,
    principal: Principal,
    context: ClientContext,
) -> CommunityRelationshipMutationResponse:
    target = _get_active_user_by_username(db, username)
    _require_other_user(principal.user.id, target.id)
    _require_not_blocked(db, actor_id=principal.user.id, target_id=target.id)
    existing = db.scalar(
        select(CommunityUserFollow).where(
            CommunityUserFollow.follower_id == principal.user.id,
            CommunityUserFollow.followed_id == target.id,
        )
    )
    if followed and existing is None:
        follow = CommunityUserFollow(follower_id=principal.user.id, followed_id=target.id)
        db.add(follow)
        db.flush()
        record_user_followed(db, follow)
        create_notification(
            db,
            recipient_id=target.id,
            actor_id=principal.user.id,
            kind=CommunityNotificationKind.FOLLOW,
            source_type=CommunityNotificationSource.USER,
            source_id=follow.id,
            post_id=None,
            comment_id=None,
            preview=f"{principal.user.username} 关注了你",
        )
    elif not followed and existing is not None:
        db.delete(existing)
    db.flush()
    _rebuild_follow_counts(db, [principal.user.id, target.id])
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.follow.created" if followed else "community.follow.removed",
        target_type="user",
        target_id=target.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={},
    )
    db.commit()
    return CommunityRelationshipMutationResponse(
        username=target.username,
        relationship=_relationship_state(db, viewer_id=principal.user.id, target_id=target.id),
        message="已关注该用户" if followed else "已取消关注该用户",
    )


def set_block(
    db: Session,
    *,
    username: str,
    blocked: bool,
    principal: Principal,
    context: ClientContext,
) -> CommunityRelationshipMutationResponse:
    target = _get_active_user_by_username(db, username)
    _require_other_user(principal.user.id, target.id)
    existing = db.scalar(
        select(CommunityUserBlock).where(
            CommunityUserBlock.blocker_id == principal.user.id,
            CommunityUserBlock.blocked_id == target.id,
        )
    )
    if blocked and existing is None:
        db.add(CommunityUserBlock(blocker_id=principal.user.id, blocked_id=target.id))
        db.execute(
            CommunityUserFollow.__table__.delete().where(
                (
                    (CommunityUserFollow.follower_id == principal.user.id)
                    & (CommunityUserFollow.followed_id == target.id)
                )
                | (
                    (CommunityUserFollow.follower_id == target.id)
                    & (CommunityUserFollow.followed_id == principal.user.id)
                )
            )
        )
    elif not blocked and existing is not None:
        db.delete(existing)
    db.flush()
    _rebuild_follow_counts(db, [principal.user.id, target.id])
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.block.created" if blocked else "community.block.removed",
        target_type="user",
        target_id=target.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"follow_edges_removed": blocked},
    )
    db.commit()
    return CommunityRelationshipMutationResponse(
        username=target.username,
        relationship=_relationship_state(db, viewer_id=principal.user.id, target_id=target.id),
        message="已拉黑该用户并移除双方关注关系" if blocked else "已解除拉黑该用户",
    )


def set_mute(
    db: Session,
    *,
    username: str,
    muted: bool,
    payload: CommunityMuteRequest | None,
    principal: Principal,
    context: ClientContext,
) -> CommunityRelationshipMutationResponse:
    target = _get_active_user_by_username(db, username)
    _require_other_user(principal.user.id, target.id)
    now = utc_now()
    if payload is not None and payload.expires_at is not None and payload.expires_at <= now:
        raise AppError(
            "community.invalid_mute_expiry", "静音截止时间必须晚于当前时间", status_code=422
        )
    existing = db.scalar(
        select(CommunityUserMute).where(
            CommunityUserMute.user_id == principal.user.id,
            CommunityUserMute.muted_user_id == target.id,
        )
    )
    if muted:
        if existing is None:
            db.add(
                CommunityUserMute(
                    user_id=principal.user.id,
                    muted_user_id=target.id,
                    expires_at=payload.expires_at if payload is not None else None,
                )
            )
        else:
            existing.expires_at = payload.expires_at if payload is not None else None
    elif existing is not None:
        db.delete(existing)
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.mute.created" if muted else "community.mute.removed",
        target_type="user",
        target_id=target.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "expires_at": payload.expires_at.isoformat()
            if muted and payload and payload.expires_at
            else None
        },
    )
    db.commit()
    return CommunityRelationshipMutationResponse(
        username=target.username,
        relationship=_relationship_state(db, viewer_id=principal.user.id, target_id=target.id),
        message="已静音该用户；不会改变其访问权限" if muted else "已取消静音该用户",
    )


def list_relationship_users(
    db: Session,
    *,
    username: str,
    direction: str,
    principal: Principal | None,
    cursor: str | None,
    limit: int,
) -> CommunityRelationListResponse:
    target = _get_active_user_by_username(db, username)
    viewer_id = principal.user.id if principal is not None else None
    profile = _profile_or_default(db, target)
    is_self = viewer_id == target.id
    visibility = (
        profile.follower_visibility if direction == "followers" else profile.following_visibility
    )
    if not is_self and visibility != CommunityRelationVisibility.PUBLIC:
        raise AppError(
            "community.relation_list_private", "该用户已将关系列表设为私密", status_code=403
        )
    relation_column = (
        CommunityUserFollow.followed_id
        if direction == "followers"
        else CommunityUserFollow.follower_id
    )
    member_column = (
        CommunityUserFollow.follower_id
        if direction == "followers"
        else CommunityUserFollow.followed_id
    )
    conditions = [relation_column == target.id]
    if cursor is not None:
        created_at, record_id = _decode_cursor(cursor)
        conditions.append(
            or_(
                CommunityUserFollow.created_at < created_at,
                (CommunityUserFollow.created_at == created_at)
                & (CommunityUserFollow.id < record_id),
            )
        )
    relations = db.scalars(
        select(CommunityUserFollow)
        .join(User, User.id == member_column)
        .where(*conditions, User.status == UserStatus.ACTIVE)
        .order_by(CommunityUserFollow.created_at.desc(), CommunityUserFollow.id.desc())
        .limit(limit + 1)
    ).all()
    has_more = len(relations) > limit
    items = relations[:limit]
    users = {
        user.id: user
        for user in db.scalars(
            select(User).where(
                User.id.in_([getattr(item, member_column.key) for item in items]),
                User.status == UserStatus.ACTIVE,
            )
        ).all()
    }
    cards = [
        _relation_user(db, users[getattr(item, member_column.key)])
        for item in items
        if getattr(item, member_column.key) in users
    ]
    next_cursor = _encode_cursor(items[-1].created_at, items[-1].id) if has_more and items else None
    return CommunityRelationListResponse(
        items=cards, next_cursor=next_cursor, has_more=next_cursor is not None
    )


def _get_active_user_by_username(db: Session, username: str) -> User:
    user = db.scalar(
        select(User).where(
            func.lower(User.username) == username.strip().lower(), User.status == UserStatus.ACTIVE
        )
    )
    if user is None:
        raise AppError("community.user_not_found", "社区用户不存在", status_code=404)
    return user


def _profile_or_default(db: Session, user: User) -> CommunityPublicProfile:
    profile = db.get(CommunityPublicProfile, user.id)
    if profile is not None:
        return profile
    return CommunityPublicProfile(
        user_id=user.id,
        display_name=user.username,
        bio="",
        avatar_seed=_default_avatar_seed(user.id),
        avatar_kind=CommunityAvatarKind.GENERATED,
        avatar_url=None,
        gravatar_enabled=False,
        follower_visibility=CommunityRelationVisibility.PUBLIC,
        following_visibility=CommunityRelationVisibility.PUBLIC,
        message_policy=CommunityInteractionPolicy.FOLLOWING,
        mention_policy=CommunityInteractionPolicy.EVERYONE,
        follower_count=_follow_count(db, followed_id=user.id),
        following_count=_follow_count(db, follower_id=user.id),
    )


def _ensure_profile(db: Session, user: User) -> CommunityPublicProfile:
    profile = db.get(CommunityPublicProfile, user.id)
    if profile is None:
        profile = _profile_or_default(db, user)
        db.add(profile)
        db.flush()
    return profile


def _new_avatar_seed() -> str:
    return secrets.token_hex(12)


def _default_avatar_seed(user_id: str) -> str:
    return re.sub("-", "", user_id)[:24].ljust(24, "0")


def _follow_count(
    db: Session, *, follower_id: str | None = None, followed_id: str | None = None
) -> int:
    condition = (
        CommunityUserFollow.follower_id == follower_id
        if follower_id is not None
        else CommunityUserFollow.followed_id == followed_id
    )
    return int(db.scalar(select(func.count(CommunityUserFollow.id)).where(condition)) or 0)


def _rebuild_follow_counts(db: Session, user_ids: list[str]) -> None:
    for user_id in set(user_ids):
        user = db.get(User, user_id)
        if user is None:
            continue
        profile = _ensure_profile(db, user)
        profile.follower_count = _follow_count(db, followed_id=user_id)
        profile.following_count = _follow_count(db, follower_id=user_id)
    db.flush()


def _relationship_state(
    db: Session, *, viewer_id: str | None, target_id: str
) -> CommunityRelationshipState:
    if viewer_id is None:
        return CommunityRelationshipState()
    if viewer_id == target_id:
        return CommunityRelationshipState(viewer_is_self=True)
    now = utc_now()
    return CommunityRelationshipState(
        viewer_is_following=db.scalar(
            select(CommunityUserFollow.id).where(
                CommunityUserFollow.follower_id == viewer_id,
                CommunityUserFollow.followed_id == target_id,
            )
        )
        is not None,
        follows_viewer=db.scalar(
            select(CommunityUserFollow.id).where(
                CommunityUserFollow.follower_id == target_id,
                CommunityUserFollow.followed_id == viewer_id,
            )
        )
        is not None,
        viewer_is_blocking=db.scalar(
            select(CommunityUserBlock.id).where(
                CommunityUserBlock.blocker_id == viewer_id,
                CommunityUserBlock.blocked_id == target_id,
            )
        )
        is not None,
        viewer_is_blocked=db.scalar(
            select(CommunityUserBlock.id).where(
                CommunityUserBlock.blocker_id == target_id,
                CommunityUserBlock.blocked_id == viewer_id,
            )
        )
        is not None,
        viewer_is_muting=db.scalar(
            select(CommunityUserMute.id).where(
                CommunityUserMute.user_id == viewer_id,
                CommunityUserMute.muted_user_id == target_id,
                or_(CommunityUserMute.expires_at.is_(None), CommunityUserMute.expires_at > now),
            )
        )
        is not None,
    )


def _require_other_user(actor_id: str, target_id: str) -> None:
    if actor_id == target_id:
        raise AppError(
            "community.self_relation_not_allowed", "不能对自己执行该关系操作", status_code=422
        )


def _require_not_blocked(db: Session, *, actor_id: str, target_id: str) -> None:
    if (
        db.scalar(
            select(CommunityUserBlock.id).where(
                or_(
                    (CommunityUserBlock.blocker_id == actor_id)
                    & (CommunityUserBlock.blocked_id == target_id),
                    (CommunityUserBlock.blocker_id == target_id)
                    & (CommunityUserBlock.blocked_id == actor_id),
                )
            )
        )
        is not None
    ):
        raise AppError(
            "community.interaction_blocked", "双方存在拉黑关系，无法执行此操作", status_code=403
        )


def _author_from_user(user: User) -> CommunityAuthor:
    return CommunityAuthor(user_id=user.id, username=user.username, role=user.role)


def _public_level(db: Session, user_id: str) -> CommunityPublicLevel:
    from password_detective.modules.reputation.levels import get_user_level_profile

    level = get_user_level_profile(db, user_id=user_id).current
    return CommunityPublicLevel(code=level.code, name=level.name)


def _avatar_url(profile: CommunityPublicProfile, user: User) -> str | None:
    if profile.avatar_kind == CommunityAvatarKind.UPLOAD:
        return profile.avatar_url
    if profile.avatar_kind == CommunityAvatarKind.GRAVATAR and profile.gravatar_enabled:
        normalized_email = user.email.strip().lower().encode("utf-8")
        digest = hashlib.md5(normalized_email, usedforsecurity=False).hexdigest()
        return f"https://www.gravatar.com/avatar/{digest}?d=identicon&r=g&s=256"
    return None


def _public_profile_response(
    db: Session,
    *,
    user: User,
    profile: CommunityPublicProfile,
    relationship: CommunityRelationshipState,
    recent_posts: list[CommunityPostSummary],
    recent_comments: list[CommunityPublicCommentSummary],
) -> CommunityPublicProfileResponse:
    return CommunityPublicProfileResponse(
        username=user.username,
        display_name=profile.display_name,
        bio=profile.bio,
        avatar_seed=profile.avatar_seed,
        avatar_kind=profile.avatar_kind,
        avatar_url=_avatar_url(profile, user),
        role=user.role,
        level=_public_level(db, user.id),
        registered_month=user.created_at.strftime("%Y-%m"),
        stats=CommunityProfileStats(
            post_count=int(
                db.scalar(
                    select(func.count(CommunityPost.id)).where(
                        CommunityPost.author_id == user.id,
                        CommunityPost.status == CommunityContentStatus.PUBLISHED,
                    )
                )
                or 0
            ),
            comment_count=int(
                db.scalar(
                    select(func.count(CommunityComment.id)).where(
                        CommunityComment.author_id == user.id,
                        CommunityComment.status == CommunityContentStatus.PUBLISHED,
                    )
                )
                or 0
            ),
            follower_count=profile.follower_count,
            following_count=profile.following_count,
        ),
        relationship=relationship,
        recent_posts=recent_posts,
        recent_comments=recent_comments,
    )


def _relation_user(db: Session, user: User) -> CommunityRelationUser:
    profile = _profile_or_default(db, user)
    return CommunityRelationUser(
        username=user.username,
        display_name=profile.display_name,
        avatar_seed=profile.avatar_seed,
        role=user.role,
        level=_public_level(db, user.id),
    )


def _compact_preview(value: str, *, limit: int) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else f"{compact[: limit - 3]}..."


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
    recipients = [
        recipient
        for recipient in recipients
        if _mention_allowed(db, actor_id=actor_id, recipient_id=recipient.id)
        and can_user_view_post(
            db,
            db.get(CommunityPost, post_id),
            recipient.id,
        )
    ]
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
    preview = notification_preview(text)
    for recipient in recipients:
        if recipient.id in existing:
            continue
        create_notification(
            db,
            recipient_id=recipient.id,
            actor_id=actor_id,
            kind=CommunityNotificationKind.MENTION,
            source_type=source_type,
            source_id=source_id,
            post_id=post_id,
            comment_id=comment_id,
            preview=preview,
        )


def get_notification_preferences(
    db: Session, *, principal: Principal
) -> CommunityNotificationPreferencesResponse:
    stored = {
        item.kind: item
        for item in db.scalars(
            select(CommunityNotificationPreference).where(
                CommunityNotificationPreference.user_id == principal.user.id
            )
        ).all()
    }
    return CommunityNotificationPreferencesResponse(
        items=[
            CommunityNotificationPreferenceItem(
                kind=kind,
                in_app_enabled=stored[kind].in_app_enabled if kind in stored else True,
                email_digest_enabled=(
                    stored[kind].email_digest_enabled if kind in stored else False
                ),
            )
            for kind in CommunityNotificationKind
        ]
    )


def update_notification_preferences(
    db: Session,
    *,
    payload: CommunityNotificationPreferencesUpdateRequest,
    principal: Principal,
) -> CommunityNotificationPreferencesResponse:
    kinds = [item.kind for item in payload.items]
    if len(kinds) != len(set(kinds)):
        raise AppError(
            "community.notification_preference_duplicate",
            "通知偏好类型不能重复",
            status_code=422,
        )
    stored = {
        item.kind: item
        for item in db.scalars(
            select(CommunityNotificationPreference).where(
                CommunityNotificationPreference.user_id == principal.user.id,
                CommunityNotificationPreference.kind.in_(kinds),
            )
        ).all()
    }
    for item in payload.items:
        preference = stored.get(item.kind)
        if preference is None:
            preference = CommunityNotificationPreference(user_id=principal.user.id, kind=item.kind)
            db.add(preference)
        preference.in_app_enabled = item.in_app_enabled
        preference.email_digest_enabled = item.email_digest_enabled
    db.commit()
    return get_notification_preferences(db, principal=principal)


def _mention_allowed(db: Session, *, actor_id: str, recipient_id: str) -> bool:
    if (
        db.scalar(
            select(CommunityUserBlock.id).where(
                or_(
                    (CommunityUserBlock.blocker_id == actor_id)
                    & (CommunityUserBlock.blocked_id == recipient_id),
                    (CommunityUserBlock.blocker_id == recipient_id)
                    & (CommunityUserBlock.blocked_id == actor_id),
                )
            )
        )
        is not None
    ):
        return False
    profile = db.get(CommunityPublicProfile, recipient_id)
    policy = profile.mention_policy if profile is not None else CommunityInteractionPolicy.EVERYONE
    if policy == CommunityInteractionPolicy.NOBODY:
        return False
    if policy == CommunityInteractionPolicy.FOLLOWING:
        return (
            db.scalar(
                select(CommunityUserFollow.id).where(
                    CommunityUserFollow.follower_id == recipient_id,
                    CommunityUserFollow.followed_id == actor_id,
                )
            )
            is not None
        )
    return True


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


def _notification_visibility_condition(user_id: str):
    visible_post_ids = select(CommunityPost.id).where(
        CommunityPost.status == CommunityContentStatus.PUBLISHED,
        post_visibility_condition(user_id),
    )
    return or_(
        CommunityNotification.post_id.is_(None),
        CommunityNotification.post_id.in_(visible_post_ids),
    )


def _notification_is_visible(
    db: Session, notification: CommunityNotification, user_id: str
) -> bool:
    if notification.post_id is None:
        return True
    post = db.get(CommunityPost, notification.post_id)
    return (
        post is not None
        and post.status == CommunityContentStatus.PUBLISHED
        and can_user_view_post(db, post, user_id)
    )


def _unread_notification_count(db: Session, user_id: str) -> int:
    return (
        db.scalar(
            select(func.count(CommunityNotification.id)).where(
                CommunityNotification.recipient_id == user_id,
                CommunityNotification.read_at.is_(None),
                _notification_visibility_condition(user_id),
            )
        )
        or 0
    )


def _has_post_like(db: Session, user_id: str | None, post_id: str) -> bool:
    if user_id is None:
        return False
    return (
        db.scalar(
            select(CommunityPostLike.id).where(
                CommunityPostLike.user_id == user_id,
                CommunityPostLike.post_id == post_id,
            )
        )
        is not None
    )


def _has_post_bookmark(db: Session, user_id: str | None, post_id: str) -> bool:
    if user_id is None:
        return False
    return (
        db.scalar(
            select(CommunityPostBookmark.id).where(
                CommunityPostBookmark.user_id == user_id,
                CommunityPostBookmark.post_id == post_id,
            )
        )
        is not None
    )


def _liked_comment_ids(
    db: Session,
    user_id: str | None,
    comments: list[CommunityComment],
) -> set[str]:
    if user_id is None or not comments:
        return set()
    comment_ids = [comment.id for comment in comments]
    return set(
        db.scalars(
            select(CommunityCommentLike.comment_id).where(
                CommunityCommentLike.user_id == user_id,
                CommunityCommentLike.comment_id.in_(comment_ids),
            )
        ).all()
    )


def _sync_post_like_notification(db: Session, post: CommunityPost, *, refresh_unread: bool) -> None:
    latest = db.scalar(
        select(CommunityPostLike)
        .where(
            CommunityPostLike.post_id == post.id,
            CommunityPostLike.user_id != post.author_id,
        )
        .order_by(CommunityPostLike.created_at.desc(), CommunityPostLike.id.desc())
    )
    external_count = (
        db.scalar(
            select(func.count(CommunityPostLike.id)).where(
                CommunityPostLike.post_id == post.id,
                CommunityPostLike.user_id != post.author_id,
            )
        )
        or 0
    )
    sync_like_summary(
        db,
        recipient_id=post.author_id,
        actor_id=latest.user_id if latest is not None else post.author_id,
        source_type=CommunityNotificationSource.POST,
        source_id=post.id,
        post_id=post.id,
        comment_id=None,
        like_count=external_count,
        preview=f"有人赞了你的主题《{post.title}》",
        refresh_unread=refresh_unread,
        create_if_missing=refresh_unread,
    )


def _sync_comment_like_notification(
    db: Session, comment: CommunityComment, *, refresh_unread: bool
) -> None:
    latest = db.scalar(
        select(CommunityCommentLike)
        .where(
            CommunityCommentLike.comment_id == comment.id,
            CommunityCommentLike.user_id != comment.author_id,
        )
        .order_by(CommunityCommentLike.created_at.desc(), CommunityCommentLike.id.desc())
    )
    external_count = (
        db.scalar(
            select(func.count(CommunityCommentLike.id)).where(
                CommunityCommentLike.comment_id == comment.id,
                CommunityCommentLike.user_id != comment.author_id,
            )
        )
        or 0
    )
    sync_like_summary(
        db,
        recipient_id=comment.author_id,
        actor_id=latest.user_id if latest is not None else comment.author_id,
        source_type=CommunityNotificationSource.COMMENT,
        source_id=comment.id,
        post_id=comment.post_id,
        comment_id=comment.id,
        like_count=external_count,
        preview=f"有人赞了你的回复：{notification_preview(comment.content)}",
        refresh_unread=refresh_unread,
        create_if_missing=refresh_unread,
    )


def _count_post_likes(db: Session, post_id: str) -> int:
    return (
        db.scalar(
            select(func.count(CommunityPostLike.id)).where(CommunityPostLike.post_id == post_id)
        )
        or 0
    )


def _count_comment_likes(db: Session, comment_id: str) -> int:
    return (
        db.scalar(
            select(func.count(CommunityCommentLike.id)).where(
                CommunityCommentLike.comment_id == comment_id
            )
        )
        or 0
    )


def _post_interaction_response(
    db: Session,
    post: CommunityPost,
    user_id: str,
) -> CommunityPostInteractionResponse:
    return CommunityPostInteractionResponse(
        post_id=post.id,
        like_count=post.like_count,
        viewer_has_liked=_has_post_like(db, user_id, post.id),
        viewer_has_bookmarked=_has_post_bookmark(db, user_id, post.id),
    )


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


def _post_summary(
    db: Session, post: CommunityPost, author: CommunityAuthor
) -> CommunityPostSummary:
    compact = " ".join(post.content.split())
    preview = compact if len(compact) <= 180 else f"{compact[:177]}..."
    return CommunityPostSummary(
        id=post.id,
        board_code=post.board_code,
        group_slug=group_slug_for_post(db, post.group_id),
        title=post.title,
        content_preview=preview,
        author=author,
        is_pinned=post.is_pinned,
        is_locked=post.is_locked,
        reply_count=post.reply_count,
        like_count=post.like_count,
        version=post.version,
        edited_at=post.edited_at,
        last_activity_at=post.last_activity_at,
        created_at=post.created_at,
    )


def _comment_response(
    comment: CommunityComment,
    author: CommunityAuthor,
    *,
    viewer_has_liked: bool = False,
) -> CommunityCommentResponse:
    return CommunityCommentResponse(
        id=comment.id,
        parent_id=comment.parent_id,
        root_id=comment.root_id,
        reply_to_user_id=comment.reply_to_user_id,
        content=comment.content,
        like_count=comment.like_count,
        viewer_has_liked=viewer_has_liked,
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
    hidden_author_ids: set[str] | None = None,
) -> tuple[list[CommunityComment], str | None]:
    conditions = [
        CommunityComment.post_id == post_id,
        CommunityComment.status == CommunityContentStatus.PUBLISHED,
    ]
    if hidden_author_ids:
        conditions.append(CommunityComment.author_id.not_in(hidden_author_ids))
    if cursor is not None:
        created_at, record_id = _decode_cursor(cursor)
        conditions.append(
            or_(
                CommunityComment.created_at > created_at,
                (CommunityComment.created_at == created_at) & (CommunityComment.id > record_id),
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
    db: Session,
    post: CommunityPost,
    authors: dict[str, CommunityAuthor],
    comments: list[CommunityComment],
    *,
    viewer_has_liked: bool,
    viewer_has_bookmarked: bool,
    liked_comment_ids: set[str],
) -> CommunityPostDetail:
    return CommunityPostDetail(
        id=post.id,
        board_code=post.board_code,
        group_slug=group_slug_for_post(db, post.group_id),
        title=post.title,
        content=post.content,
        author=authors[post.author_id],
        is_pinned=post.is_pinned,
        is_locked=post.is_locked,
        reply_count=post.reply_count,
        like_count=post.like_count,
        viewer_has_liked=viewer_has_liked,
        viewer_has_bookmarked=viewer_has_bookmarked,
        version=post.version,
        edited_at=post.edited_at,
        last_activity_at=post.last_activity_at,
        created_at=post.created_at,
        comments=[
            _comment_response(
                comment,
                authors[comment.author_id],
                viewer_has_liked=comment.id in liked_comment_ids,
            )
            for comment in comments
        ],
    )
