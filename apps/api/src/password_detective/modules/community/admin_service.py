from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.community import (
    CommunityBoard,
    CommunityComment,
    CommunityContentStatus,
    CommunityModerationAction,
    CommunityNotification,
    CommunityNotificationKind,
    CommunityNotificationOutbox,
    CommunityNotificationOutboxStatus,
    CommunityPost,
    CommunityReport,
    CommunityReportDecision,
    CommunityReportStatus,
    CommunitySearchOutbox,
    CommunitySearchOutboxStatus,
    CommunitySearchRebuildRun,
    CommunitySearchSource,
)
from password_detective.db.models.reauthentication_grant import ReauthenticationPurpose
from password_detective.db.models.user import User, UserRole
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.auth.reauthentication import consume_reauthentication_grant
from password_detective.modules.community.admin_schemas import (
    AdminCommunityBoardCreateRequest,
    AdminCommunityBoardListResponse,
    AdminCommunityBoardMutationResponse,
    AdminCommunityBoardResponse,
    AdminCommunityBoardUpdateRequest,
    AdminCommunityNotificationOutboxItem,
    AdminCommunityNotificationOutboxListResponse,
    AdminCommunityNotificationOutboxMetrics,
    AdminCommunityNotificationReplayRequest,
    AdminCommunityNotificationReplayResponse,
    AdminCommunityPostModerateRequest,
    AdminCommunityPostMutationResponse,
    AdminCommunityPostState,
    AdminCommunityReportListResponse,
    AdminCommunityReportMutationResponse,
    AdminCommunityReportResolveRequest,
    AdminCommunityReportSummary,
    AdminCommunitySearchHealthResponse,
    AdminCommunitySearchProviderHealth,
    AdminCommunitySearchRebuildSummary,
)
from password_detective.modules.community.boards import ensure_seed_boards
from password_detective.modules.community.search_index import (
    enqueue_search_event,
    source_document_version,
)
from password_detective.modules.community.search_provider import provider_for_session


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
    enqueue_search_event(
        db,
        source_type=CommunitySearchSource.BOARD,
        source_id=board.id,
        document_version=source_document_version(board),
    )
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
    enqueue_search_event(
        db,
        source_type=CommunitySearchSource.BOARD,
        source_id=board.id,
        document_version=source_document_version(board),
    )
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
    enqueue_search_event(
        db,
        source_type=CommunitySearchSource.POST,
        source_id=post.id,
        document_version=source_document_version(post),
    )
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


def get_admin_search_health(db: Session) -> AdminCommunitySearchHealthResponse:
    now = utc_now()
    counts = {
        status: int(count)
        for status, count in db.execute(
            select(CommunitySearchOutbox.status, func.count(CommunitySearchOutbox.id)).group_by(
                CommunitySearchOutbox.status
            )
        ).all()
    }
    oldest_pending_at = db.scalar(
        select(func.min(CommunitySearchOutbox.created_at)).where(
            CommunitySearchOutbox.status == CommunitySearchOutboxStatus.PENDING
        )
    )
    retry_due_count = int(
        db.scalar(
            select(func.count(CommunitySearchOutbox.id)).where(
                CommunitySearchOutbox.status == CommunitySearchOutboxStatus.FAILED,
                CommunitySearchOutbox.available_at <= now,
            )
        )
        or 0
    )
    last_delivered_at = db.scalar(select(func.max(CommunitySearchOutbox.delivered_at)))
    latest_rebuild = db.scalar(
        select(CommunitySearchRebuildRun).order_by(
            CommunitySearchRebuildRun.created_at.desc(), CommunitySearchRebuildRun.id.desc()
        )
    )
    provider_state = provider_for_session(db).preflight(db)
    return AdminCommunitySearchHealthResponse(
        generated_at=now,
        provider=AdminCommunitySearchProviderHealth(
            mode=provider_state.mode,
            degraded=provider_state.degraded,
        ),
        pending_count=counts.get(CommunitySearchOutboxStatus.PENDING, 0),
        delivered_count=counts.get(CommunitySearchOutboxStatus.DELIVERED, 0),
        failed_count=counts.get(CommunitySearchOutboxStatus.FAILED, 0),
        retry_due_count=retry_due_count,
        oldest_pending_seconds=(
            max(0, int((now - _aware_datetime(oldest_pending_at)).total_seconds()))
            if oldest_pending_at is not None
            else None
        ),
        last_delivered_at=last_delivered_at,
        delivery_latency_buckets=_search_delivery_latency_buckets(db, now=now),
        last_rebuild=(
            AdminCommunitySearchRebuildSummary(
                status=latest_rebuild.status,
                expected_count=latest_rebuild.expected_count,
                indexed_count=latest_rebuild.indexed_count,
                missing_count=latest_rebuild.missing_count,
                extra_count=latest_rebuild.extra_count,
                started_at=latest_rebuild.started_at,
                finished_at=latest_rebuild.finished_at,
            )
            if latest_rebuild is not None
            else None
        ),
    )


