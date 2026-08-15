from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class ThirdPartyAppStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class ThirdPartyAppSource(StrEnum):
    ADMIN = "admin"
    DEVELOPER_SELF_SERVICE = "developer_self_service"


class ThirdPartyApp(Base):
    __tablename__ = "third_party_apps"
    __table_args__ = (
        Index("ix_third_party_apps_status_created", "status", "created_at"),
        Index("ix_third_party_apps_submitted_by_status", "submitted_by_user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    management_secret_hash: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    developer_name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ThirdPartyAppStatus] = mapped_column(
        Enum(ThirdPartyAppStatus, native_enum=False, length=24),
        default=ThirdPartyAppStatus.DRAFT,
        index=True,
    )
    application_source: Mapped[ThirdPartyAppSource] = mapped_column(
        Enum(ThirdPartyAppSource, native_enum=False, length=32),
        default=ThirdPartyAppSource.ADMIN,
        index=True,
    )
    requested_scopes_json: Mapped[str] = mapped_column(Text, default="[]")
    approved_scopes_json: Mapped[str] = mapped_column(Text, default="[]")
    submitted_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewer_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    trusted_verification_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ThirdPartyAppRedirectUri(Base):
    __tablename__ = "third_party_app_redirect_uris"
    __table_args__ = (
        UniqueConstraint(
            "app_id", "redirect_uri_hash", name="uq_third_party_app_redirect_uri_hash"
        ),
        Index("ix_third_party_app_redirect_uris_app_id", "app_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    app_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("third_party_apps.id", ondelete="CASCADE")
    )
    redirect_uri: Mapped[str] = mapped_column(String(2_000))
    redirect_uri_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

