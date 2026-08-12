from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.community import (
    CommunityBoard,
    CommunityComment,
    CommunityContentStatus,
    CommunityModerationAction,
    CommunityPost,
    CommunityReport,
    CommunityReportDecision,
    CommunityReportStatus,
)
from password_detective.db.models.user import User, UserRole
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.community.admin_schemas import (
    AdminCommunityBoardCreateRequest,
    AdminCommunityBoardListResponse,
    AdminCommunityBoardMutationResponse,
    AdminCommunityBoardResponse,
    AdminCommunityBoardUpdateRequest,
    AdminCommunityPostModerateRequest,
    AdminCommunityPostMutationResponse,
    AdminCommunityPostState,
    AdminCommunityReportListResponse,
    AdminCommunityReportMutationResponse,
    AdminCommunityReportResolveRequest,
    AdminCommunityReportSummary,
)
from password_detective.modules.community.boards import ensure_seed_boards


def list_admin_boards(db: Session) -> AdminCommunityBoardListResponse:
    ensure_seed_boards(db)
    boards = db.scalars(
        select(CommunityBoard).order_by(CommunityBoard.sort_order, CommunityBoard.code)
    ).all()
    return AdminCommunityBoardListResponse(items=[_board_response(db, item) for item in boards])


def create_admin_board(
    db: Session,
    *,
    payload: AdminCommunityBoardCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> AdminCommunityBoardMutationResponse:
    _validate_board_role(payload.minimum_role)
    if db.scalar(select(CommunityBoard.id).where(CommunityBoard.code == payload.code)):
        raise AppError("community.board_code_conflict", "板块代码已存在", status_code=409)
    board = CommunityBoard(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        sort_order=payload.sort_order,
        minimum_role=payload.minimum_role.value,
        is_read_only=payload.is_read_only,
        status=payload.status,
    )
    db.add(board)
    db.flush()
    audit = _audit_board(db, board, principal, context, "community.board.create", None)
    db.commit()
    db.refresh(board)
    return AdminCommunityBoardMutationResponse(
        board=_board_response(db, board), audit_id=audit.id, request_id=context.request_id
    )


def update_admin_board(
    db: Session,
    *,
    board_code: str,
    payload: AdminCommunityBoardUpdateRequest,
    principal: Principal,
    context: ClientContext,
) -> AdminCommunityBoardMutationResponse:
    _validate_board_role(payload.minimum_role)
    board = db.scalar(select(CommunityBoard).where(CommunityBoard.code == board_code))
    if board is None:
        raise AppError("community.board_not_found", "社区板块不存在", status_code=404)
    before = _board_state(board)
    board.name = payload.name
    board.description = payload.description
    board.sort_order = payload.sort_order
    board.minimum_role = payload.minimum_role.value
    board.is_read_only = payload.is_read_only
    board.status = payload.status
    audit = _audit_board(db, board, principal, context, "community.board.update", before)
    db.commit()
    db.refresh(board)
    return AdminCommunityBoardMutationResponse(
        board=_board_response(db, board), audit_id=audit.id, request_id=context.request_id
    )


def _validate_board_role(role: UserRole) -> None:
    if role == UserRole.SERVICE:
        raise AppError(
            "community.board_role_invalid", "服务账号不能作为社区发帖最低角色", status_code=422
        )


def _board_response(db: Session, board: CommunityBoard) -> AdminCommunityBoardResponse:
    count = (
        db.scalar(
            select(func.count(CommunityPost.id)).where(
                CommunityPost.board_id == board.id,
                CommunityPost.status == CommunityContentStatus.PUBLISHED,
            )
        )
        or 0
    )
    return AdminCommunityBoardResponse(
        code=board.code,
        name=board.name,
        description=board.description,
        sort_order=board.sort_order,
        minimum_role=UserRole(board.minimum_role),
        is_read_only=board.is_read_only,
        status=board.status,
        post_count=count,
        created_at=board.created_at,
        updated_at=board.updated_at,
    )


def _board_state(board: CommunityBoard) -> dict[str, object]:
    return {
        "code": board.code,
        "name": board.name,
        "description": board.description,
        "sort_order": board.sort_order,
        "minimum_role": board.minimum_role,
        "is_read_only": board.is_read_only,
        "status": board.status.value,
    }


def _audit_board(
    db: Session,
    board: CommunityBoard,
    principal: Principal,
    context: ClientContext,
    action: str,
    before: dict[str, object] | None,
):
    return write_audit_log(
        db,
        actor_id=principal.user.id,
        action=action,
        target_type="community_board",
        target_id=board.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"before": before, "after": _board_state(board)},
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
        was_counted_as_public_reply = comment.deleted_by_author_at is None
        comment.status = CommunityContentStatus.REMOVED
        if was_counted_as_public_reply:
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
