from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.community import (
    CommunityComment,
    CommunityContentStatus,
    CommunityModerationAction,
    CommunityPost,
    CommunityReport,
    CommunityReportDecision,
    CommunityReportStatus,
)
from password_detective.db.models.user import User
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.community.admin_schemas import (
    AdminCommunityPostModerateRequest,
    AdminCommunityPostMutationResponse,
    AdminCommunityPostState,
    AdminCommunityReportListResponse,
    AdminCommunityReportMutationResponse,
    AdminCommunityReportResolveRequest,
    AdminCommunityReportSummary,
)


def list_admin_reports(
    db: Session,
    *,
    status: CommunityReportStatus | None,
    page: int,
    page_size: int,
) -> AdminCommunityReportListResponse:
    conditions = [] if status is None else [CommunityReport.status == status]
    total = db.scalar(select(func.count(CommunityReport.id)).where(*conditions)) or 0
    reports = db.scalars(
        select(CommunityReport)
        .where(*conditions)
        .order_by(CommunityReport.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AdminCommunityReportListResponse(
        items=[_report_summary(db, report) for report in reports],
        page=page,
        page_size=page_size,
        total=total,
    )


def resolve_admin_report(
    db: Session,
    *,
    report_id: str,
    payload: AdminCommunityReportResolveRequest,
    principal: Principal,
    context: ClientContext,
) -> AdminCommunityReportMutationResponse:
    report = db.get(CommunityReport, report_id)
    if report is None:
        raise AppError("community.report_not_found", "社区举报不存在", status_code=404)
    if report.status != CommunityReportStatus.OPEN:
        raise AppError("community.report_already_resolved", "社区举报已处理", status_code=409)
    post = db.get(CommunityPost, report.post_id)
    if post is None:
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)

    if payload.decision != CommunityReportDecision.DISMISS:
        _remove_reported_content(db, report=report, post=post)
    if payload.decision == CommunityReportDecision.REMOVE_AND_LOCK:
        post.is_locked = True

    report.status = (
        CommunityReportStatus.DISMISSED
        if payload.decision == CommunityReportDecision.DISMISS
        else CommunityReportStatus.RESOLVED
    )
    report.decision = payload.decision
    report.resolved_by_id = principal.user.id
    report.resolution_note = payload.note
    report.resolved_at = utc_now()
    audit = write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.report.resolve",
        target_type="community_report",
        target_id=report.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "decision": payload.decision.value,
            "post_id": report.post_id,
            "comment_id": report.comment_id,
            "note": payload.note,
        },
    )
    db.flush()
    db.commit()
    db.refresh(report)
    db.refresh(post)
    return AdminCommunityReportMutationResponse(
        report=_report_summary(db, report),
        post=_post_state(post),
        audit_id=audit.id,
        request_id=context.request_id,
    )


def moderate_admin_post(
    db: Session,
    *,
    post_id: str,
    payload: AdminCommunityPostModerateRequest,
    principal: Principal,
    context: ClientContext,
) -> AdminCommunityPostMutationResponse:
    post = db.get(CommunityPost, post_id)
    if post is None:
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
    previous = {
        "status": post.status.value,
        "is_locked": post.is_locked,
        "is_pinned": post.is_pinned,
    }
    match payload.action:
        case CommunityModerationAction.LOCK:
            post.is_locked = True
        case CommunityModerationAction.UNLOCK:
            post.is_locked = False
        case CommunityModerationAction.PIN:
            if post.status != CommunityContentStatus.PUBLISHED:
                raise AppError(
                    "community.removed_post_cannot_pin",
                    "已移除主题不能置顶",
                    status_code=409,
                )
            post.is_pinned = True
        case CommunityModerationAction.UNPIN:
            post.is_pinned = False
        case CommunityModerationAction.REMOVE:
            post.status = CommunityContentStatus.REMOVED
            post.is_pinned = False
        case CommunityModerationAction.RESTORE:
            post.status = CommunityContentStatus.PUBLISHED
    audit = write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.post.moderate",
        target_type="community_post",
        target_id=post.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "action": payload.action.value,
            "note": payload.note,
            "previous": previous,
            "current": {
                "status": post.status.value,
                "is_locked": post.is_locked,
                "is_pinned": post.is_pinned,
            },
        },
    )
    db.flush()
    db.commit()
    db.refresh(post)
    return AdminCommunityPostMutationResponse(
        post=_post_state(post),
        audit_id=audit.id,
        request_id=context.request_id,
    )


def _remove_reported_content(
    db: Session,
    *,
    report: CommunityReport,
    post: CommunityPost,
) -> None:
    if report.comment_id is None:
        post.status = CommunityContentStatus.REMOVED
        post.is_pinned = False
        return
    comment = db.get(CommunityComment, report.comment_id)
    if comment is None:
        raise AppError("community.comment_not_found", "被举报的评论不存在", status_code=404)
    if comment.status == CommunityContentStatus.PUBLISHED:
        comment.status = CommunityContentStatus.REMOVED
        post.reply_count = max(0, post.reply_count - 1)


def _report_summary(db: Session, report: CommunityReport) -> AdminCommunityReportSummary:
    post = db.get(CommunityPost, report.post_id)
    if post is None:
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
    reporter = db.get(User, report.reporter_id)
    resolver = db.get(User, report.resolved_by_id) if report.resolved_by_id else None
    if report.comment_id:
        comment = db.get(CommunityComment, report.comment_id)
        target_text = comment.content if comment is not None else "评论已不存在"
        target_type = "comment"
    else:
        target_text = post.content
        target_type = "post"
    compact = " ".join(target_text.split())
    excerpt = compact if len(compact) <= 240 else f"{compact[:237]}..."
    return AdminCommunityReportSummary(
        id=report.id,
        reporter_username=reporter.username if reporter else "已注销用户",
        post_id=post.id,
        post_title=post.title,
        comment_id=report.comment_id,
        target_type=target_type,
        target_excerpt=excerpt,
        reason=report.reason,
        details=report.details,
        status=report.status,
        decision=report.decision,
        resolution_note=report.resolution_note,
        resolved_by_username=resolver.username if resolver else None,
        created_at=report.created_at,
        resolved_at=report.resolved_at,
    )


def _post_state(post: CommunityPost) -> AdminCommunityPostState:
    return AdminCommunityPostState(
        id=post.id,
        board_code=post.board_code,
        title=post.title,
        status=post.status,
        is_pinned=post.is_pinned,
        is_locked=post.is_locked,
        reply_count=post.reply_count,
        updated_at=post.updated_at,
    )
