from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from password_detective.db.models.risk_alert import (
    RiskAlertKind,
    RiskAlertSeverity,
    RiskAlertStatus,
)


class RiskAlertResolutionCode(StrEnum):
    INVESTIGATION_STARTED = "admin.investigation_started"
    MITIGATED = "admin.mitigated"
    FALSE_POSITIVE = "admin.false_positive"
    REOPENED = "admin.reopened"


class RiskAlertTransitionRequest(BaseModel):
    target_status: RiskAlertStatus
    resolution_code: RiskAlertResolutionCode
    resolution_note: str | None = Field(default=None, max_length=1000)

    @field_validator("resolution_note")
    @classmethod
    def normalize_resolution_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_code_for_status(self) -> RiskAlertTransitionRequest:
        allowed = {
            RiskAlertStatus.OPEN: {RiskAlertResolutionCode.REOPENED},
            RiskAlertStatus.ACKNOWLEDGED: {
                RiskAlertResolutionCode.INVESTIGATION_STARTED
            },
            RiskAlertStatus.RESOLVED: {
                RiskAlertResolutionCode.MITIGATED,
                RiskAlertResolutionCode.FALSE_POSITIVE,
            },
        }
        if self.resolution_code not in allowed[self.target_status]:
            raise ValueError("处理结果码与目标状态不匹配")
        return self


class RiskAlertSummary(BaseModel):
    id: str
    candidate_id: str
    trigger_evidence_id: str
    kind: RiskAlertKind
    severity: RiskAlertSeverity
    status: RiskAlertStatus
    rule_version: str
    window_started_at: datetime
    window_ended_at: datetime
    independent_failure_count: int
    failure_weight: float
    assigned_to_id: str | None
    resolved_by_id: str | None
    resolution_code: str | None
    resolution_note: str | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RiskAlertEventResponse(BaseModel):
    id: str
    actor_id: str | None
    previous_status: RiskAlertStatus | None
    next_status: RiskAlertStatus
    action: str
    reason_code: str
    note: str | None
    request_id: str | None
    created_at: datetime


class RiskAlertDetail(RiskAlertSummary):
    events: list[RiskAlertEventResponse]


class RiskAlertListResponse(BaseModel):
    items: list[RiskAlertSummary]
    page: int
    page_size: int
    total: int


class RiskAlertTransitionResponse(BaseModel):
    alert_id: str
    previous_status: RiskAlertStatus
    current_status: RiskAlertStatus
    event_id: str
    resolution_code: RiskAlertResolutionCode
    request_id: str | None
