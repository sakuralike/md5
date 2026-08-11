from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from password_detective.db.models.desktop_update import (
    DesktopArchitecture,
    DesktopReleaseChannel,
    DesktopReleaseStatus,
)

DesktopPlatform = Literal["windows"]


class DesktopReleaseCreateRequest(BaseModel):
    channel: DesktopReleaseChannel = DesktopReleaseChannel.STABLE
    platform: DesktopPlatform = "windows"
    architecture: DesktopArchitecture
    version: str = Field(min_length=5, max_length=32)
    minimum_supported_version: str = Field(min_length=5, max_length=32)
    mandatory: bool = False
    release_notes: str = Field(default="", max_length=20_000)
    artifact_filename: str = Field(min_length=1, max_length=255)
    artifact_sha256: str = Field(min_length=64, max_length=64)
    artifact_size_bytes: int = Field(gt=0)
    content_type: str = Field(default="application/octet-stream", min_length=3, max_length=128)
    distribution_authorized: bool
    legal_declaration: str = Field(min_length=20, max_length=2_000)

    @field_validator("artifact_sha256")
    @classmethod
    def normalize_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("artifact_sha256 必须是十六进制 SHA-256")
        return normalized

    @field_validator("legal_declaration")
    @classmethod
    def normalize_legal_declaration(cls, value: str) -> str:
        return value.strip()


class DesktopReleaseResponse(BaseModel):
    id: str
    channel: DesktopReleaseChannel
    platform: str
    architecture: DesktopArchitecture
    version: str
    minimum_supported_version: str
    status: DesktopReleaseStatus
    mandatory: bool
    release_notes: str
    artifact_filename: str
    artifact_sha256: str
    artifact_size_bytes: int
    content_type: str
    artifact_uploaded: bool
    distribution_authorized: bool
    legal_declaration: str
    download_count: int
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    withdrawn_at: datetime | None


class DesktopReleaseListResponse(BaseModel):
    items: list[DesktopReleaseResponse]


class DesktopUpdateCheckResponse(BaseModel):
    update_available: bool
    mandatory: bool
    current_version: str
    latest_version: str | None
    minimum_supported_version: str | None
    channel: DesktopReleaseChannel
    platform: str
    architecture: DesktopArchitecture
    release_id: str | None
    release_notes: str
    published_at: datetime | None
    download_url: str | None
    artifact_filename: str | None
    artifact_sha256: str | None
    artifact_size_bytes: int | None
    artifact_integrity: Literal["sha256-verified"] | None
    distribution_authorized: bool | None
