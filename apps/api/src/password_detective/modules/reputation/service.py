from __future__ import annotations

from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.reputation_event import ReputationEvent
from password_detective.db.models.submission import Submission
from password_detective.db.models.user import User
from password_detective.db.models.verification import (
    CandidateFeedback,
    FeedbackOutcome,
    VerificationEvidenceEvent,
)
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.reputation.levels import get_user_level_profile
from password_detective.modules.reputation.schemas import (
    ContributionSummary,
    FeedbackSummary,
    PointsLedgerItem,
    PointsLedgerResponse,
    PointsSummary,
    ReputationEventItem,
    ReputationEventsResponse,
    TrustProfileResponse,
)

REPUTATION_MIN = 0
REPUTATION_MAX = 100
REPUTATION_RULE_VERSION = "reputation-v1"
CONTRIBUTION_VERIFIED_REPUTATION = 3
VERIFICATION_ACCEPTED_REPUTATION = 2


def apply_reputation_event(
    db: Session,
    *,
    user_id: str,
    amount: int,
    event_type: str,
    reference_id: str,
    reason_code: str,
    rule_version: str = REPUTATION_RULE_VERSION,
) -> ReputationEvent | None:
    """Apply one bounded, idempotent reputation mutation and append its event."""

    existing = db.scalar(
        select(ReputationEvent).where(
            ReputationEvent.user_id == user_id,
            ReputationEvent.event_type == event_type,
            ReputationEvent.reference_id == reference_id,
        )
    )
    if existing is not None:
        return existing

    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        return None
    existing = db.scalar(
        select(ReputationEvent).where(
            ReputationEvent.user_id == user_id,
            ReputationEvent.event_type == event_type,
            ReputationEvent.reference_id == reference_id,
        )
    )
    if existing is not None:
        return existing
    previous_score = user.reputation_score
    next_score = max(REPUTATION_MIN, min(REPUTATION_MAX, previous_score + amount))
    applied_amount = next_score - previous_score

    event = ReputationEvent(
        user_id=user_id,
        amount=applied_amount,
        event_type=event_type,
        reference_id=reference_id,
        reason_code=reason_code,
        rule_version=rule_version,
        previous_score=previous_score,
        next_score=next_score,
    )
    user.reputation_score = next_score
    db.add(event)
    return event


def get_trust_profile(db: Session, *, principal: Principal) -> TrustProfileResponse:
    user_id = principal.user.id
    points_row = db.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (PointsLedger.status == PointsLedgerStatus.POSTED, PointsLedger.amount),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (PointsLedger.status == PointsLedgerStatus.PENDING, PointsLedger.amount),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (PointsLedger.status == PointsLedgerStatus.REVERSED, PointsLedger.amount),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(PointsLedger.user_id == user_id)
    ).one()
    effective_success = db.scalar(
        select(func.count(CandidateFeedback.id)).where(
            CandidateFeedback.user_id == user_id,
            CandidateFeedback.outcome == FeedbackOutcome.SUCCESS,
        )
    ) or 0
    effective_failure = db.scalar(
        select(func.count(CandidateFeedback.id)).where(
            CandidateFeedback.user_id == user_id,
            CandidateFeedback.outcome == FeedbackOutcome.FAILURE,
        )
    ) or 0
    history_events = db.scalar(
        select(func.count(VerificationEvidenceEvent.id)).where(
            VerificationEvidenceEvent.user_id == user_id
        )
    ) or 0
    contribution_total = db.scalar(
        select(func.count(Submission.id)).where(Submission.user_id == user_id)
    ) or 0
    verified_contributions = db.scalar(
        select(func.count(Submission.id))
        .join(PasswordCandidate, PasswordCandidate.id == Submission.candidate_id)
        .where(
            Submission.user_id == user_id,
            PasswordCandidate.status == CandidateStatus.VERIFIED,
        )
    ) or 0
    current_score = db.scalar(select(User.reputation_score).where(User.id == user_id))

    return TrustProfileResponse(
        reputation_score=(
            current_score if current_score is not None else principal.user.reputation_score
        ),
        points=PointsSummary(
            available=int(points_row[0]),
            pending=int(points_row[1]),
            reversed=int(points_row[2]),
        ),
        feedback=FeedbackSummary(
            effective_success=effective_success,
            effective_failure=effective_failure,
            history_events=history_events,
        ),
        contributions=ContributionSummary(
            total=contribution_total,
            verified=verified_contributions,
        ),
        level=get_user_level_profile(db, user_id=user_id),
    )


def list_my_points(
    db: Session, *, principal: Principal, page: int, page_size: int
) -> PointsLedgerResponse:
    total = db.scalar(
        select(func.count(PointsLedger.id)).where(PointsLedger.user_id == principal.user.id)
    ) or 0
    entries = list(
        db.scalars(
            select(PointsLedger)
            .where(PointsLedger.user_id == principal.user.id)
            .order_by(desc(PointsLedger.created_at), desc(PointsLedger.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return PointsLedgerResponse(
        items=[
            PointsLedgerItem(
                id=item.id,
                amount=item.amount,
                event_type=item.event_type,
                reference_id=item.reference_id,
                status=item.status,
                created_at=item.created_at,
                settled_at=item.settled_at,
            )
            for item in entries
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


def list_my_reputation_events(
    db: Session, *, principal: Principal, page: int, page_size: int
) -> ReputationEventsResponse:
    total = db.scalar(
        select(func.count(ReputationEvent.id)).where(
            ReputationEvent.user_id == principal.user.id
        )
    ) or 0
    entries = list(
        db.scalars(
            select(ReputationEvent)
            .where(ReputationEvent.user_id == principal.user.id)
            .order_by(desc(ReputationEvent.created_at), desc(ReputationEvent.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return ReputationEventsResponse(
        items=[
            ReputationEventItem(
                id=item.id,
                amount=item.amount,
                event_type=item.event_type,
                reference_id=item.reference_id,
                reason_code=item.reason_code,
                rule_version=item.rule_version,
                previous_score=item.previous_score,
                next_score=item.next_score,
                created_at=item.created_at,
            )
            for item in entries
        ],
        page=page,
        page_size=page_size,
        total=total,
    )
