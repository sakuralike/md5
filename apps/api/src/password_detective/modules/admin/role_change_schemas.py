from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from password_detective.db.models.role_change_request import RoleChangeRequestStatus
from password_detective.db.models.user import UserRole


class RoleChangeReasonCode(StrEnum):
    TRUST_PROMOTION = "trust_promotion"
    ROLE_ALIGNMENT = "role_alignment"
    DUTY_ASSIGNMENT = "duty_assignment"
    DUTY_REMOVAL = "duty_removal"
    SECURITY_RESPONSE = "security_response"


class RoleChangeReviewReasonCode(StrEnum):
    VERIFIED = "verified"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    POLICY_CONFLICT = "policy_conflict"
    SECURITY_RESPONSE = "security_response"


class RoleChangeCreateRequest(BaseModel):
    expected_role: UserRole
    requested_role: UserRole
    reason_code: RoleChangeReasonCode
    reauth_token: str = Field(min_length=16, max_length=256)


class RoleChangeReviewRequest(BaseModel):
    expected_status: RoleChangeRequestStatus = RoleChangeRequestStatus.PENDING
    reason_code: RoleChangeReviewReasonCode
    reauth_token: str = Field(min_length=16, max_length=256)


class RoleChangeRequestResponse(BaseModel):
    id: str
    target_user_id: str
    expected_role: UserRole
    requested_role: UserRole
    status: RoleChangeRequestStatus
    requested_by: str
    reviewed_by: str | None
    reason_code: str
    review_reason_code: str | None
    created_at: datetime
    reviewed_at: datetime | None


class RoleChangeRequestListResponse(BaseModel):
    items: list[RoleChangeRequestResponse]
    page: int
    page_size: int
    total: int


class RoleChangeMutationResponse(BaseModel):
    request: RoleChangeRequestResponse
    revoked_session_count: int
    audit_id: str
    request_id: str | None
