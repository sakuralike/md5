from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
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


class DesktopPluginStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class DesktopPluginVersionStatus(StrEnum):
    DRAFT = "draft"
    UPLOADING = "uploading"
    QUARANTINED = "quarantined"
    REVIEW_QUEUED = "review_queued"
    AUTO_REVIEW_RUNNING = "auto_review_running"
    AUTO_REVIEW_FAILED = "auto_review_failed"
    MANUAL_REVIEW_READY = "manual_review_ready"
    APPROVED = "approved"
    PUBLISHED = "published"
    YANKED = "yanked"
    REJECTED = "rejected"
    REVOKED = "revoked"


class DesktopPluginSigningKeyStatus(StrEnum):
    ACTIVE = "active"
    ROTATING = "rotating"
    REVOKED = "revoked"


class DesktopPluginArtifactStatus(StrEnum):
    UPLOADING = "uploading"
    QUARANTINED = "quarantined"
    PUBLIC = "public"
    YANKED = "yanked"
    REVOKED = "revoked"


class DesktopPluginUploadSessionStatus(StrEnum):
    OPEN = "open"
    UPLOADED = "uploaded"
    FINALIZED = "finalized"
    EXPIRED = "expired"
    ABORTED = "aborted"


class DesktopPluginArtifactZone(StrEnum):
    QUARANTINE = "quarantine"
    PUBLIC = "public"
    REVOKED = "revoked"


class DesktopPluginRevocationScope(StrEnum):
    PLUGIN = "plugin"
    VERSION = "version"
    SIGNING_KEY = "signing_key"


