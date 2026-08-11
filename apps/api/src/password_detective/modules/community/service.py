from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityBoardCode,
    CommunityComment,
    CommunityContentStatus,
    CommunityPost,
)
from password_detective.db.models.user import User
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.community.schemas import (
    CommunityAuthor,
    CommunityBoard,
    CommunityBoardListResponse,
    CommunityCommentCreateRequest,
    CommunityCommentResponse,
    CommunityPostCreateRequest,
    CommunityPostDetail,
    CommunityPostListResponse,
    CommunityPostSummary,
)

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
    post = db.scalar(
        select(CommunityPost).where(
            CommunityPost.id == post_id,
            CommunityPost.status == CommunityContentStatus.PUBLISHED,
        )
    )
    if post is None:
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
    comments = db.scalars(
        select(CommunityComment)
        .where(
            CommunityComment.post_id == post.id,
            CommunityComment.status == CommunityContentStatus.PUBLISHED,
        )
        .order_by(CommunityComment.created_at.asc())
        .limit(200)
    ).all()
    authors = _load_authors(
        db,
        [post.author_id, *(comment.author_id for comment in comments)],
    )
    return CommunityPostDetail(
        id=post.id,
        board_code=post.board_code,
        title=post.title,
        content=post.content,
        author=authors[post.author_id],
        is_pinned=post.is_pinned,
        is_locked=post.is_locked,
        reply_count=post.reply_count,
        last_activity_at=post.last_activity_at,
        created_at=post.created_at,
        comments=[_comment_response(comment, authors[comment.author_id]) for comment in comments],
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
    db.commit()
    db.refresh(post)
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
    if payload.parent_id is not None:
        parent = db.scalar(
            select(CommunityComment).where(
                CommunityComment.id == payload.parent_id,
                CommunityComment.post_id == post.id,
                CommunityComment.status == CommunityContentStatus.PUBLISHED,
            )
        )
        if parent is None:
            raise AppError(
                "community.comment_parent_not_found",
                "被回复的评论不存在",
                status_code=404,
            )
    now = utc_now()
    db.add(
        CommunityComment(
            post_id=post.id,
            author_id=principal.user.id,
            parent_id=payload.parent_id,
            content=payload.content,
        )
    )
    post.reply_count += 1
    post.last_activity_at = now
    db.commit()
    return get_post(db, post.id)


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
        user.id: CommunityAuthor(username=user.username, role=user.role)
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
        last_activity_at=post.last_activity_at,
        created_at=post.created_at,
    )


def _comment_response(
    comment: CommunityComment, author: CommunityAuthor
) -> CommunityCommentResponse:
    return CommunityCommentResponse(
        id=comment.id,
        parent_id=comment.parent_id,
        content=comment.content,
        author=author,
        created_at=comment.created_at,
    )
