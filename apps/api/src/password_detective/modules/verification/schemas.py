from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from password_detective.db.models.password_candidate import CandidateStatus
from password_detective.db.models.verification import FeedbackOutcome, VerificationSource


class FeedbackRequest(BaseModel):
    outcome: FeedbackOutcome


class VerificationSnapshot(BaseModel):
    rule_version: str
    independent_success_count: int
    independent_failure_count: int
    success_weight: float
    failure_weight: float
    needs_more_independent_success: int


class FeedbackResponse(BaseModel):
    feedback_id: str
    evidence_event_id: str | None
    candidate_id: str
    outcome: FeedbackOutcome
    source: VerificationSource
    revision: int
    created: bool
    changed: bool
    candidate_status: CandidateStatus
    snapshot: VerificationSnapshot
    updated_at: datetime


class MyFeedbackHistoryItem(BaseModel):
    evidence_event_id: str
    feedback_id: str
    candidate_id: str
    previous_outcome: FeedbackOutcome | None
    outcome: FeedbackOutcome
    source: VerificationSource
    revision: int
    rule_version: str
    candidate_status: CandidateStatus
    created_at: datetime


class MyFeedbackHistoryResponse(BaseModel):
    items: list[MyFeedbackHistoryItem]
    page: int
    page_size: int
    total: int
