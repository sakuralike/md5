from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.time import utc_now
from password_detective.db.models.risk_alert import (
    RiskAlert,
    RiskAlertEvent,
    RiskAlertKind,
    RiskAlertSeverity,
    RiskAlertStatus,
)
from password_detective.db.models.verification import (
    CandidateFeedback,
    FeedbackOutcome,
    VerificationEvidenceEvent,
)
from password_detective.modules.verification.service import summarize_feedbacks


@dataclass(frozen=True)
class FailureSurgeRule:
    version: str = "risk-alert-v1"
    window_minutes: int = 15
    independent_failure_required: int = 3
    failure_weight_required: float = 3.0


ACTIVE_FAILURE_SURGE_RULE = FailureSurgeRule()


def detect_failure_surge(
    db: Session,
    *,
    candidate_id: str,
    trigger_evidence: VerificationEvidenceEvent,
    rule: FailureSurgeRule = ACTIVE_FAILURE_SURGE_RULE,
) -> RiskAlert | None:
    """Create one active aggregate-only alert when independent failures surge."""

    if trigger_evidence.outcome != FeedbackOutcome.FAILURE:
        return None
    active_alert = db.scalar(
        select(RiskAlert).where(
            RiskAlert.candidate_id == candidate_id,
            RiskAlert.kind == RiskAlertKind.FAILURE_SURGE,
            RiskAlert.rule_version == rule.version,
            RiskAlert.status.in_([RiskAlertStatus.OPEN, RiskAlertStatus.ACKNOWLEDGED]),
        )
    )
    if active_alert is not None:
        return active_alert

    now = utc_now()
    cutoff = now - timedelta(minutes=rule.window_minutes)
    feedbacks = list(
        db.scalars(
            select(CandidateFeedback).where(
                CandidateFeedback.candidate_id == candidate_id,
                CandidateFeedback.outcome == FeedbackOutcome.FAILURE,
                CandidateFeedback.updated_at >= cutoff,
            )
        )
    )
    totals = summarize_feedbacks(feedbacks)
    if (
        totals.independent_failure_count < rule.independent_failure_required
        or totals.failure_weight < rule.failure_weight_required
    ):
        return None

    observed_times = [_as_utc(item.updated_at) for item in feedbacks]
    alert = RiskAlert(
        candidate_id=candidate_id,
        trigger_evidence_id=trigger_evidence.id,
        kind=RiskAlertKind.FAILURE_SURGE,
        severity=RiskAlertSeverity.HIGH,
        status=RiskAlertStatus.OPEN,
        rule_version=rule.version,
        window_started_at=min(observed_times) if observed_times else cutoff,
        window_ended_at=now,
        independent_failure_count=totals.independent_failure_count,
        failure_weight=round(totals.failure_weight, 3),
    )
    db.add(alert)
    db.flush()
    db.add(
        RiskAlertEvent(
            alert_id=alert.id,
            actor_id=None,
            previous_status=None,
            next_status=RiskAlertStatus.OPEN,
            action="risk_alert.detected",
            reason_code="detection.failure_surge",
            note=None,
            request_id=None,
        )
    )
    db.flush()
    return alert


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite naive values and timezone-aware production values."""

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
