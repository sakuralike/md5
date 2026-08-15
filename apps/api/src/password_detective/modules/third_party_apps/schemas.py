from __future__ import annotations

from pydantic import BaseModel, Field

from password_detective.db.models.third_party_app import ThirdPartyAppSource, ThirdPartyAppStatus


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
