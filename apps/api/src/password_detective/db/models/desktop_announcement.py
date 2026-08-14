from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class DesktopAnnouncementStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class DesktopAnnouncementContentType(StrEnum):
    TEXT = "text"
    HTML = "html"


class DesktopAnnouncement(Base):
    __tablename__ = "desktop_announcements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text)
    content_type: Mapped[DesktopAnnouncementContentType] = mapped_column(
        Enum(DesktopAnnouncementContentType, native_enum=False, length=16),
        default=DesktopAnnouncementContentType.TEXT,
    )
    image_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    action_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action_url: Mapped[str | None] = mapped_column(String(2_000), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[DesktopAnnouncementStatus] = mapped_column(
        Enum(DesktopAnnouncementStatus, native_enum=False, length=16),
        default=DesktopAnnouncementStatus.DRAFT,
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
