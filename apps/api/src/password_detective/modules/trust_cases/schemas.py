from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from password_detective.db.models.trust_case import TrustCaseKind, TrustCaseStatus


class ReportReason(StrEnum):
    INVALID_CANDIDATE = "report.invalid_candidate"
    POLICY_VIOLATION = "report.policy_violation"
    MISLEADING_METADATA = "report.misleading_metadata"
    OTHER = "report.other"


class AppealReason(StrEnum):
    DECISION_INCORRECT = "appeal.decision_incorrect"
    NEW_EVIDENCE = "appeal.new_evidence"
    CONTEXT_MISSING = "appeal.context_missing"
    OTHER = "appeal.other"


class CaseResolutionCode(StrEnum):
    REVIEW_STARTED = "admin.review_started"
    ACTION_TAKEN = "admin.action_taken"
    NO_VIOLATION = "admin.no_violation"
    INSUFFICIENT_EVIDENCE = "admin.insufficient_evidence"
    APPEAL_UPHELD = "admin.appeal_upheld"
    APPEAL_DENIED = "admin.appeal_denied"
    REOPENED = "admin.reopened"


class ReportCreateRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=36)
    reason_code: ReportReason
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_note(value)


class AppealCreateRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=36)
    related_case_id: str | None = Field(default=None, max_length=36)
    reason_code: AppealReason
    description: str = Field(min_length=1, max_length=1000)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        normalized = _normalize_note(value)
        if normalized is None:
            raise ValueError("申诉说明不能为空")
        return normalized


class TrustCaseTransitionRequest(BaseModel):
    target_status: TrustCaseStatus
    resolution_code: CaseResolutionCode
    resolution_note: str | None = Field(default=None, max_length=1000)

    @field_validator("resolution_note")
    @classmethod
    def normalize_resolution_note(cls, value: str | None) -> str | None:
        return _normalize_note(value)

    @model_validator(mode="after")
    def validate_code_for_status(self) -> TrustCaseTransitionRequest:
        allowed = {
            TrustCaseStatus.OPEN: {CaseResolutionCode.REOPENED},
            TrustCaseStatus.IN_REVIEW: {CaseResolutionCode.REVIEW_STARTED},
            TrustCaseStatus.RESOLVED: {
                CaseResolutionCode.ACTION_TAKEN,
                CaseResolutionCode.NO_VIOLATION,
                CaseResolutionCode.APPEAL_UPHELD,
                CaseResolutionCode.APPEAL_DENIED,
            },
            TrustCaseStatus.DISMISSED: {
                CaseResolutionCode.INSUFFICIENT_EVIDENCE,
                CaseResolutionCode.NO_VIOLATION,
            },
        }
        if self.resolution_code not in allowed[self.target_status]:
            raise ValueError("处理结果码与目标状态不匹配")
        return self


class TrustCaseSummary(BaseModel):
    id: str
    kind: TrustCaseKind
    status: TrustCaseStatus
    reporter_id: str
    reporter_username: str
    candidate_id: str
    related_case_id: str | None
    reason_code: str
    description: str | None
    assigned_to_id: str | None
    resolved_by_id: str | None
    resolution_code: str | None
    resolution_note: str | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TrustCaseEventResponse(BaseModel):
    id: str
    actor_id: str | None
    previous_status: TrustCaseStatus | None
    next_status: TrustCaseStatus
    action: str
    reason_code: str
    note: str | None
    request_id: str | None
    created_at: datetime


class TrustCaseDetail(TrustCaseSummary):
    events: list[TrustCaseEventResponse]


class TrustCaseListResponse(BaseModel):
    items: list[TrustCaseSummary]
    page: int
    page_size: int
    total: int


class TrustCaseTransitionResponse(BaseModel):
    case_id: str
    previous_status: TrustCaseStatus
    current_status: TrustCaseStatus
    event_id: str
    resolution_code: CaseResolutionCode
    request_id: str | None


def _normalize_note(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
