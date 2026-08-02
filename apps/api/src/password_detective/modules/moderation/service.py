from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.archive import Archive
from password_detective.db.models.archive_fingerprint import ArchiveFingerprint
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.submission import Submission
from password_detective.db.models.verification import (
    CandidateFeedback,
    RecordStateEvent,
    StateTransitionSource,
    VerificationEvidenceEvent,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.moderation.schemas import (
    CandidateModerationDetail,
    CandidateModerationListResponse,
    CandidateModerationSummary,
    CandidateTransitionRequest,
    CandidateTransitionResponse,
    EvidenceEventResponse,
    EvidenceSnapshotResponse,
    FingerprintSummary,
    ManualTransitionReason,
    StateEventResponse,
)
from password_detective.modules.verification.service import ACTIVE_RULE, candidate_evidence_totals

MODERATION_RULE_VERSION = "moderation-v1"

_ALLOWED_TRANSITIONS: dict[CandidateStatus, set[CandidateStatus]] = {
    CandidateStatus.PENDING: {
        CandidateStatus.VERIFIED,
        CandidateStatus.REJECTED,
        CandidateStatus.QUARANTINED,
    },
    CandidateStatus.VERIFIED: {CandidateStatus.REJECTED, CandidateStatus.QUARANTINED},
    CandidateStatus.QUARANTINED: {
        CandidateStatus.PENDING,
        CandidateStatus.VERIFIED,
        CandidateStatus.REJECTED,
    },
    CandidateStatus.REJECTED: {CandidateStatus.PENDING},
}

_REASON_TARGETS: dict[ManualTransitionReason, set[CandidateStatus]] = {
    ManualTransitionReason.EVIDENCE_CONFLICT: {CandidateStatus.QUARANTINED},
    ManualTransitionReason.SECURITY_HOLD: {CandidateStatus.QUARANTINED},
    ManualTransitionReason.INVALID_CANDIDATE: {CandidateStatus.REJECTED},
    ManualTransitionReason.POLICY_VIOLATION: {CandidateStatus.REJECTED},
    ManualTransitionReason.REVIEW_REOPENED: {CandidateStatus.PENDING},
    ManualTransitionReason.VERIFIED_BY_REVIEW: {CandidateStatus.VERIFIED},
    ManualTransitionReason.QUARANTINE_CLEARED: {
        CandidateStatus.PENDING,
        CandidateStatus.VERIFIED,
    },
}


def list_candidates(
    db: Session,
    *,
    status: CandidateStatus | None,
    query: str | None,
    page: int,
    page_size: int,
) -> CandidateModerationListResponse:
    filters = []
    if status is not None:
        filters.append(PasswordCandidate.status == status)
    normalized_query = query.strip().lower() if query else None
    if normalized_query:
        pattern = f"%{normalized_query}%"
        matching_archive_ids = select(ArchiveFingerprint.archive_id).where(
            func.lower(ArchiveFingerprint.digest).like(pattern)
        )
        filters.append(
            or_(
                func.lower(PasswordCandidate.id).like(pattern),
                func.lower(PasswordCandidate.archive_id).like(pattern),
                PasswordCandidate.archive_id.in_(matching_archive_ids),
            )
        )

    total = db.scalar(select(func.count(PasswordCandidate.id)).where(*filters)) or 0
    candidates = list(
        db.scalars(
            select(PasswordCandidate)
            .options(
                selectinload(PasswordCandidate.archive),
                selectinload(PasswordCandidate.archive).selectinload(Archive.fingerprints),
            )
            .where(*filters)
            .order_by(PasswordCandidate.updated_at.desc(), PasswordCandidate.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    counts = _candidate_counts(db, [candidate.id for candidate in candidates])
    return CandidateModerationListResponse(
        items=[_summary(candidate, counts) for candidate in candidates],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_candidate_detail(db: Session, candidate_id: str) -> CandidateModerationDetail:
    candidate = db.scalar(
        select(PasswordCandidate)
        .options(
            selectinload(PasswordCandidate.archive),
            selectinload(PasswordCandidate.archive).selectinload(Archive.fingerprints),
        )
        .where(PasswordCandidate.id == candidate_id)
    )
    if candidate is None:
        raise AppError("moderation.candidate_not_found", "未找到候选记录", status_code=404)
    counts = _candidate_counts(db, [candidate.id])
    totals = candidate_evidence_totals(db, candidate.id)
    evidence_events = list(
        db.scalars(
            select(VerificationEvidenceEvent)
            .where(VerificationEvidenceEvent.candidate_id == candidate.id)
            .order_by(VerificationEvidenceEvent.created_at.desc())
        )
    )
    state_events = list(
        db.scalars(
            select(RecordStateEvent)
            .where(RecordStateEvent.candidate_id == candidate.id)
            .order_by(RecordStateEvent.created_at.desc())
        )
    )
    summary = _summary(candidate, counts)
    return CandidateModerationDetail(
        **summary.model_dump(),
        evidence_snapshot=EvidenceSnapshotResponse(
            rule_version=ACTIVE_RULE.version,
            independent_success_count=totals.independent_success_count,
            independent_failure_count=totals.independent_failure_count,
            success_weight=round(totals.success_weight, 3),
            failure_weight=round(totals.failure_weight, 3),
        ),
        evidence_events=[
            EvidenceEventResponse(
                id=event.id,
                user_id=event.user_id,
                previous_outcome=event.previous_outcome,
                outcome=event.outcome,
                source=event.source,
                weight=event.weight,
                rule_version=event.rule_version,
                revision=event.revision,
                created_at=event.created_at,
            )
            for event in evidence_events
        ],
        state_events=[_state_event(event) for event in state_events],
    )


def transition_candidate(
    db: Session,
    *,
    candidate_id: str,
    payload: CandidateTransitionRequest,
    principal: Principal,
    context: ClientContext,
) -> CandidateTransitionResponse:
    candidate = db.scalar(
        select(PasswordCandidate)
        .where(PasswordCandidate.id == candidate_id)
        .with_for_update()
    )
    if candidate is None:
        raise AppError("moderation.candidate_not_found", "未找到候选记录", status_code=404)

    previous_status = candidate.status
    allowed_targets = _ALLOWED_TRANSITIONS.get(previous_status, set())
    if payload.target_status not in allowed_targets:
        raise AppError(
            "moderation.invalid_transition",
            f"不允许从 {previous_status.value} 转换为 {payload.target_status.value}",
            status_code=409,
        )
    if payload.target_status not in _REASON_TARGETS[payload.reason_code]:
        raise AppError(
            "moderation.reason_target_mismatch",
            "处置原因与目标状态不匹配",
            status_code=422,
        )

    totals = candidate_evidence_totals(db, candidate.id)
    event = RecordStateEvent(
        candidate_id=candidate.id,
        previous_status=previous_status,
        next_status=payload.target_status,
        reason_code=payload.reason_code.value,
        reason_note=payload.reason_note,
        rule_version=MODERATION_RULE_VERSION,
        transition_source=StateTransitionSource.MANUAL,
        actor_id=principal.user.id,
        request_id=context.request_id,
        trigger_evidence_id=None,
        independent_success_count=totals.independent_success_count,
        independent_failure_count=totals.independent_failure_count,
        success_weight=totals.success_weight,
        failure_weight=totals.failure_weight,
    )
    candidate.status = payload.target_status
    candidate.updated_at = utc_now()
    if payload.target_status == CandidateStatus.VERIFIED:
        candidate.last_verified_at = utc_now()
    db.add(event)
    db.flush()
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="candidate.manual_transition",
        target_type="password_candidate",
        target_id=candidate.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "previous_status": previous_status.value,
            "current_status": payload.target_status.value,
            "reason_code": payload.reason_code.value,
            "state_event_id": event.id,
        },
    )
    db.commit()
    return CandidateTransitionResponse(
        candidate_id=candidate.id,
        previous_status=previous_status,
        current_status=payload.target_status,
        state_event_id=event.id,
        reason_code=payload.reason_code,
        request_id=context.request_id,
    )


def _candidate_counts(db: Session, candidate_ids: Sequence[str]) -> dict[str, tuple[int, int]]:
    if not candidate_ids:
        return {}
    submission_counts = dict(
        db.execute(
            select(Submission.candidate_id, func.count(Submission.id))
            .where(Submission.candidate_id.in_(candidate_ids))
            .group_by(Submission.candidate_id)
        ).all()
    )
    feedback_counts = dict(
        db.execute(
            select(CandidateFeedback.candidate_id, func.count(CandidateFeedback.id))
            .where(CandidateFeedback.candidate_id.in_(candidate_ids))
            .group_by(CandidateFeedback.candidate_id)
        ).all()
    )
    return {
        candidate_id: (
            int(submission_counts.get(candidate_id, 0)),
            int(feedback_counts.get(candidate_id, 0)),
        )
        for candidate_id in candidate_ids
    }


def _summary(
    candidate: PasswordCandidate,
    counts: dict[str, tuple[int, int]],
) -> CandidateModerationSummary:
    submission_count, feedback_count = counts.get(candidate.id, (0, 0))
    fingerprints = sorted(
        candidate.archive.fingerprints,
        key=lambda item: (item.algorithm.value, item.digest),
    )
    return CandidateModerationSummary(
        id=candidate.id,
        archive_id=candidate.archive_id,
        status=candidate.status,
        confidence_score=round(candidate.confidence_score, 3),
        fingerprints=[
            FingerprintSummary(algorithm=item.algorithm.value, digest=item.digest)
            for item in fingerprints
        ],
        submission_count=submission_count,
        feedback_count=feedback_count,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


def _state_event(event: RecordStateEvent) -> StateEventResponse:
    return StateEventResponse(
        id=event.id,
        previous_status=event.previous_status,
        next_status=event.next_status,
        reason_code=event.reason_code,
        reason_note=event.reason_note,
        rule_version=event.rule_version,
        transition_source=event.transition_source,
        actor_id=event.actor_id,
        request_id=event.request_id,
        independent_success_count=event.independent_success_count,
        independent_failure_count=event.independent_failure_count,
        success_weight=round(event.success_weight, 3),
        failure_weight=round(event.failure_weight, 3),
        created_at=event.created_at,
    )
