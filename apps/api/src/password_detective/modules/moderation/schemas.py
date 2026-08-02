from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from password_detective.db.models.password_candidate import CandidateStatus
from password_detective.db.models.reward_adjustment_event import (
    RewardAdjustmentDirection,
    RewardKind,
)
from password_detective.db.models.verification import (
    FeedbackOutcome,
    StateTransitionSource,
    VerificationSource,
)


class ManualTransitionReason(StrEnum):
    EVIDENCE_CONFLICT = "manual.evidence_conflict"
    SECURITY_HOLD = "manual.security_hold"
    INVALID_CANDIDATE = "manual.invalid_candidate"
    POLICY_VIOLATION = "manual.policy_violation"
    REVIEW_REOPENED = "manual.review_reopened"
    VERIFIED_BY_REVIEW = "manual.verified_by_review"
    QUARANTINE_CLEARED = "manual.quarantine_cleared"


class CandidateTransitionRequest(BaseModel):
    target_status: CandidateStatus
    reason_code: ManualTransitionReason
    reason_note: str | None = Field(default=None, max_length=500)

    @field_validator("reason_note")
    @classmethod
    def normalize_reason_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class FingerprintSummary(BaseModel):
    algorithm: str
    digest: str


class EvidenceSnapshotResponse(BaseModel):
    rule_version: str
    independent_success_count: int
    independent_failure_count: int
    success_weight: float
    failure_weight: float


class CandidateModerationSummary(BaseModel):
    id: str
    archive_id: str
    status: CandidateStatus
    confidence_score: float
    fingerprints: list[FingerprintSummary]
    submission_count: int
    feedback_count: int
    created_at: datetime
    updated_at: datetime


class CandidateModerationListResponse(BaseModel):
    items: list[CandidateModerationSummary]
    page: int
    page_size: int
    total: int


class EvidenceEventResponse(BaseModel):
    id: str
    user_id: str
    previous_outcome: FeedbackOutcome | None
    outcome: FeedbackOutcome
    source: VerificationSource
    weight: float
    rule_version: str
    revision: int
    created_at: datetime


class StateEventResponse(BaseModel):
    id: str
    previous_status: CandidateStatus
    next_status: CandidateStatus
    reason_code: str
    reason_note: str | None
    rule_version: str
    transition_source: StateTransitionSource
    actor_id: str | None
    request_id: str | None
    independent_success_count: int
    independent_failure_count: int
    success_weight: float
    failure_weight: float
    created_at: datetime


class RewardAdjustmentSummaryResponse(BaseModel):
    rule_version: str
    direction: RewardAdjustmentDirection | None
    affected_users: int
    points_entries: int
    reputation_events: int
    points_amount: int
    reputation_amount: int


class RewardAdjustmentEventResponse(BaseModel):
    id: str
    state_event_id: str
    user_id: str
    reward_kind: RewardKind
    source_reference_id: str
    direction: RewardAdjustmentDirection
    points_amount: int
    reputation_amount: int
    reason_code: str
    rule_version: str
    created_at: datetime


class CandidateModerationDetail(CandidateModerationSummary):
    evidence_snapshot: EvidenceSnapshotResponse
    evidence_events: list[EvidenceEventResponse]
    state_events: list[StateEventResponse]
    reward_adjustments: list[RewardAdjustmentEventResponse]


class CandidateTransitionResponse(BaseModel):
    candidate_id: str
    previous_status: CandidateStatus
    current_status: CandidateStatus
    state_event_id: str
    reason_code: ManualTransitionReason
    request_id: str | None
    reward_adjustment: RewardAdjustmentSummaryResponse
