from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class WebAnnouncementStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class WebAnnouncementContentType(StrEnum):
    TEXT = "text"
    HTML = "html"


class WebAnnouncement(Base):
    __tablename__ = "web_announcements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text)
    content_type: Mapped[WebAnnouncementContentType] = mapped_column(
        Enum(WebAnnouncementContentType, native_enum=False, length=16),
        default=WebAnnouncementContentType.TEXT,
    )
    image_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    action_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action_url: Mapped[str | None] = mapped_column(String(2_000), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    auto_close_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[WebAnnouncementStatus] = mapped_column(
        Enum(WebAnnouncementStatus, native_enum=False, length=16),
        default=WebAnnouncementStatus.DRAFT,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
