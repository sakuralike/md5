from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AdminQueueBacklog(BaseModel):
    pending_candidates: int = Field(ge=0)
    active_trust_cases: int = Field(ge=0)
    active_risk_alerts: int = Field(ge=0)
    pending_privacy_exports: int = Field(ge=0)
    pending_deletion_requests: int = Field(ge=0)
    total: int = Field(ge=0)


class AdminDashboardSummary(BaseModel):
    window_hours: int = Field(ge=1)
    window_started_at: datetime
    generated_at: datetime
    search_count: int = Field(ge=0)
    search_hit_count: int = Field(ge=0)
    search_hit_rate: float = Field(ge=0, le=1)
    contribution_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    verified_candidate_count: int = Field(ge=0)
    candidate_verification_rate: float = Field(ge=0, le=1)
    quarantined_candidate_count: int = Field(ge=0)
    audited_operation_count: int = Field(ge=0)
    audited_error_count: int = Field(ge=0)
    audited_error_rate: float = Field(ge=0, le=1)
    queue_backlog: AdminQueueBacklog
