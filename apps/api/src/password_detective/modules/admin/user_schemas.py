from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

from password_detective.db.models.reauthentication_grant import ReauthenticationPurpose
from password_detective.db.models.user import UserRole, UserStatus
from password_detective.modules.auth.schemas import RegisterRequest
from password_detective.modules.reputation.schemas import UserLevelProfileResponse


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


class AdminUserProfileReasonCode(StrEnum):
    PROFILE_CORRECTION = "profile_correction"
    USER_REQUEST = "user_request"
    COMPLIANCE_REVIEW = "compliance_review"


class AdminReauthenticationRequest(BaseModel):
    purpose: Literal[
        ReauthenticationPurpose.ADMIN_USER_GOVERNANCE,
        ReauthenticationPurpose.ADMIN_SETTINGS_GOVERNANCE,
        ReauthenticationPurpose.ADMIN_COMMUNITY_NOTIFICATION_OPS,
    ] = ReauthenticationPurpose.ADMIN_USER_GOVERNANCE
    current_password: str = Field(min_length=1, max_length=128)
    totp_code: str | None = Field(default=None, min_length=6, max_length=8, pattern=r"^[0-9]+$")


class AdminReauthenticationResponse(BaseModel):
    reauth_token: str
    purpose: Literal[
        ReauthenticationPurpose.ADMIN_USER_GOVERNANCE,
        ReauthenticationPurpose.ADMIN_SETTINGS_GOVERNANCE,
        ReauthenticationPurpose.ADMIN_COMMUNITY_NOTIFICATION_OPS,
    ]
    expires_at: datetime


class AdminUserCreateRequest(RegisterRequest):
    role: Literal[
        UserRole.USER,
        UserRole.TRUSTED_CONTRIBUTOR,
        UserRole.MODERATOR,
    ] = UserRole.USER
    status: Literal[UserStatus.ACTIVE, UserStatus.DISABLED] = UserStatus.ACTIVE
    email_verified: bool = True


class AdminUserStatusChangeRequest(BaseModel):
    expected_status: UserStatus
    status: Literal[UserStatus.ACTIVE, UserStatus.DISABLED]
    reason_code: AdminUserStatusReasonCode
    reauth_token: str = Field(min_length=16, max_length=256)


class AdminUserSessionRevocationRequest(BaseModel):
    expected_active_session_count: int = Field(ge=0)
    reason_code: AdminSessionRevocationReasonCode
    reauth_token: str = Field(min_length=16, max_length=256)


class AdminUserProfileUpdateRequest(BaseModel):
    expected_updated_at: datetime
    email: EmailStr | None = None
    email_verified: bool | None = None
    reason_code: AdminUserProfileReasonCode
    reauth_token: str = Field(min_length=16, max_length=256)

    @model_validator(mode="after")
    def require_update(self) -> AdminUserProfileUpdateRequest:
        if self.email is None and self.email_verified is None:
            raise ValueError("至少提交一项资料变更")
        return self


class AdminUserListItem(BaseModel):
    id: str
    uid: str
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
    level: UserLevelProfileResponse
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


class AdminUserProfileUpdateResponse(BaseModel):
    user_id: str
    masked_email: str
    email_verified: bool
    updated_at: datetime
    audit_id: str
    request_id: str | None
