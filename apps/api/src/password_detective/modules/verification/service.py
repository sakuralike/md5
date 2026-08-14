from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.submission import Submission
from password_detective.db.models.user import UserRole
from password_detective.db.models.verification import (
    CandidateFeedback,
    FeedbackOutcome,
    RecordStateEvent,
    VerificationEvidenceEvent,
    VerificationSource,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.correlation.analysis import (
    CorrelationAnalysis,
    analyze_feedback_correlations,
    persist_correlation_assessment,
)
from password_detective.modules.reputation.adjustments import (
    reconcile_candidate_rewards,
)
from password_detective.modules.reputation.levels import (
    ACCEPTED_VERIFICATION_GROWTH,
    VERIFIED_CONTRIBUTION_GROWTH,
    record_growth_event,
)
from password_detective.modules.reputation.service import (
    CONTRIBUTION_VERIFIED_REPUTATION,
    VERIFICATION_ACCEPTED_REPUTATION,
    apply_reputation_event,
)
from password_detective.modules.verification.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    MyFeedbackHistoryItem,
    MyFeedbackHistoryResponse,
    VerificationSnapshot,
)


@dataclass(frozen=True)
class VerificationRule:
    version: str
    independent_success_required: int
    maximum_failure_weight_for_verification: float
    independent_failure_quarantine: int
    failure_weight_quarantine: float


ACTIVE_RULE = VerificationRule(
    version="verification-v3",
    independent_success_required=4,
    maximum_failure_weight_for_verification=2.0,
    independent_failure_quarantine=3,
    failure_weight_quarantine=3.0,
)


@dataclass(frozen=True)
class EvidenceTotals:
    independent_success_count: int
    independent_failure_count: int
    success_weight: float
    failure_weight: float
    raw_success_weight: float
    raw_failure_weight: float
    correlated_group_count: int
    downweighted_feedback_count: int

    def to_snapshot(self, rule: VerificationRule = ACTIVE_RULE) -> VerificationSnapshot:
        return VerificationSnapshot(
            rule_version=rule.version,
            independent_success_count=self.independent_success_count,
            independent_failure_count=self.independent_failure_count,
            success_weight=round(self.success_weight, 3),
            failure_weight=round(self.failure_weight, 3),
            needs_more_independent_success=max(
                rule.independent_success_required - self.independent_success_count,
                0,
            ),
        )


def feedback_weight(role: UserRole) -> float:
    if role in {UserRole.MODERATOR, UserRole.ADMIN}:
        return 1.5
    if role == UserRole.TRUSTED_CONTRIBUTOR:
        return 1.25
    return 1.0


def summarize_feedbacks(feedbacks: list[CandidateFeedback]) -> EvidenceTotals:
    """Apply candidate-local connected-component correlation and dynamic weight caps."""

    analysis = analyze_feedback_correlations(feedbacks)
    return _evidence_totals(analysis)


def candidate_correlation_analysis(db: Session, candidate_id: str) -> CorrelationAnalysis:
    feedbacks = list(
        db.scalars(select(CandidateFeedback).where(CandidateFeedback.candidate_id == candidate_id))
    )
    return analyze_feedback_correlations(feedbacks)


def _evidence_totals(analysis: CorrelationAnalysis) -> EvidenceTotals:
    return EvidenceTotals(
        independent_success_count=analysis.independent_success_count,
        independent_failure_count=analysis.independent_failure_count,
        success_weight=analysis.effective_success_weight,
        failure_weight=analysis.effective_failure_weight,
        raw_success_weight=analysis.raw_success_weight,
        raw_failure_weight=analysis.raw_failure_weight,
        correlated_group_count=analysis.correlated_group_count,
        downweighted_feedback_count=analysis.downweighted_feedback_count,
    )


def has_ever_been_verified(db: Session, candidate_id: str) -> bool:
    return bool(
        db.scalar(
            select(RecordStateEvent.id).where(
                RecordStateEvent.candidate_id == candidate_id,
                RecordStateEvent.next_status == CandidateStatus.VERIFIED,
            )
        )
    )


def candidate_evidence_totals(db: Session, candidate_id: str) -> EvidenceTotals:
    return _evidence_totals(candidate_correlation_analysis(db, candidate_id))


@dataclass(frozen=True)
class EvidenceMutation:
    feedback: CandidateFeedback
    evidence_event: VerificationEvidenceEvent | None
    totals: EvidenceTotals
    created: bool
    changed: bool


