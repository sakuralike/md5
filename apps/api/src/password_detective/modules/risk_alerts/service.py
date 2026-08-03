from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.risk_alert import (
    RiskAlert,
    RiskAlertEvent,
    RiskAlertKind,
    RiskAlertNotification,
    RiskAlertNotificationKind,
    RiskAlertSeverity,
    RiskAlertStatus,
)
from password_detective.db.models.user import User, UserRole, UserStatus
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.risk_alerts.notifications import (
    ACTIVE_RISK_ALERT_SLA_RULE,
    eligible_operator_query,
    queue_risk_alert_notifications,
)
from password_detective.modules.risk_alerts.schemas import (
    RiskAlertAssignmentRequest,
    RiskAlertAssignmentResponse,
    RiskAlertDetail,
    RiskAlertEventResponse,
    RiskAlertListResponse,
    RiskAlertNotificationResponse,
    RiskAlertOperator,
    RiskAlertSlaState,
    RiskAlertSummary,
    RiskAlertTransitionRequest,
    RiskAlertTransitionResponse,
)

_ALLOWED_TRANSITIONS = {
    RiskAlertStatus.OPEN: {RiskAlertStatus.ACKNOWLEDGED, RiskAlertStatus.RESOLVED},
    RiskAlertStatus.ACKNOWLEDGED: {RiskAlertStatus.OPEN, RiskAlertStatus.RESOLVED},
    RiskAlertStatus.RESOLVED: {RiskAlertStatus.OPEN},
}


