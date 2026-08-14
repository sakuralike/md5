from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from password_detective.db.models.web_announcement import (
    WebAnnouncementContentType,
    WebAnnouncementStatus,
)


def _validate_http_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip()
    if not normalized.startswith(("http://", "https://")):
        raise ValueError("地址必须使用 http:// 或 https://")
    return normalized


class WebAnnouncementWriteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=20_000)
    content_type: WebAnnouncementContentType = WebAnnouncementContentType.TEXT
    image_urls: list[str] = Field(default_factory=list, max_length=8)
    action_label: str | None = Field(default=None, max_length=64)
    action_url: str | None = Field(default=None, max_length=2_000)
    sort_order: int = Field(default=0, ge=-10_000, le=10_000)
    auto_close_seconds: int | None = Field(default=10, ge=1, le=86_400)
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
            if candidate.startswith("/api/v1/web/announcements/assets/"):
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
        return self


class WebAnnouncementResponse(BaseModel):
    id: str
    title: str
    content: str
    content_type: WebAnnouncementContentType
    image_urls: list[str]
    action_label: str | None
    action_url: str | None
    sort_order: int
    auto_close_seconds: int | None
    starts_at: datetime | None
    ends_at: datetime | None
    status: WebAnnouncementStatus
    revision: int
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    archived_at: datetime | None


class WebAnnouncementListResponse(BaseModel):
    items: list[WebAnnouncementResponse]


class WebAnnouncementImageUploadResponse(BaseModel):
    url: str
    content_type: str
    size_bytes: int
    sha256: str
