from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from password_detective.db.models.risk_alert import (
    RiskAlertKind,
    RiskAlertNotificationKind,
    RiskAlertNotificationStatus,
    RiskAlertSeverity,
    RiskAlertStatus,
)
from password_detective.db.models.user import UserRole


class RiskAlertResolutionCode(StrEnum):
    INVESTIGATION_STARTED = "admin.investigation_started"
    MITIGATED = "admin.mitigated"
    FALSE_POSITIVE = "admin.false_positive"
    REOPENED = "admin.reopened"


class RiskAlertSlaState(StrEnum):
    WITHIN_SLA = "within_sla"
    ACKNOWLEDGEMENT_OVERDUE = "acknowledgement_overdue"
    RESOLUTION_OVERDUE = "resolution_overdue"
    MET = "met"
    BREACHED = "breached"


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
            RiskAlertStatus.ACKNOWLEDGED: {RiskAlertResolutionCode.INVESTIGATION_STARTED},
            RiskAlertStatus.RESOLVED: {
                RiskAlertResolutionCode.MITIGATED,
                RiskAlertResolutionCode.FALSE_POSITIVE,
            },
        }
        if self.resolution_code not in allowed[self.target_status]:
            raise ValueError("处理结果码与目标状态不匹配")
        return self


class RiskAlertAssignmentRequest(BaseModel):
    assignee_id: str = Field(min_length=1, max_length=36)
    assignment_note: str | None = Field(default=None, max_length=500)

    @field_validator("assignment_note")
    @classmethod
    def normalize_assignment_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class RiskAlertOperator(BaseModel):
    id: str
    username: str
    role: UserRole


class RiskAlertSummary(BaseModel):
    id: str
    candidate_id: str
    trigger_evidence_id: str
    kind: RiskAlertKind
    severity: RiskAlertSeverity
    status: RiskAlertStatus
    rule_version: str
    sla_rule_version: str
    sla_state: RiskAlertSlaState
    window_started_at: datetime
    window_ended_at: datetime
    acknowledge_due_at: datetime
    resolve_due_at: datetime
    acknowledged_at: datetime | None
    independent_failure_count: int
    failure_weight: float
    assigned_to_id: str | None
    assigned_to_username: str | None
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
    previous_assignee_id: str | None
    next_assignee_id: str | None
    action: str
    reason_code: str
    note: str | None
    request_id: str | None
    created_at: datetime


class RiskAlertNotificationResponse(BaseModel):
    id: str
    alert_id: str
    event_id: str | None
    recipient_user_id: str
    recipient_username: str
    kind: RiskAlertNotificationKind
    status: RiskAlertNotificationStatus
    attempts: int
    provider: str | None
    provider_message_id: str | None
    available_at: datetime
    sent_at: datetime | None
    failed_at: datetime | None
    last_error_code: str | None
    replay_count: int
    last_replayed_at: datetime | None
    last_replayed_by_id: str | None
    created_at: datetime
    updated_at: datetime


class RiskAlertNotificationProviderMetrics(BaseModel):
    provider: str
    pending_count: int
    sent_count: int
    failed_count: int


class RiskAlertNotificationMetricsResponse(BaseModel):
    generated_at: datetime
    pending_count: int
    sent_count: int
    failed_count: int
    failed_last_24_hours: int
    oldest_pending_seconds: int | None
    providers: list[RiskAlertNotificationProviderMetrics]


class RiskAlertNotificationListResponse(BaseModel):
    items: list[RiskAlertNotificationResponse]
    page: int
    page_size: int
    total: int


class RiskAlertNotificationReplayRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()


class RiskAlertNotificationReplayResponse(BaseModel):
    notification_id: str
    status: RiskAlertNotificationStatus
    replay_count: int
    request_id: str | None


class RiskAlertDetail(RiskAlertSummary):
    events: list[RiskAlertEventResponse]
    notifications: list[RiskAlertNotificationResponse]


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


class RiskAlertAssignmentResponse(BaseModel):
    alert_id: str
    previous_assignee_id: str | None
    current_assignee_id: str
    event_id: str
    request_id: str | None
