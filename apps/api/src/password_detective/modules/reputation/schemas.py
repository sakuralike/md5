from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from password_detective.db.models.points_ledger import PointsLedgerStatus


class PointsSummary(BaseModel):
    available: int
    pending: int
    reversed: int


class FeedbackSummary(BaseModel):
    effective_success: int
    effective_failure: int
    history_events: int


class ContributionSummary(BaseModel):
    total: int
    verified: int


class TrustProfileResponse(BaseModel):
    reputation_score: int
    reputation_min: int = 0
    reputation_max: int = 100
    points: PointsSummary
    feedback: FeedbackSummary
    contributions: ContributionSummary


class PointsLedgerItem(BaseModel):
    id: str
    amount: int
    event_type: str
    reference_id: str
    status: PointsLedgerStatus
    created_at: datetime
    settled_at: datetime | None


class PointsLedgerResponse(BaseModel):
    items: list[PointsLedgerItem]
    page: int
    page_size: int
    total: int


class ReputationEventItem(BaseModel):
    id: str
    amount: int
    event_type: str
    reference_id: str
    reason_code: str
    rule_version: str
    previous_score: int
    next_score: int
    created_at: datetime


class ReputationEventsResponse(BaseModel):
    items: list[ReputationEventItem]
    page: int
    page_size: int
    total: int