def _search_delivery_latency_buckets(db: Session, *, now: datetime) -> dict[str, int]:
    buckets = {
        "under_5_seconds": 0,
        "under_30_seconds": 0,
        "under_5_minutes": 0,
        "over_5_minutes": 0,
    }
    delivered_events = db.execute(
        select(CommunitySearchOutbox.created_at, CommunitySearchOutbox.delivered_at).where(
            CommunitySearchOutbox.status == CommunitySearchOutboxStatus.DELIVERED,
            CommunitySearchOutbox.delivered_at.is_not(None),
            CommunitySearchOutbox.delivered_at >= now - timedelta(hours=24),
        )
    ).all()
    for created_at, delivered_at in delivered_events:
        latency_seconds = max(
            0, int((_aware_datetime(delivered_at) - _aware_datetime(created_at)).total_seconds())
        )
        if latency_seconds <= 5:
            buckets["under_5_seconds"] += 1
        elif latency_seconds <= 30:
            buckets["under_30_seconds"] += 1
        elif latency_seconds <= 300:
            buckets["under_5_minutes"] += 1
        else:
            buckets["over_5_minutes"] += 1
    return buckets


def list_admin_notification_outbox(
    db: Session,
    *,
    status: CommunityNotificationOutboxStatus | None,
    kind: CommunityNotificationKind | None,
    error_code: str | None,
    page: int,
    page_size: int,
) -> AdminCommunityNotificationOutboxListResponse:
    recipient = aliased(User)
    actor = aliased(User)
    replayer = aliased(User)
    conditions = []
    if status is not None:
        conditions.append(CommunityNotificationOutbox.status == status)
    if kind is not None:
        conditions.append(CommunityNotification.kind == kind)
    normalized_error = error_code.replace("\x00", "").strip() if error_code else ""
    if normalized_error:
        conditions.append(CommunityNotificationOutbox.last_error_code == normalized_error)

    total_statement = (
        select(func.count(CommunityNotificationOutbox.id))
        .join(
            CommunityNotification,
            CommunityNotification.id == CommunityNotificationOutbox.notification_id,
        )
        .where(*conditions)
    )
    total = int(db.scalar(total_statement) or 0)
    rows = db.execute(
        select(
            CommunityNotificationOutbox,
            CommunityNotification,
            recipient.username,
            actor.username,
            replayer.username,
        )
        .join(
            CommunityNotification,
            CommunityNotification.id == CommunityNotificationOutbox.notification_id,
        )
        .join(recipient, recipient.id == CommunityNotificationOutbox.recipient_id)
        .join(actor, actor.id == CommunityNotification.actor_id)
        .outerjoin(replayer, replayer.id == CommunityNotificationOutbox.last_replayed_by_id)
        .where(*conditions)
        .order_by(
            CommunityNotificationOutbox.created_at.desc(),
            CommunityNotificationOutbox.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AdminCommunityNotificationOutboxListResponse(
        items=[
            _notification_outbox_item(
                event,
                notification,
                recipient_username,
                actor_username,
                replayer_username,
            )
            for event, notification, recipient_username, actor_username, replayer_username in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_admin_notification_outbox_metrics(
    db: Session,
) -> AdminCommunityNotificationOutboxMetrics:
    now = utc_now()
    counts = {
        item_status: int(count)
        for item_status, count in db.execute(
            select(
                CommunityNotificationOutbox.status, func.count(CommunityNotificationOutbox.id)
            ).group_by(CommunityNotificationOutbox.status)
        ).all()
    }
    failed_last_24_hours = int(
        db.scalar(
            select(func.count(CommunityNotificationOutbox.id)).where(
                CommunityNotificationOutbox.status == CommunityNotificationOutboxStatus.FAILED,
                CommunityNotificationOutbox.failed_at >= now - timedelta(hours=24),
            )
        )
        or 0
    )
    retry_due_count = int(
        db.scalar(
            select(func.count(CommunityNotificationOutbox.id)).where(
                CommunityNotificationOutbox.status == CommunityNotificationOutboxStatus.PENDING,
                CommunityNotificationOutbox.available_at <= now,
            )
        )
        or 0
    )
    oldest_pending_at = db.scalar(
        select(func.min(CommunityNotificationOutbox.created_at)).where(
            CommunityNotificationOutbox.status == CommunityNotificationOutboxStatus.PENDING
        )
    )
    oldest_pending_seconds = (
        max(0, int((now - _aware_datetime(oldest_pending_at)).total_seconds()))
        if oldest_pending_at is not None
        else None
    )
    return AdminCommunityNotificationOutboxMetrics(
        generated_at=now,
        pending_count=counts.get(CommunityNotificationOutboxStatus.PENDING, 0),
        delivered_count=counts.get(CommunityNotificationOutboxStatus.DELIVERED, 0),
        failed_count=counts.get(CommunityNotificationOutboxStatus.FAILED, 0),
        failed_last_24_hours=failed_last_24_hours,
        retry_due_count=retry_due_count,
        oldest_pending_seconds=oldest_pending_seconds,
    )


def replay_admin_notification_outbox(
    db: Session,
    *,
    event_id: str,
    payload: AdminCommunityNotificationReplayRequest,
    principal: Principal,
    context: ClientContext,
) -> AdminCommunityNotificationReplayResponse:
    event = db.scalar(
        select(CommunityNotificationOutbox)
        .where(CommunityNotificationOutbox.id == event_id)
        .with_for_update()
    )
    if event is None:
        raise AppError(
            "community.notification_outbox_not_found",
            "社区通知投递事件不存在",
            status_code=404,
        )
    if event.status != CommunityNotificationOutboxStatus.FAILED:
        raise AppError(
            "community.notification_outbox_not_failed",
            "仅失败的社区通知投递事件可以重放",
            status_code=409,
        )
    notification = db.get(CommunityNotification, event.notification_id)
    if notification is None:
        raise AppError(
            "community.notification_not_found",
            "社区通知不存在，无法重放",
            status_code=409,
        )
    grant = consume_reauthentication_grant(
        db,
        raw_token=payload.reauth_token,
        user_id=principal.user.id,
        session_family_id=principal.session_family_id,
        expected_purpose=ReauthenticationPurpose.ADMIN_COMMUNITY_NOTIFICATION_OPS,
    )
    if not grant.mfa_verified:
        raise AppError(
            "auth.mfa_reauthentication_required",
            "该操作需要完成 MFA 再认证",
            status_code=403,
        )

    recipient = db.get(User, event.recipient_id)
    actor = db.get(User, notification.actor_id)
    previous = {
        "status": event.status.value,
        "attempts": event.attempts,
        "last_error_code": event.last_error_code,
        "failed_at": event.failed_at.isoformat() if event.failed_at else None,
    }
    now = utc_now()
    event.status = CommunityNotificationOutboxStatus.PENDING
    event.attempts = 0
    event.available_at = now
    event.delivered_at = None
    event.failed_at = None
    event.last_error_code = None
    event.replay_count += 1
    event.last_replayed_at = now
    event.last_replayed_by_id = principal.user.id
    audit = write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.notification_outbox.replay",
        target_type="community_notification_outbox",
        target_id=event.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "reason": payload.reason,
            "notification_id": notification.id,
            "notification_kind": notification.kind.value,
            "previous": previous,
            "replay_count": event.replay_count,
        },
    )
    db.flush()
    db.commit()
    db.refresh(event)
    return AdminCommunityNotificationReplayResponse(
        event=_notification_outbox_item(
            event,
            notification,
            recipient.username if recipient else "已注销用户",
            actor.username if actor else "已注销用户",
            principal.user.username,
        ),
        audit_id=audit.id,
        request_id=context.request_id,
    )


def _notification_outbox_item(
    event: CommunityNotificationOutbox,
    notification: CommunityNotification,
    recipient_username: str,
    actor_username: str,
    replayer_username: str | None,
) -> AdminCommunityNotificationOutboxItem:
    return AdminCommunityNotificationOutboxItem(
        id=event.id,
        notification_id=event.notification_id,
        recipient_username=recipient_username,
        actor_username=actor_username,
        kind=notification.kind,
        source_type=notification.source_type,
        status=event.status,
        attempts=event.attempts,
        available_at=event.available_at,
        delivered_at=event.delivered_at,
        failed_at=event.failed_at,
        last_error_code=event.last_error_code,
        replay_count=event.replay_count,
        last_replayed_at=event.last_replayed_at,
        last_replayed_by_username=replayer_username,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def _aware_datetime(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
