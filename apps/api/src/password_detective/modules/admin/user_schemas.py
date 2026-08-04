from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from password_detective.db.models.reauthentication_grant import ReauthenticationPurpose
from password_detective.db.models.user import UserRole, UserStatus


class AdminUserStatusReasonCode(StrEnum):
    SECURITY_RISK = "security_risk"
    ABUSE_CONFIRMED = "abuse_confirmed"
    POLICY_VIOLATION = "policy_violation"
    APPEAL_APPROVED = "appeal_approved"
    MANUAL_REVIEW = "manual_review"


class AdminSessionRevocationReasonCode(StrEnum):
    SECURITY_RISK = "security_risk"
    USER_REQUEST = "user_request"
    INCIDENT_RESPONSE = "incident_response"
    MANUAL_REVIEW = "manual_review"


class AdminReauthenticationRequest(BaseModel):
    purpose: Literal[
        ReauthenticationPurpose.ADMIN_USER_GOVERNANCE,
        ReauthenticationPurpose.ADMIN_SETTINGS_GOVERNANCE,
    ] = ReauthenticationPurpose.ADMIN_USER_GOVERNANCE
    current_password: str = Field(min_length=1, max_length=128)
    totp_code: str = Field(min_length=6, max_length=8, pattern=r"^[0-9]+$")


class AdminReauthenticationResponse(BaseModel):
    reauth_token: str
    purpose: Literal[
        ReauthenticationPurpose.ADMIN_USER_GOVERNANCE,
        ReauthenticationPurpose.ADMIN_SETTINGS_GOVERNANCE,
    ]
    expires_at: datetime


class AdminUserStatusChangeRequest(BaseModel):
    expected_status: UserStatus
    status: Literal[UserStatus.ACTIVE, UserStatus.DISABLED]
    reason_code: AdminUserStatusReasonCode
    reauth_token: str = Field(min_length=16, max_length=256)


class AdminUserSessionRevocationRequest(BaseModel):
    expected_active_session_count: int = Field(ge=0)
    reason_code: AdminSessionRevocationReasonCode
    reauth_token: str = Field(min_length=16, max_length=256)


class AdminUserListItem(BaseModel):
    id: str
    username: str
    masked_email: str
    email_verified: bool
    status: UserStatus
    role: UserRole
    reputation_score: int
    totp_enabled: bool
    active_session_count: int
    last_active_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdminUserListResponse(BaseModel):
    items: list[AdminUserListItem]
    page: int
    page_size: int
    total: int


class AdminUserDetail(AdminUserListItem):
    total_session_count: int
    submission_count: int
    trust_case_count: int
    points_balance: int
    reputation_event_count: int
    pending_privacy_export_count: int
    pending_deletion_request_count: int


class AdminUserStatusChangeResponse(BaseModel):
    user_id: str
    previous_status: UserStatus
    current_status: UserStatus
    revoked_session_count: int
    audit_id: str
    request_id: str | None


class AdminUserSessionRevocationResponse(BaseModel):
    user_id: str
    revoked_session_count: int
    audit_id: str
    request_id: str | None