def apply_candidate_evidence(
    db: Session,
    settings: Settings,
    *,
    candidate: PasswordCandidate,
    outcome: FeedbackOutcome,
    source: VerificationSource,
    principal: Principal,
    context: ClientContext,
    installation_id_hash: str | None = None,
    promote_verified_on_success: bool = False,
) -> EvidenceMutation:
    """Upsert one account's current evidence and append history for material changes."""

    if candidate.status == CandidateStatus.REJECTED:
        raise AppError(
            "verification.rejected_candidate_locked",
            "已拒绝候选不接受普通用户反馈",
            status_code=409,
        )
    feedback = db.scalar(
        select(CandidateFeedback).where(
            CandidateFeedback.candidate_id == candidate.id,
            CandidateFeedback.user_id == principal.user.id,
        )
    )
    created = feedback is None
    desktop_upgrade = (
        feedback is not None
        and source == VerificationSource.DESKTOP_RECEIPT
        and (
            feedback.source != VerificationSource.DESKTOP_RECEIPT
            or feedback.installation_id_hash != installation_id_hash
        )
    )
    trusted_success_upgrade = (
        promote_verified_on_success
        and outcome == FeedbackOutcome.SUCCESS
        and candidate.status in {CandidateStatus.PENDING, CandidateStatus.QUARANTINED}
    )
    changed = created or feedback.outcome != outcome or desktop_upgrade or trusted_success_upgrade

    if feedback is None:
        feedback = CandidateFeedback(
            candidate_id=candidate.id,
            user_id=principal.user.id,
            outcome=outcome,
            source=source,
            weight=feedback_weight(principal.user.role),
            rule_version=ACTIVE_RULE.version,
            installation_id_hash=installation_id_hash,
            ip_prefix=context.ip_prefix,
            revision=1,
        )
        db.add(feedback)
        db.flush()
        previous_outcome = None
    elif changed:
        previous_outcome = feedback.outcome
        feedback.outcome = outcome
        feedback.source = source
        feedback.weight = feedback_weight(principal.user.role)
        feedback.rule_version = ACTIVE_RULE.version
        feedback.installation_id_hash = installation_id_hash
        feedback.ip_prefix = context.ip_prefix
        feedback.revision += 1
        feedback.updated_at = utc_now()
        db.flush()
    else:
        totals = candidate_evidence_totals(db, candidate.id)
        return EvidenceMutation(
            feedback=feedback,
            evidence_event=None,
            totals=totals,
            created=False,
            changed=False,
        )

    evidence_event = VerificationEvidenceEvent(
        feedback_id=feedback.id,
        candidate_id=candidate.id,
        user_id=principal.user.id,
        previous_outcome=previous_outcome,
        outcome=feedback.outcome,
        source=feedback.source,
        weight=feedback.weight,
        rule_version=feedback.rule_version,
        installation_id_hash=feedback.installation_id_hash,
        ip_prefix=feedback.ip_prefix,
        revision=feedback.revision,
    )
    db.add(evidence_event)
    db.flush()
    analysis = candidate_correlation_analysis(db, candidate.id)
    totals = _evidence_totals(analysis)
    persist_correlation_assessment(
        db,
        candidate_id=candidate.id,
        trigger_evidence_id=evidence_event.id,
        analysis=analysis,
    )
    _apply_automatic_transition(
        db,
        settings,
        candidate=candidate,
        totals=totals,
        trigger_evidence=evidence_event,
        trusted_desktop_success=promote_verified_on_success
        and outcome == FeedbackOutcome.SUCCESS,
    )
    from password_detective.modules.risk_alerts.detection import detect_failure_surge

    detect_failure_surge(
        db,
        candidate_id=candidate.id,
        trigger_evidence=evidence_event,
    )
    return EvidenceMutation(
        feedback=feedback,
        evidence_event=evidence_event,
        totals=totals,
        created=created,
        changed=True,
    )


