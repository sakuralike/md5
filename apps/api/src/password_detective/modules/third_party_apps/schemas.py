from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from password_detective.db.models.third_party_app import (
    ThirdPartyApplicationRequestStatus,
    ThirdPartyApplicationReviewEventKind,
    ThirdPartyAppSource,
    ThirdPartyAppStatus,
)


class ThirdPartyAppCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    developer_name: str = Field(min_length=2, max_length=128)
    description: str = Field(default="", max_length=10_000)
    redirect_uris: list[str] = Field(min_length=1, max_length=10)
    scopes: list[str] = Field(min_length=1, max_length=20)


class ThirdPartyAppReviewRequest(BaseModel):
    review_note: str | None = Field(default=None, max_length=2_000)
    trusted_verification_enabled: bool = False


class ThirdPartyAppListItem(BaseModel):
    id: str
    client_id: str
    name: str
    developer_name: str
    description: str
    status: ThirdPartyAppStatus
    application_source: ThirdPartyAppSource
    requested_scopes: list[str]
    approved_scopes: list[str]
    redirect_uris: list[str]
    trusted_verification_enabled: bool
    request_count: int
    last_used_at: str | None
    reviewed_at: str | None
    created_at: str
    updated_at: str
    revoked_at: str | None
    management_secret: str | None = None


class ThirdPartyAppListResponse(BaseModel):
    items: list[ThirdPartyAppListItem]
    page: int
    page_size: int
    total: int


class ThirdPartyApplicationCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    developer_name: str = Field(min_length=2, max_length=128)
    description: str = Field(default="", max_length=10_000)
    website_url: str = Field(min_length=8, max_length=2_000)
    privacy_policy_url: str = Field(min_length=8, max_length=2_000)
    redirect_uris: list[str] = Field(min_length=1, max_length=10)
    scopes: list[str] = Field(min_length=1, max_length=20)
    windows_release_info: str = Field(min_length=2, max_length=10_000)
    use_case: str = Field(min_length=2, max_length=10_000)


class ThirdPartyApplicationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    developer_name: str | None = Field(default=None, min_length=2, max_length=128)
    description: str | None = Field(default=None, max_length=10_000)
    website_url: str | None = Field(default=None, min_length=8, max_length=2_000)
    privacy_policy_url: str | None = Field(default=None, min_length=8, max_length=2_000)
    redirect_uris: list[str] | None = Field(default=None, min_length=1, max_length=10)
    scopes: list[str] | None = Field(default=None, min_length=1, max_length=20)
    windows_release_info: str | None = Field(default=None, min_length=2, max_length=10_000)
    use_case: str | None = Field(default=None, min_length=2, max_length=10_000)


class ThirdPartyApplicationReviewRequest(BaseModel):
    review_note: str | None = Field(default=None, max_length=2_000)
    approved_scopes: list[str] = Field(default_factory=list, max_length=20)
    trusted_verification_enabled: bool = False


class ThirdPartyApplicationRejectRequest(BaseModel):
    review_note: str = Field(min_length=1, max_length=2_000)

    @field_validator("review_note")
    @classmethod
    def validate_review_note(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("驳回原因不能为空")
        return normalized


class ThirdPartyApplicationSafeApp(BaseModel):
    id: str
    client_id: str
    name: str
    status: ThirdPartyAppStatus
    application_source: ThirdPartyAppSource
    approved_scopes: list[str]
    redirect_uris: list[str]
    trusted_verification_enabled: bool


class ThirdPartyApplicationReviewEventResponse(BaseModel):
    id: str
    kind: ThirdPartyApplicationReviewEventKind
    note: str | None
    version: int
    created_at: str


class ThirdPartyApplicationDetail(BaseModel):
    id: str
    name: str
    developer_name: str
    description: str
    website_url: str
    privacy_policy_url: str
    redirect_uris: list[str]
    requested_scopes: list[str]
    windows_release_info: str
    use_case: str
    status: ThirdPartyApplicationRequestStatus
    resubmission_count: int
    current_version: int
    review_note: str | None
    reviewed_at: str | None
    created_at: str
    updated_at: str
    approved_application: ThirdPartyApplicationSafeApp | None
    events: list[ThirdPartyApplicationReviewEventResponse] = Field(default_factory=list)


class ThirdPartyApplicationListResponse(BaseModel):
    items: list[ThirdPartyApplicationDetail]
    page: int
    page_size: int
    total: int


class ThirdPartyApplicationApprovalResponse(BaseModel):
    application: ThirdPartyApplicationDetail
    created_app: ThirdPartyAppListItem
