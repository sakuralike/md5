from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from password_detective.db.models.setting_version import SettingVersionStatus


class SettingChangeReasonCode(StrEnum):
    SECURITY_HARDENING = "security_hardening"
    CAPACITY_ADJUSTMENT = "capacity_adjustment"
    PRODUCT_POLICY = "product_policy"
    INCIDENT_RESPONSE = "incident_response"
    ROLLBACK = "rollback"


class OperationalSettingsSnapshot(BaseModel):
    daily_reveal_quota: int = Field(ge=1, le=1000)
    reauthentication_ttl_minutes: int = Field(ge=1, le=15)
    privacy_deletion_grace_hours: int = Field(ge=1, le=720)
    desktop_min_client_version: str = Field(min_length=5, max_length=32)
    desktop_update_download_cache_seconds: int = Field(ge=60, le=31_536_000)

    @field_validator("desktop_min_client_version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) != 3 or any(not part.isdigit() for part in parts):
            raise ValueError("桌面最低版本必须使用 x.y.z 格式")
        return value


class SettingVersionCreateRequest(BaseModel):
    expected_base_version_id: str | None = Field(default=None, max_length=36)
    reason_code: SettingChangeReasonCode
    snapshot: OperationalSettingsSnapshot


class SettingVersionPublishRequest(BaseModel):
    expected_published_version_id: str | None = Field(default=None, max_length=36)
    reason_code: SettingChangeReasonCode
    reauth_token: str = Field(min_length=16, max_length=256)


class SettingVersionRollbackRequest(BaseModel):
    expected_published_version_id: str = Field(max_length=36)
    reason_code: SettingChangeReasonCode = SettingChangeReasonCode.ROLLBACK
    reauth_token: str = Field(min_length=16, max_length=256)


class SettingDifference(BaseModel):
    key: str
    previous: int | str | None
    current: int | str


class SettingVersionSummary(BaseModel):
    id: str
    status: SettingVersionStatus
    schema_version: str
    snapshot_hash: str
    base_version_id: str | None
    rollback_of_id: str | None
    reason_code: str
    created_by: str
    published_by: str | None
    created_at: datetime
    published_at: datetime | None
    effective_at: datetime | None


class SettingVersionDetail(SettingVersionSummary):
    snapshot: OperationalSettingsSnapshot
    differences: list[SettingDifference]


class SettingVersionListResponse(BaseModel):
    items: list[SettingVersionSummary]
    page: int
    page_size: int
    total: int
    published_version_id: str | None


class SettingVersionMutationResponse(BaseModel):
    version: SettingVersionDetail
    audit_id: str
    request_id: str | None