def record_feedback(
    db: Session,
    settings: Settings,
    *,
    candidate_id: str,
    payload: FeedbackRequest,
    principal: Principal,
    context: ClientContext,
) -> FeedbackResponse:
    candidate = db.scalar(
        select(PasswordCandidate)
        .where(PasswordCandidate.id == candidate_id)
        .with_for_update()
    )
    if candidate is None:
        raise AppError("verification.candidate_not_found", "未找到候选记录", status_code=404)

    mutation = apply_candidate_evidence(
        db,
        settings,
        candidate=candidate,
        outcome=payload.outcome,
        source=VerificationSource.WEB_FEEDBACK,
        principal=principal,
        context=context,
    )
    feedback = mutation.feedback
    evidence_event = mutation.evidence_event
    if mutation.changed:
        write_audit_log(
            db,
            actor_id=principal.user.id,
            action="candidate.feedback_recorded",
            target_type="password_candidate",
            target_id=candidate.id,
            result="success",
            ip_prefix=context.ip_prefix,
            request_id=context.request_id,
            details={
                "outcome": feedback.outcome.value,
                "revision": feedback.revision,
                "rule_version": ACTIVE_RULE.version,
                "candidate_status": candidate.status.value,
            },
        )
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise AppError(
                "verification.concurrent_feedback_conflict",
                "反馈正在被并发更新，请重试原请求",
                status_code=409,
            ) from exc
        db.refresh(feedback)
    return FeedbackResponse(
        feedback_id=feedback.id,
        evidence_event_id=evidence_event.id if evidence_event else None,
        candidate_id=candidate.id,
        outcome=feedback.outcome,
        source=feedback.source,
        revision=feedback.revision,
        created=mutation.created,
        changed=mutation.changed,
        candidate_status=candidate.status,
        snapshot=mutation.totals.to_snapshot(),
        updated_at=feedback.updated_at,
    )


def _apply_automatic_transition(
    db: Session,
    settings: Settings,
    *,
    candidate: PasswordCandidate,
    totals: EvidenceTotals,
    trigger_evidence: VerificationEvidenceEvent,
    trusted_desktop_success: bool = False,
) -> None:
    rule = ACTIVE_RULE
    should_quarantine = (
        totals.independent_failure_count >= rule.independent_failure_quarantine
        or totals.failure_weight >= rule.failure_weight_quarantine
    )
    should_verify = (
        totals.independent_success_count >= rule.independent_success_required
        and totals.failure_weight < rule.maximum_failure_weight_for_verification
    )

    next_status = candidate.status
    reason_code: str | None = None
    if trusted_desktop_success and candidate.status in {
        CandidateStatus.PENDING,
        CandidateStatus.QUARANTINED,
    }:
        next_status = CandidateStatus.VERIFIED
        reason_code = "automatic.desktop_verified_success"
    elif should_quarantine and candidate.status in {
        CandidateStatus.PENDING,
        CandidateStatus.VERIFIED,
    }:
        next_status = CandidateStatus.QUARANTINED
        reason_code = "automatic.failure_threshold_reached"
    elif should_verify and candidate.status in {
        CandidateStatus.PENDING,
        CandidateStatus.QUARANTINED,
    }:
        next_status = CandidateStatus.VERIFIED
        reason_code = "automatic.success_threshold_reached"

    confidence = (totals.success_weight - totals.failure_weight) / max(
        float(rule.independent_success_required),
        1.0,
    )
    candidate.confidence_score = (
        1.0 if trusted_desktop_success else max(0.0, min(1.0, confidence))
    )
    if next_status == candidate.status:
        return

    previous_status = candidate.status
    first_verification = (
        next_status == CandidateStatus.VERIFIED
        and not has_ever_been_verified(db, candidate.id)
    )
    candidate.status = next_status
    if next_status == CandidateStatus.VERIFIED:
        candidate.last_verified_at = utc_now()

    state_event = RecordStateEvent(
        candidate_id=candidate.id,
        previous_status=previous_status,
        next_status=next_status,
        reason_code=reason_code or "automatic.rule_evaluation",
        rule_version=rule.version,
        trigger_evidence_id=trigger_evidence.id,
        independent_success_count=totals.independent_success_count,
        independent_failure_count=totals.independent_failure_count,
        success_weight=totals.success_weight,
        failure_weight=totals.failure_weight,
    )
    db.add(state_event)
    db.flush()
    if first_verification:
        settle_first_verification_rewards(db, settings, candidate.id)
        db.flush()
    reconcile_candidate_rewards(
        db,
        candidate_id=candidate.id,
        state_event_id=state_event.id,
        target_status=next_status,
    )