class DesktopPluginReviewEventKind(StrEnum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    YANKED = "yanked"
    REVOKED = "revoked"


class DesktopPluginPublicationStatus(StrEnum):
    PUBLISHED = "published"
    YANKED = "yanked"


class DesktopPluginReportStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class DesktopPlugin(Base):
    __tablename__ = "desktop_plugins"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_desktop_plugins_slug"),
        Index("ix_desktop_plugins_slug", "slug"),
        Index("ix_desktop_plugins_owner_status", "owner_user_id", "status"),
        Index("ix_desktop_plugins_status_updated", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(128))
    owner_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    linked_third_party_app_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("third_party_apps.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128))
    summary: Mapped[str] = mapped_column(String(320), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="development")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    website_url: Mapped[str | None] = mapped_column(String(2_000), nullable=True)
    privacy_policy_url: Mapped[str | None] = mapped_column(String(2_000), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2_000), nullable=True)
    status: Mapped[DesktopPluginStatus] = mapped_column(
        Enum(DesktopPluginStatus, native_enum=False, length=16),
        default=DesktopPluginStatus.DRAFT,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DesktopPluginSigningKey(Base):
    __tablename__ = "desktop_plugin_signing_keys"
    __table_args__ = (
        UniqueConstraint("key_id", name="uq_desktop_plugin_signing_keys_key_id"),
        UniqueConstraint("fingerprint", name="uq_desktop_plugin_signing_keys_fingerprint"),
        Index("ix_desktop_plugin_signing_keys_owner_status", "owner_user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    rotated_from_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("desktop_plugin_signing_keys.id", ondelete="SET NULL"),
        nullable=True,
    )
    key_id: Mapped[str] = mapped_column(String(128))
    public_key_base64: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[DesktopPluginSigningKeyStatus] = mapped_column(
        Enum(DesktopPluginSigningKeyStatus, native_enum=False, length=16),
        default=DesktopPluginSigningKeyStatus.ACTIVE,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DesktopPluginVersion(Base):
    __tablename__ = "desktop_plugin_versions"
    __table_args__ = (
        UniqueConstraint("plugin_id", "semver", name="uq_desktop_plugin_versions_plugin_semver"),
        Index("ix_desktop_plugin_versions_plugin_status", "plugin_id", "status"),
        Index("ix_desktop_plugin_versions_status_published", "status", "published_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plugin_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("desktop_plugins.id", ondelete="CASCADE"), index=True
    )
    semver: Mapped[str] = mapped_column(String(32))
    status: Mapped[DesktopPluginVersionStatus] = mapped_column(
        Enum(DesktopPluginVersionStatus, native_enum=False, length=24),
        default=DesktopPluginVersionStatus.DRAFT,
        index=True,
    )
    signing_key_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("desktop_plugin_signing_keys.id", ondelete="RESTRICT"), index=True
    )
    signing_key_fingerprint: Mapped[str] = mapped_column(String(64))
    manifest_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    manifest_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    protocol_min: Mapped[int] = mapped_column(Integer, default=1)
    protocol_max: Mapped[int] = mapped_column(Integer, default=1)
    host_min: Mapped[str] = mapped_column(String(32), default="0.1.0")
    host_max: Mapped[str] = mapped_column(String(32), default="0.x")
    requested_capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    approved_capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    risk_tier: Mapped[str] = mapped_column(String(16), default="standard")
    release_notes: Mapped[str] = mapped_column(Text, default="")
    source_review_mode: Mapped[str] = mapped_column(String(32), default="binary_only")
    reviewer_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    review_policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    platform_key_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform_public_key_base64: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform_signature_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    yanked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DesktopPluginArtifact(Base):
    __tablename__ = "desktop_plugin_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "plugin_version_id", "architecture", name="uq_desktop_plugin_artifacts_version_arch"
        ),
        Index("ix_desktop_plugin_artifacts_status_zone", "status", "zone"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plugin_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("desktop_plugin_versions.id", ondelete="CASCADE"), index=True
    )
    architecture: Mapped[str] = mapped_column(String(16))
    runtime: Mapped[str] = mapped_column(String(32), default="process")
    status: Mapped[DesktopPluginArtifactStatus] = mapped_column(
        Enum(DesktopPluginArtifactStatus, native_enum=False, length=16),
        default=DesktopPluginArtifactStatus.UPLOADING,
        index=True,
    )
    zone: Mapped[DesktopPluginArtifactZone] = mapped_column(
        Enum(DesktopPluginArtifactZone, native_enum=False, length=16),
        default=DesktopPluginArtifactZone.QUARANTINE,
    )
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    public_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    artifact_filename: Mapped[str] = mapped_column(String(255), default="plugin.pdpkg")
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    expanded_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    developer_signature_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DesktopPluginUploadSession(Base):
    __tablename__ = "desktop_plugin_upload_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_desktop_plugin_upload_sessions_token_hash"),
        Index("ix_desktop_plugin_upload_sessions_version_status", "plugin_version_id", "status"),
        Index("ix_desktop_plugin_upload_sessions_expires_status", "expires_at", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plugin_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("desktop_plugin_versions.id", ondelete="CASCADE"), index=True
    )
    artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("desktop_plugin_artifacts.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64))
    expected_size_bytes: Mapped[int] = mapped_column(BigInteger)
    expected_sha256: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[DesktopPluginUploadSessionStatus] = mapped_column(
        Enum(DesktopPluginUploadSessionStatus, native_enum=False, length=16),
        default=DesktopPluginUploadSessionStatus.OPEN,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DesktopPluginDownloadTicket(Base):
    __tablename__ = "desktop_plugin_download_tickets"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_desktop_plugin_download_tickets_token_hash"),
        Index("ix_desktop_plugin_download_tickets_expires", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("desktop_plugin_artifacts.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DesktopPluginRevocation(Base):
    __tablename__ = "desktop_plugin_revocations"
    __table_args__ = (
        CheckConstraint(
            "(plugin_id IS NOT NULL AND plugin_version_id IS NULL AND signing_key_id IS NULL) OR "
            "(plugin_id IS NULL AND plugin_version_id IS NOT NULL AND signing_key_id IS NULL) OR "
            "(plugin_id IS NULL AND plugin_version_id IS NULL AND signing_key_id IS NOT NULL)",
            name="ck_desktop_plugin_revocations_single_target",
        ),
        Index("ix_desktop_plugin_revocations_effective", "effective_at", "created_at"),
        Index("ix_desktop_plugin_revocations_scope_effective", "scope", "effective_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scope: Mapped[DesktopPluginRevocationScope] = mapped_column(
        Enum(DesktopPluginRevocationScope, native_enum=False, length=16), index=True
    )
    plugin_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("desktop_plugins.id", ondelete="CASCADE"), nullable=True, index=True
    )
    plugin_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("desktop_plugin_versions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    signing_key_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("desktop_plugin_signing_keys.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    reason_code: Mapped[str] = mapped_column(String(64))
    affects_historical_versions: Mapped[bool] = mapped_column(Boolean, default=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    platform_key_id: Mapped[str] = mapped_column(String(128))
    platform_public_key_base64: Mapped[str] = mapped_column(String(128))
    platform_signature_base64: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DesktopPluginReviewEvent(Base):
    __tablename__ = "desktop_plugin_review_events"
    __table_args__ = (
        Index("ix_desktop_plugin_review_events_version_created", "version_id", "created_at"),
        Index("ix_desktop_plugin_review_events_kind_created", "kind", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("desktop_plugin_versions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[DesktopPluginReviewEventKind] = mapped_column(
        Enum(DesktopPluginReviewEventKind, native_enum=False, length=16), index=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    approved_capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    version_number: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DesktopPluginPublication(Base):
    __tablename__ = "desktop_plugin_publications"
    __table_args__ = (
        UniqueConstraint(
            "version_id", "channel", name="uq_desktop_plugin_publications_version_channel"
        ),
        Index("ix_desktop_plugin_publications_channel_status", "channel", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("desktop_plugin_versions.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(32), default="stable")
    status: Mapped[DesktopPluginPublicationStatus] = mapped_column(
        Enum(DesktopPluginPublicationStatus, native_enum=False, length=16),
        default=DesktopPluginPublicationStatus.PUBLISHED,
        index=True,
    )
    published_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT")
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    yanked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    yanked_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class DesktopPluginReport(Base):
    __tablename__ = "desktop_plugin_reports"
    __table_args__ = (
        Index("ix_desktop_plugin_reports_status_created", "status", "created_at"),
        Index("ix_desktop_plugin_reports_plugin_status", "plugin_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plugin_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("desktop_plugins.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("desktop_plugin_versions.id", ondelete="SET NULL"), nullable=True
    )
    reporter_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[DesktopPluginReportStatus] = mapped_column(
        Enum(DesktopPluginReportStatus, native_enum=False, length=16),
        default=DesktopPluginReportStatus.OPEN,
        index=True,
    )
    reviewer_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
