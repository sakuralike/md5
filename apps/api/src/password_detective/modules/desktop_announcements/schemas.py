from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from password_detective.db.models.desktop_announcement import (
    DesktopAnnouncementContentType,
    DesktopAnnouncementStatus,
)


def _validate_http_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip()
    if not normalized.startswith(("http://", "https://")):
        raise ValueError("地址必须使用 http:// 或 https://")
    return normalized


class DesktopAnnouncementWriteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=20_000)
    content_type: DesktopAnnouncementContentType = DesktopAnnouncementContentType.TEXT
    image_urls: list[str] = Field(default_factory=list, max_length=8)
    action_label: str | None = Field(default=None, max_length=64)
    action_url: str | None = Field(default=None, max_length=2_000)
    sort_order: int = Field(default=0, ge=-10_000, le=10_000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("title", "content")
    @classmethod
    def strip_required(cls, value: str) -> str:
        return value.strip()

    @field_validator("action_label")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @field_validator("action_url")
    @classmethod
    def validate_action_url(cls, value: str | None) -> str | None:
        return _validate_http_url(value)

    @field_validator("image_urls")
    @classmethod
    def validate_image_urls(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            candidate = value.strip()
            if not candidate:
                continue
            if candidate.startswith("/api/v1/desktop/announcements/assets/"):
                if candidate not in normalized:
                    normalized.append(candidate)
                continue
            url = _validate_http_url(candidate)
            if url and url not in normalized:
                normalized.append(url)
        return normalized

    @model_validator(mode="after")
    def validate_window(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("结束时间必须晚于开始时间")
        if self.action_url and not self.action_label:
            raise ValueError("配置跳转地址时必须填写按钮文字")
        return self


class DesktopAnnouncementResponse(BaseModel):
    id: str
    title: str
    content: str
    content_type: DesktopAnnouncementContentType
    image_urls: list[str]
    action_label: str | None
    action_url: str | None
    sort_order: int
    starts_at: datetime | None
    ends_at: datetime | None
    status: DesktopAnnouncementStatus
    revision: int
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    archived_at: datetime | None


class DesktopAnnouncementListResponse(BaseModel):
    items: list[DesktopAnnouncementResponse]


class DesktopAnnouncementImageUploadResponse(BaseModel):
    url: str
    content_type: str
    size_bytes: int
    sha256: str
