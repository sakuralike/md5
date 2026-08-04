from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class SettingVersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"


class SystemSettingVersion(Base):
    __tablename__ = "system_setting_versions"
    __table_args__ = (
        Index("ix_system_setting_versions_status_created", "status", "created_at"),
        Index("ix_system_setting_versions_published_at", "published_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    status: Mapped[SettingVersionStatus] = mapped_column(String(24), index=True)
    schema_version: Mapped[str] = mapped_column(String(32), default="operational-v1")
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    base_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("system_setting_versions.id", ondelete="SET NULL"), nullable=True
    )
    rollback_of_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("system_setting_versions.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    published_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    reason_code: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
