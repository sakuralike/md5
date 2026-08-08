from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from password_detective.db.models.password_candidate import CandidateStatus
from password_detective.db.models.trust_case import (
    TrustCaseKind,
    TrustCaseStatus,
    TrustCaseSubjectType,
)


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


class AccountAppealReason(StrEnum):
    RESTRICTION_INCORRECT = "account_appeal.restriction_incorrect"
    ACCOUNT_RECOVERED = "account_appeal.account_recovered"
    CONTEXT_MISSING = "account_appeal.context_missing"
    OTHER = "account_appeal.other"


class AccountAppealRequestedAction(StrEnum):
    RESTORE_ACCESS = "restore_access"
    REVIEW_RESTRICTION = "review_restriction"


class CaseAssignmentReason(StrEnum):
    ASSIGNED = "admin.assigned"
    REASSIGNED = "admin.reassigned"


class CaseReopenReason(StrEnum):
    REOPENED = "admin.reopened"


class CaseResolutionCode(StrEnum):
    REVIEW_STARTED = "admin.review_started"
    ACTION_TAKEN = "admin.action_taken"
    NO_VIOLATION = "admin.no_violation"
    INSUFFICIENT_EVIDENCE = "admin.insufficient_evidence"
    APPEAL_UPHELD = "admin.appeal_upheld"
    APPEAL_DENIED = "admin.appeal_denied"
    ACCOUNT_RESTORED = "admin.account_restored"
    ACCOUNT_RESTRICTION_UPHELD = "admin.account_restriction_upheld"
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


class AccountAppealCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_action: AccountAppealRequestedAction
    reason_code: AccountAppealReason
    description: str = Field(min_length=1, max_length=1000)
    evidence_summary: str | None = Field(default=None, max_length=1000)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        normalized = _normalize_note(value)
        if normalized is None:
            raise ValueError("账号申诉说明不能为空")
        return normalized

    @field_validator("evidence_summary")
    @classmethod
    def normalize_evidence_summary(cls, value: str | None) -> str | None:
        return _normalize_note(value)


class TrustCaseAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    assignee_id: str = Field(min_length=1, max_length=36)
    reason_code: CaseAssignmentReason
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("assignee_id")
    @classmethod
    def normalize_assignee_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        return _normalize_note(value)


class TrustCaseReopenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason_code: CaseReopenReason = CaseReopenReason.REOPENED
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        return _normalize_note(value)


class TrustCaseResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    resolution_code: CaseResolutionCode
    resolution_note: str = Field(min_length=1, max_length=1000)
    candidate_target_status: CandidateStatus | None = None

    @field_validator("resolution_note")
    @classmethod
    def normalize_resolution_note(cls, value: str) -> str:
        normalized = _normalize_note(value)
        if normalized is None:
            raise ValueError("处置说明不能为空")
        return normalized

    @model_validator(mode="after")
    def validate_candidate_target(self) -> TrustCaseResolveRequest:
        if self.resolution_code == CaseResolutionCode.ACTION_TAKEN:
            if self.candidate_target_status not in {
                CandidateStatus.REJECTED,
                CandidateStatus.QUARANTINED,
            }:
                raise ValueError("采取治理动作时必须指定拒绝或隔离候选")
        elif self.resolution_code == CaseResolutionCode.APPEAL_UPHELD:
            if self.candidate_target_status != CandidateStatus.VERIFIED:
                raise ValueError("候选申诉成立时必须恢复为已验证状态")
        elif self.candidate_target_status is not None:
            raise ValueError("该处置结果不允许修改候选状态")
        return self


class TrustCaseTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
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
    version: int
    kind: TrustCaseKind
    subject_type: TrustCaseSubjectType
    status: TrustCaseStatus
    reporter_id: str
    reporter_username: str
    candidate_id: str | None
    target_user_id: str | None
    risk_alert_id: str | None
    related_case_id: str | None
    reason_code: str
    requested_action: str | None
    description: str | None
    evidence_summary: str | None
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
    previous_assignee_id: str | None
    next_status: TrustCaseStatus
    next_assignee_id: str | None
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
    previous_assignee_id: str | None
    current_assignee_id: str | None
    version: int
    event_id: str
    resolution_code: CaseResolutionCode
    request_id: str | None


class TrustCaseRewardAdjustment(BaseModel):
    affected_users: int = 0
    points_entries: int = 0
    reputation_events: int = 0
    points_amount: int = 0
    reputation_amount: int = 0


class TrustCaseSideEffectResponse(BaseModel):
    effect_type: str
    target_type: str
    target_id: str
    previous_value: str | None
    next_value: str | None
    reference_id: str | None = None
    reward_adjustment: TrustCaseRewardAdjustment | None = None


class TrustCaseResolveResponse(BaseModel):
    case_id: str
    previous_status: TrustCaseStatus
    current_status: TrustCaseStatus
    current_assignee_id: str
    resolved_by_id: str
    version: int
    event_id: str
    resolution_code: CaseResolutionCode
    side_effects: list[TrustCaseSideEffectResponse] = Field(default_factory=list)
    request_id: str | None


class TrustCaseAssignResponse(BaseModel):
    case_id: str
    previous_status: TrustCaseStatus
    current_status: TrustCaseStatus
    previous_assignee_id: str | None
    current_assignee_id: str
    version: int
    event_id: str
    reason_code: CaseAssignmentReason
    request_id: str | None


class TrustCaseReopenResponse(BaseModel):
    case_id: str
    previous_status: TrustCaseStatus
    current_status: TrustCaseStatus
    previous_assignee_id: str | None
    current_assignee_id: str | None
    version: int
    event_id: str
    reason_code: CaseReopenReason
    request_id: str | None


def _normalize_note(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
