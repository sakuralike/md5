from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.trust_case import TrustCase, TrustCaseEvent, TrustCaseStatus

SLA_ESCALATION_REASON = "system.sla_overdue"


def escalate_overdue_cases(
    db: Session,
    *,
    now: datetime | None = None,
    batch_size: int = 100,
) -> int:
    observed_at = _as_utc(now or utc_now())
    cases = list(
        db.scalars(
            select(TrustCase)
            .where(
                TrustCase.status.in_([TrustCaseStatus.OPEN, TrustCaseStatus.IN_REVIEW]),
                TrustCase.sla_due_at.is_not(None),
                TrustCase.sla_due_at <= observed_at,
                TrustCase.escalated_at.is_(None),
            )
            .order_by(TrustCase.sla_due_at, TrustCase.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
    )
    for case in cases:
        case.escalated_at = observed_at
        case.escalation_count += 1
        case.last_escalation_reason = SLA_ESCALATION_REASON
        case.version += 1
        event = TrustCaseEvent(
            case_id=case.id,
            actor_id=None,
            previous_status=case.status,
            previous_assignee_id=case.assigned_to_id,
            next_status=case.status,
            next_assignee_id=case.assigned_to_id,
            action="case.sla_escalated",
            reason_code=SLA_ESCALATION_REASON,
            note=None,
            request_id=None,
        )
        db.add(event)
        write_audit_log(
            db,
            action="trust_case.sla.escalate",
            target_type="trust_case",
            target_id=case.id,
            result="success",
            actor_id=None,
            ip_prefix=None,
            request_id=None,
            details={
                "kind": case.kind.value,
                "status": case.status.value,
                "assigned_to_id": case.assigned_to_id,
                "escalation_count": case.escalation_count,
                "reason_code": SLA_ESCALATION_REASON,
            },
        )
    db.commit()
    return len(cases)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
