from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from password_detective.db.models.desktop_update import DesktopArchitecture, DesktopReleaseChannel


class ThirdPartyUpdateCheckResponse(BaseModel):
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
    artifact_integrity: str | None
