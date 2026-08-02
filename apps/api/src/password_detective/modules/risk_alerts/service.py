from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.risk_alert import (
    RiskAlert,
    RiskAlertEvent,
    RiskAlertKind,
    RiskAlertSeverity,
    RiskAlertStatus,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.risk_alerts.schemas import (
    RiskAlertDetail,
    RiskAlertEventResponse,
    RiskAlertListResponse,
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
    normalized_query = query.strip() if query else None
    if normalized_query:
        filters.append(
            or_(RiskAlert.id == normalized_query, RiskAlert.candidate_id == normalized_query)
        )
    total = db.scalar(select(func.count(RiskAlert.id)).where(*filters)) or 0
    alerts = list(
        db.scalars(
            select(RiskAlert)
            .where(*filters)
            .order_by(RiskAlert.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return RiskAlertListResponse(
        items=[_summary(alert) for alert in alerts],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_risk_alert_detail(db: Session, alert_id: str) -> RiskAlertDetail:
    alert = db.scalar(
        select(RiskAlert)
        .options(selectinload(RiskAlert.events))
        .where(RiskAlert.id == alert_id)
    )
    if alert is None:
        raise AppError("risk_alert.not_found", "未找到风险告警", status_code=404)
    return RiskAlertDetail(
        **_summary(alert).model_dump(),
        events=[_event(event) for event in alert.events],
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
    if payload.target_status == previous_status:
        raise AppError("risk_alert.noop_transition", "告警状态没有变化", status_code=409)
    if payload.target_status not in _ALLOWED_TRANSITIONS[previous_status]:
        raise AppError("risk_alert.invalid_transition", "不允许执行该告警状态转换", status_code=409)

    now = utc_now()
    alert.status = payload.target_status
    alert.updated_at = now
    if payload.target_status == RiskAlertStatus.ACKNOWLEDGED:
        alert.assigned_to_id = principal.user.id
        alert.resolved_by_id = None
        alert.resolution_code = None
        alert.resolution_note = None
        alert.resolved_at = None
    elif payload.target_status == RiskAlertStatus.RESOLVED:
        alert.assigned_to_id = alert.assigned_to_id or principal.user.id
        alert.resolved_by_id = principal.user.id
        alert.resolution_code = payload.resolution_code.value
        alert.resolution_note = payload.resolution_note
        alert.resolved_at = now
    else:
        alert.assigned_to_id = None
        alert.resolved_by_id = None
        alert.resolution_code = None
        alert.resolution_note = None
        alert.resolved_at = None

    event = RiskAlertEvent(
        alert_id=alert.id,
        actor_id=principal.user.id,
        previous_status=previous_status,
        next_status=payload.target_status,
        action="risk_alert.transitioned",
        reason_code=payload.resolution_code.value,
        note=payload.resolution_note,
        request_id=context.request_id,
    )
    db.add(event)
    db.flush()
    write_audit_log(
        db,
        action="risk_alert.transition",
        target_type="risk_alert",
        target_id=alert.id,
        result="success",
        actor_id=principal.user.id,
        # Risk-alert audits deliberately omit network correlation data.
        ip_prefix=None,
        request_id=context.request_id,
        details={
            "candidate_id": alert.candidate_id,
            "kind": alert.kind.value,
            "severity": alert.severity.value,
            "previous_status": previous_status.value,
            "current_status": payload.target_status.value,
            "resolution_code": payload.resolution_code.value,
            "event_id": event.id,
            "independent_failure_count": alert.independent_failure_count,
            "failure_weight": alert.failure_weight,
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


def _summary(alert: RiskAlert) -> RiskAlertSummary:
    return RiskAlertSummary(
        id=alert.id,
        candidate_id=alert.candidate_id,
        trigger_evidence_id=alert.trigger_evidence_id,
        kind=alert.kind,
        severity=alert.severity,
        status=alert.status,
        rule_version=alert.rule_version,
        window_started_at=alert.window_started_at,
        window_ended_at=alert.window_ended_at,
        independent_failure_count=alert.independent_failure_count,
        failure_weight=round(alert.failure_weight, 3),
        assigned_to_id=alert.assigned_to_id,
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
        action=event.action,
        reason_code=event.reason_code,
        note=event.note,
        request_id=event.request_id,
        created_at=event.created_at,
    )