def settle_first_verification_rewards(
    db: Session,
    settings: Settings,
    candidate_id: str,
) -> None:
    submissions = list(
        db.scalars(
            select(Submission)
            .where(Submission.candidate_id == candidate_id)
            .order_by(Submission.created_at, Submission.id)
        )
    )
    first_submission_id = submissions[0].id if submissions else None
    pending_ledgers = list(
        db.scalars(
            select(PointsLedger)
            .join(Submission, Submission.id == PointsLedger.reference_id)
            .where(
                Submission.candidate_id == candidate_id,
                PointsLedger.event_type == "submission.pending",
                PointsLedger.status == PointsLedgerStatus.PENDING,
            )
        )
    )
    now = utc_now()
    for ledger in pending_ledgers:
        ledger.status = (
            PointsLedgerStatus.POSTED
            if ledger.reference_id == first_submission_id
            else PointsLedgerStatus.REVERSED
        )
        ledger.settled_at = now

    if submissions:
        first_submission = submissions[0]
        if first_submission.user_id is not None:
            apply_reputation_event(
                db,
                user_id=first_submission.user_id,
                amount=CONTRIBUTION_VERIFIED_REPUTATION,
                event_type="contribution.verified",
                reference_id=first_submission.id,
                reason_code="reputation.valid_contribution",
            )
            record_growth_event(
                db,
                user_id=first_submission.user_id,
                amount=VERIFIED_CONTRIBUTION_GROWTH,
                event_type="contribution.verified",
                reference_id=first_submission.id,
                reason_code="growth.valid_contribution",
            )

    successful_feedbacks = list(
        db.scalars(
            select(CandidateFeedback).where(
                CandidateFeedback.candidate_id == candidate_id,
                CandidateFeedback.outcome == FeedbackOutcome.SUCCESS,
            )
        )
    )
    for feedback in successful_feedbacks:
        if settings.verification_reward_points > 0:
            existing = db.scalar(
                select(PointsLedger.id).where(
                    PointsLedger.user_id == feedback.user_id,
                    PointsLedger.event_type == "verification.accepted",
                    PointsLedger.reference_id == feedback.id,
                )
            )
            if existing is None:
                db.add(
                    PointsLedger(
                        user_id=feedback.user_id,
                        amount=settings.verification_reward_points,
                        event_type="verification.accepted",
                        reference_id=feedback.id,
                        status=PointsLedgerStatus.POSTED,
                        settled_at=now,
                    )
                )
        apply_reputation_event(
            db,
            user_id=feedback.user_id,
            amount=VERIFICATION_ACCEPTED_REPUTATION,
            event_type="verification.accepted",
            reference_id=feedback.id,
            reason_code="reputation.valid_verification",
        )
        record_growth_event(
            db,
            user_id=feedback.user_id,
            amount=ACCEPTED_VERIFICATION_GROWTH,
            event_type="verification.accepted",
            reference_id=feedback.id,
            reason_code="growth.valid_verification",
        )


def list_my_feedback_history(
    db: Session,
    *,
    principal: Principal,
    page: int,
    page_size: int,
) -> MyFeedbackHistoryResponse:
    total = db.scalar(
        select(func.count(VerificationEvidenceEvent.id)).where(
            VerificationEvidenceEvent.user_id == principal.user.id
        )
    ) or 0
    events = list(
        db.scalars(
            select(VerificationEvidenceEvent)
            .where(VerificationEvidenceEvent.user_id == principal.user.id)
            .order_by(
                desc(VerificationEvidenceEvent.created_at),
                desc(VerificationEvidenceEvent.id),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    statuses = {
        candidate_id: status
        for candidate_id, status in db.execute(
            select(PasswordCandidate.id, PasswordCandidate.status).where(
                PasswordCandidate.id.in_({item.candidate_id for item in events})
            )
        )
    }
    return MyFeedbackHistoryResponse(
        items=[
            MyFeedbackHistoryItem(
                evidence_event_id=item.id,
                feedback_id=item.feedback_id,
                candidate_id=item.candidate_id,
                previous_outcome=item.previous_outcome,
                outcome=item.outcome,
                source=item.source,
                revision=item.revision,
                rule_version=item.rule_version,
                candidate_status=statuses[item.candidate_id],
                created_at=item.created_at,
            )
            for item in events
        ],
        page=page,
        page_size=page_size,
        total=total,
    )
