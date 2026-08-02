from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from password_detective.core.time import utc_now
from password_detective.db.models.password_candidate import CandidateStatus
from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.reputation_event import ReputationEvent
from password_detective.db.models.reward_adjustment_event import (
    RewardAdjustmentDirection,
    RewardAdjustmentEvent,
    RewardKind,
)
from password_detective.db.models.submission import Submission
from password_detective.db.models.verification import CandidateFeedback
from password_detective.modules.reputation.service import apply_reputation_event

REWARD_COMPENSATION_RULE_VERSION = "reward-compensation-v1"


@dataclass(frozen=True)
class RewardAdjustmentSummary:
    direction: RewardAdjustmentDirection | None = None
    affected_users: int = 0
    points_entries: int = 0
    reputation_events: int = 0
    points_amount: int = 0
    reputation_amount: int = 0


@dataclass(frozen=True)
class _RewardSource:
    user_id: str
    reward_kind: RewardKind
    reference_id: str
    original_points: int
    original_reputation: int
    has_reputation_event: bool


def reconcile_candidate_rewards(
    db: Session,
    *,
    candidate_id: str,
    state_event_id: str,
    target_status: CandidateStatus,
) -> RewardAdjustmentSummary:
    """Append compensation/restoration events until candidate rewards match its state."""

    existing = list(
        db.scalars(
            select(RewardAdjustmentEvent).where(
                RewardAdjustmentEvent.state_event_id == state_event_id
            )
        )
    )
    if existing:
        return _summarize(existing)

    direction = (
        RewardAdjustmentDirection.RESTORE
        if target_status == CandidateStatus.VERIFIED
        else RewardAdjustmentDirection.INVALIDATE
    )
    desired_multiplier = 1 if target_status == CandidateStatus.VERIFIED else 0
    created: list[RewardAdjustmentEvent] = []
    now = utc_now()

    for source in _candidate_reward_sources(db, candidate_id):
        prior_points, prior_reputation = db.execute(
            select(
                func.coalesce(func.sum(RewardAdjustmentEvent.points_amount), 0),
                func.coalesce(func.sum(RewardAdjustmentEvent.reputation_amount), 0),
            ).where(
                RewardAdjustmentEvent.candidate_id == candidate_id,
                RewardAdjustmentEvent.user_id == source.user_id,
                RewardAdjustmentEvent.reward_kind == source.reward_kind,
                RewardAdjustmentEvent.source_reference_id == source.reference_id,
            )
        ).one()
        points_delta = (
            source.original_points * desired_multiplier
            - source.original_points
            - int(prior_points)
        )
        reputation_delta = (
            source.original_reputation * desired_multiplier
            - source.original_reputation
            - int(prior_reputation)
        )
        if points_delta == 0 and reputation_delta == 0:
            continue

        event_type = f"reward.{source.reward_kind.value}.{direction.value}"
        reason_code = f"reward.{direction.value}"
        adjustment = RewardAdjustmentEvent(
            candidate_id=candidate_id,
            state_event_id=state_event_id,
            user_id=source.user_id,
            reward_kind=source.reward_kind,
            source_reference_id=source.reference_id,
            direction=direction,
            points_amount=points_delta,
            reputation_amount=0,
            reason_code=reason_code,
            rule_version=REWARD_COMPENSATION_RULE_VERSION,
        )
        db.add(adjustment)
        db.flush()

        if points_delta != 0:
            db.add(
                PointsLedger(
                    user_id=source.user_id,
                    amount=points_delta,
                    event_type=event_type,
                    reference_id=adjustment.id,
                    status=PointsLedgerStatus.POSTED,
                    settled_at=now,
                )
            )

        if source.has_reputation_event:
            reputation_event = apply_reputation_event(
                db,
                user_id=source.user_id,
                amount=reputation_delta,
                event_type=event_type,
                reference_id=adjustment.id,
                reason_code=reason_code,
                rule_version=REWARD_COMPENSATION_RULE_VERSION,
            )
            adjustment.reputation_amount = (
                reputation_event.amount if reputation_event is not None else 0
            )
        created.append(adjustment)

    return _summarize(created, direction=direction)


def list_candidate_reward_adjustments(
    db: Session, candidate_id: str
) -> list[RewardAdjustmentEvent]:
    return list(
        db.scalars(
            select(RewardAdjustmentEvent)
            .where(RewardAdjustmentEvent.candidate_id == candidate_id)
            .order_by(
                RewardAdjustmentEvent.created_at,
                RewardAdjustmentEvent.id,
            )
        )
    )


def _candidate_reward_sources(db: Session, candidate_id: str) -> list[_RewardSource]:
    sources: list[_RewardSource] = []
    first_submission = db.scalar(
        select(Submission)
        .where(Submission.candidate_id == candidate_id)
        .order_by(Submission.created_at, Submission.id)
        .limit(1)
    )
    if first_submission is not None:
        source = _reward_source(
            db,
            user_id=first_submission.user_id,
            reward_kind=RewardKind.CONTRIBUTION,
            reference_id=first_submission.id,
            points_event_type="submission.pending",
            reputation_event_type="contribution.verified",
        )
        if source is not None:
            sources.append(source)

    feedbacks = list(
        db.scalars(
            select(CandidateFeedback)
            .where(CandidateFeedback.candidate_id == candidate_id)
            .order_by(CandidateFeedback.user_id, CandidateFeedback.id)
        )
    )
    for feedback in feedbacks:
        source = _reward_source(
            db,
            user_id=feedback.user_id,
            reward_kind=RewardKind.VERIFICATION,
            reference_id=feedback.id,
            points_event_type="verification.accepted",
            reputation_event_type="verification.accepted",
        )
        if source is not None:
            sources.append(source)

    return sorted(
        sources,
        key=lambda item: (item.user_id, item.reward_kind.value, item.reference_id),
    )


def _reward_source(
    db: Session,
    *,
    user_id: str,
    reward_kind: RewardKind,
    reference_id: str,
    points_event_type: str,
    reputation_event_type: str,
) -> _RewardSource | None:
    points = db.scalar(
        select(PointsLedger).where(
            PointsLedger.user_id == user_id,
            PointsLedger.event_type == points_event_type,
            PointsLedger.reference_id == reference_id,
            PointsLedger.status == PointsLedgerStatus.POSTED,
        )
    )
    reputation = db.scalar(
        select(ReputationEvent).where(
            ReputationEvent.user_id == user_id,
            ReputationEvent.event_type == reputation_event_type,
            ReputationEvent.reference_id == reference_id,
        )
    )
    if points is None and reputation is None:
        return None
    return _RewardSource(
        user_id=user_id,
        reward_kind=reward_kind,
        reference_id=reference_id,
        original_points=points.amount if points is not None else 0,
        original_reputation=reputation.amount if reputation is not None else 0,
        has_reputation_event=reputation is not None,
    )


def _summarize(
    events: list[RewardAdjustmentEvent],
    *,
    direction: RewardAdjustmentDirection | None = None,
) -> RewardAdjustmentSummary:
    if not events:
        return RewardAdjustmentSummary()
    return RewardAdjustmentSummary(
        direction=direction or events[0].direction,
        affected_users=len({event.user_id for event in events}),
        points_entries=sum(event.points_amount != 0 for event in events),
        reputation_events=len(events),
        points_amount=sum(event.points_amount for event in events),
        reputation_amount=sum(event.reputation_amount for event in events),
    )
