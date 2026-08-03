from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from password_detective.db.models.authorization_declaration import AuthorizationSource
from password_detective.db.models.privacy_request import (
    PrivacyDeletionStatus,
    PrivacyExportStatus,
)


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int


class RevealHistoryItem(BaseModel):
    audit_id: str
    archive_id: str | None
    fingerprint_summary: list[str]
    result: str
    revealed_at: datetime


class RevealHistoryResponse(Pagination):
    items: list[RevealHistoryItem]


class AuthorizationDeclarationCreateRequest(BaseModel):
    purpose: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    source: AuthorizationSource = AuthorizationSource.WEB
    accepted: Literal[True]


class AuthorizationDeclarationResponse(BaseModel):
    id: str
    declaration_version: str
    purpose: str
    source: AuthorizationSource
    confirmed_at: datetime
    withdrawn_at: datetime | None
    active: bool


class AuthorizationDeclarationListResponse(Pagination):
    items: list[AuthorizationDeclarationResponse]


class PrivacyExportResponse(BaseModel):
    id: str
    status: PrivacyExportStatus
    requested_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None
    downloaded_at: datetime | None
    download_available: bool
    download_token: str | None = None
    artifact_sha256: str | None = None
    failure_code: str | None = None


class PrivacyExportDownloadRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class PrivacyDeletionCreateRequest(BaseModel):
    reauth_token: str = Field(min_length=32, max_length=256)


class PrivacyDeletionResponse(BaseModel):
    id: str
    status: PrivacyDeletionStatus
    requested_at: datetime
    cancel_before: datetime
    cancelled_at: datetime | None
    processing_started_at: datetime | None
    completed_at: datetime | None
    can_cancel: bool