def list_risk_alerts(
    db: Session,
    *,
    kind: RiskAlertKind | None,
    severity: RiskAlertSeverity | None,
    status: RiskAlertStatus | None,
    assigned_to_id: str | None,
    overdue: bool | None,
    query: str | None,
    page: int,
    page_size: int,
) -> RiskAlertListResponse:
    filters = []
    if kind is not None:
        filters.append(RiskAlert.kind == kind)
    if severity is not None:
        filters.append(RiskAlert.severity == severity)
    if status is not None:
        filters.append(RiskAlert.status == status)
    if assigned_to_id is not None:
        filters.append(RiskAlert.assigned_to_id == assigned_to_id)
    now = utc_now()
    overdue_filter = or_(
        and_(RiskAlert.status == RiskAlertStatus.OPEN, RiskAlert.acknowledge_due_at < now),
        and_(
            RiskAlert.status == RiskAlertStatus.ACKNOWLEDGED,
            RiskAlert.resolve_due_at < now,
        ),
    )
    if overdue is True:
        filters.append(overdue_filter)
    elif overdue is False:
        filters.append(~overdue_filter)
    normalized_query = query.strip() if query else None
    if normalized_query:
        filters.append(
            or_(RiskAlert.id == normalized_query, RiskAlert.candidate_id == normalized_query)
        )
    total = db.scalar(select(func.count(RiskAlert.id)).where(*filters)) or 0
    alerts = list(
        db.scalars(
            select(RiskAlert)
            .options(selectinload(RiskAlert.assigned_to))
            .where(*filters)
            .order_by(RiskAlert.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return RiskAlertListResponse(
        items=[_summary(alert, now=now) for alert in alerts],
        page=page,
        page_size=page_size,
        total=total,
    )


def list_risk_alert_operators(db: Session) -> list[RiskAlertOperator]:
    operators = list(db.scalars(eligible_operator_query().order_by(User.username)))
    return [
        RiskAlertOperator(id=operator.id, username=operator.username, role=operator.role)
        for operator in operators
    ]


def get_risk_alert_detail(db: Session, alert_id: str) -> RiskAlertDetail:
    alert = db.scalar(
        select(RiskAlert)
        .options(
            selectinload(RiskAlert.assigned_to),
            selectinload(RiskAlert.events),
            selectinload(RiskAlert.notifications).selectinload(RiskAlertNotification.recipient),
        )
        .where(RiskAlert.id == alert_id)
    )
    if alert is None:
        raise AppError("risk_alert.not_found", "未找到风险告警", status_code=404)
    return RiskAlertDetail(
        **_summary(alert).model_dump(),
        events=[_event(event) for event in alert.events],
        notifications=[_notification(notification) for notification in alert.notifications],
    )


def assign_risk_alert(
    db: Session,
    *,
    alert_id: str,
    payload: RiskAlertAssignmentRequest,
    principal: Principal,
    context: ClientContext,
) -> RiskAlertAssignmentResponse:
    alert = db.scalar(select(RiskAlert).where(RiskAlert.id == alert_id).with_for_update())
    if alert is None:
        raise AppError("risk_alert.not_found", "未找到风险告警", status_code=404)
    if alert.status == RiskAlertStatus.RESOLVED:
        raise AppError("risk_alert.assignment_closed", "已解决告警不能重新分派", status_code=409)
    assignee = db.get(User, payload.assignee_id)
    if (
        assignee is None
        or assignee.status != UserStatus.ACTIVE
        or assignee.role not in {UserRole.MODERATOR, UserRole.ADMIN}
        or not assignee.totp_enabled
    ):
        raise AppError("risk_alert.invalid_assignee", "值班处理人不可用", status_code=422)
    previous_assignee_id = alert.assigned_to_id
    if previous_assignee_id == assignee.id:
        raise AppError("risk_alert.noop_assignment", "告警已分派给该处理人", status_code=409)

    alert.assigned_to_id = assignee.id
    alert.updated_at = utc_now()
    event = RiskAlertEvent(
        alert_id=alert.id,
        actor_id=principal.user.id,
        previous_status=alert.status,
        next_status=alert.status,
        previous_assignee_id=previous_assignee_id,
        next_assignee_id=assignee.id,
        action="risk_alert.assigned",
        reason_code="admin.assigned",
        note=payload.assignment_note,
        request_id=context.request_id,
    )
    db.add(event)
    db.flush()
    queue_risk_alert_notifications(
        db,
        alert=alert,
        event=event,
        kind=RiskAlertNotificationKind.ASSIGNED,
        recipient_ids=[assignee.id],
    )
    write_audit_log(
        db,
        action="risk_alert.assign",
        target_type="risk_alert",
        target_id=alert.id,
        result="success",
        actor_id=principal.user.id,
        ip_prefix=None,
        request_id=context.request_id,
        details={
            "candidate_id": alert.candidate_id,
            "previous_assignee_id": previous_assignee_id,
            "current_assignee_id": assignee.id,
            "event_id": event.id,
        },
    )
    db.commit()
    return RiskAlertAssignmentResponse(
        alert_id=alert.id,
        previous_assignee_id=previous_assignee_id,
        current_assignee_id=assignee.id,
        event_id=event.id,
        request_id=context.request_id,
    )


def transition_risk_alert(
    db: Session,
    *,
    alert_id: str,
    payload: RiskAlertTransitionRequest,
    principal: Principal,
    context: ClientContext,
) -> RiskAlertTransitionResponse:
    alert = db.scalar(select(RiskAlert).where(RiskAlert.id == alert_id).with_for_update())
    if alert is None:
        raise AppError("risk_alert.not_found", "未找到风险告警", status_code=404)
    previous_status = alert.status
    previous_assignee_id = alert.assigned_to_id
    if payload.target_status == previous_status:
        raise AppError("risk_alert.noop_transition", "告警状态没有变化", status_code=409)
    if payload.target_status not in _ALLOWED_TRANSITIONS[previous_status]:
        raise AppError("risk_alert.invalid_transition", "不允许执行该告警状态转换", status_code=409)

    now = utc_now()
    alert.status = payload.target_status
    alert.updated_at = now
    notification_kind: RiskAlertNotificationKind | None = None
    notification_recipients: list[str] | None = None
    if payload.target_status == RiskAlertStatus.ACKNOWLEDGED:
        alert.assigned_to_id = alert.assigned_to_id or principal.user.id
        alert.acknowledged_at = alert.acknowledged_at or now
        alert.resolved_by_id = None
        alert.resolution_code = None
        alert.resolution_note = None
        alert.resolved_at = None
        if previous_assignee_id is None:
            notification_kind = RiskAlertNotificationKind.ASSIGNED
            notification_recipients = [alert.assigned_to_id]
    elif payload.target_status == RiskAlertStatus.RESOLVED:
        alert.assigned_to_id = alert.assigned_to_id or principal.user.id
        alert.resolved_by_id = principal.user.id
        alert.resolution_code = payload.resolution_code.value
        alert.resolution_note = payload.resolution_note
        alert.resolved_at = now
        notification_kind = RiskAlertNotificationKind.RESOLVED
        notification_recipients = [alert.assigned_to_id]
    else:
        alert.assigned_to_id = None
        alert.acknowledged_at = None
        alert.resolved_by_id = None
        alert.resolution_code = None
        alert.resolution_note = None
        alert.resolved_at = None
        alert.sla_rule_version = ACTIVE_RISK_ALERT_SLA_RULE.version
        alert.acknowledge_due_at = now + timedelta(
            minutes=ACTIVE_RISK_ALERT_SLA_RULE.acknowledge_minutes
        )
        alert.resolve_due_at = now + timedelta(minutes=ACTIVE_RISK_ALERT_SLA_RULE.resolve_minutes)
        notification_kind = RiskAlertNotificationKind.REOPENED

    event = RiskAlertEvent(
        alert_id=alert.id,
        actor_id=principal.user.id,
        previous_status=previous_status,
        next_status=payload.target_status,
        previous_assignee_id=previous_assignee_id,
        next_assignee_id=alert.assigned_to_id,
        action="risk_alert.transitioned",
        reason_code=payload.resolution_code.value,
        note=payload.resolution_note,
        request_id=context.request_id,
    )
    db.add(event)
    db.flush()
    if notification_kind is not None:
        queue_risk_alert_notifications(
            db,
            alert=alert,
            event=event,
            kind=notification_kind,
            recipient_ids=notification_recipients,
        )
    write_audit_log(
        db,
        action="risk_alert.transition",
        target_type="risk_alert",
        target_id=alert.id,
        result="success",
        actor_id=principal.user.id,
        ip_prefix=None,
        request_id=context.request_id,
        details={
            "candidate_id": alert.candidate_id,
            "kind": alert.kind.value,
            "severity": alert.severity.value,
            "previous_status": previous_status.value,
            "current_status": payload.target_status.value,
            "previous_assignee_id": previous_assignee_id,
            "current_assignee_id": alert.assigned_to_id,
            "resolution_code": payload.resolution_code.value,
            "event_id": event.id,
            "independent_failure_count": alert.independent_failure_count,
            "failure_weight": alert.failure_weight,
            "sla_state": _sla_state(alert, now=now).value,
        },
    )
    db.commit()
    return RiskAlertTransitionResponse(
        alert_id=alert.id,
        previous_status=previous_status,
        current_status=alert.status,
        event_id=event.id,
        resolution_code=payload.resolution_code,
        request_id=context.request_id,
    )


def _summary(alert: RiskAlert, *, now: datetime | None = None) -> RiskAlertSummary:
    return RiskAlertSummary(
        id=alert.id,
        candidate_id=alert.candidate_id,
        trigger_evidence_id=alert.trigger_evidence_id,
        kind=alert.kind,
        severity=alert.severity,
        status=alert.status,
        rule_version=alert.rule_version,
        sla_rule_version=alert.sla_rule_version,
        sla_state=_sla_state(alert, now=now),
        window_started_at=alert.window_started_at,
        window_ended_at=alert.window_ended_at,
        acknowledge_due_at=alert.acknowledge_due_at,
        resolve_due_at=alert.resolve_due_at,
        acknowledged_at=alert.acknowledged_at,
        independent_failure_count=alert.independent_failure_count,
        failure_weight=round(alert.failure_weight, 3),
        assigned_to_id=alert.assigned_to_id,
        assigned_to_username=alert.assigned_to.username if alert.assigned_to else None,
        resolved_by_id=alert.resolved_by_id,
        resolution_code=alert.resolution_code,
        resolution_note=alert.resolution_note,
        resolved_at=alert.resolved_at,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


def _event(event: RiskAlertEvent) -> RiskAlertEventResponse:
    return RiskAlertEventResponse(
        id=event.id,
        actor_id=event.actor_id,
        previous_status=event.previous_status,
        next_status=event.next_status,
        previous_assignee_id=event.previous_assignee_id,
        next_assignee_id=event.next_assignee_id,
        action=event.action,
        reason_code=event.reason_code,
        note=event.note,
        request_id=event.request_id,
        created_at=event.created_at,
    )


def _notification(notification: RiskAlertNotification) -> RiskAlertNotificationResponse:
    return RiskAlertNotificationResponse(
        id=notification.id,
        recipient_user_id=notification.recipient_user_id,
        recipient_username=notification.recipient.username,
        kind=notification.kind,
        status=notification.status,
        attempts=notification.attempts,
        available_at=notification.available_at,
        sent_at=notification.sent_at,
        last_error_code=notification.last_error_code,
        created_at=notification.created_at,
    )


def _sla_state(alert: RiskAlert, *, now: datetime | None = None) -> RiskAlertSlaState:
    observed_at = _as_utc(now or utc_now())
    acknowledge_due_at = _as_utc(alert.acknowledge_due_at)
    resolve_due_at = _as_utc(alert.resolve_due_at)
    if alert.status == RiskAlertStatus.OPEN:
        return (
            RiskAlertSlaState.ACKNOWLEDGEMENT_OVERDUE
            if observed_at > acknowledge_due_at
            else RiskAlertSlaState.WITHIN_SLA
        )
    if alert.status == RiskAlertStatus.ACKNOWLEDGED:
        return (
            RiskAlertSlaState.RESOLUTION_OVERDUE
            if observed_at > resolve_due_at
            else RiskAlertSlaState.WITHIN_SLA
        )
    effective_acknowledged_at = alert.acknowledged_at or alert.resolved_at
    ack_breached = (
        effective_acknowledged_at is None or _as_utc(effective_acknowledged_at) > acknowledge_due_at
    )
    resolution_breached = alert.resolved_at is None or _as_utc(alert.resolved_at) > resolve_due_at
    return (
        RiskAlertSlaState.BREACHED if ack_breached or resolution_breached else RiskAlertSlaState.MET
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
