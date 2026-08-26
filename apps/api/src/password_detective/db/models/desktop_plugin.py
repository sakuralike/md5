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
    WITHDRAWN = "withdrawn"
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
    WITHDRAWN = "withdrawn"
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


class DesktopPluginReviewRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    INFRASTRUCTURE_FAILED = "infrastructure_failed"
    CANCELLED = "cancelled"


class DesktopPluginReviewStage(StrEnum):
    STRUCTURE = "structure"
    SIGNATURE = "signature"
    SBOM = "sbom"
    VULNERABILITY = "vulnerability"
    LICENSE = "license"
    SECRET = "secret"
    STATIC_BEHAVIOR = "static_behavior"
    PE_ANALYSIS = "pe_analysis"
    DYNAMIC_PROTOCOL = "dynamic_protocol"
    DYNAMIC_RESOURCE = "dynamic_resource"
    DYNAMIC_FILE = "dynamic_file"
    DYNAMIC_PROCESS = "dynamic_process"
    DYNAMIC_NETWORK = "dynamic_network"
    DYNAMIC_CLEANUP = "dynamic_cleanup"


class DesktopPluginFindingSeverity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DesktopPluginRunnerStatus(StrEnum):
    READY = "ready"
    BUSY = "busy"
    OFFLINE = "offline"
    REVOKED = "revoked"


class DesktopPluginDynamicTaskStatus(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    PASSED = "passed"
    BLOCKED = "blocked"
    INFRASTRUCTURE_FAILED = "infrastructure_failed"
    CANCELLED = "cancelled"


class DesktopPluginInstallEventKind(StrEnum):
    INSTALLED = "installed"
    UPGRADED = "upgraded"
    ROLLED_BACK = "rolled_back"
    ENABLED = "enabled"
    DISABLED = "disabled"
    UNINSTALLED = "uninstalled"
    DOWNLOAD_FAILED = "download_failed"


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
    remediation_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


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


class DesktopPluginReviewRun(Base):
    __tablename__ = "desktop_plugin_review_runs"
    __table_args__ = (
        Index("ix_desktop_plugin_review_runs_version_created", "version_id", "created_at"),
        Index("ix_desktop_plugin_review_runs_status_lease", "status", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("desktop_plugin_versions.id", ondelete="CASCADE"), index=True
    )
    policy_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[DesktopPluginReviewRunStatus] = mapped_column(
        Enum(DesktopPluginReviewRunStatus, native_enum=False, length=32),
        default=DesktopPluginReviewRunStatus.QUEUED,
        index=True,
    )
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DesktopPluginReviewFinding(Base):
    __tablename__ = "desktop_plugin_review_findings"
    __table_args__ = (
        Index("ix_desktop_plugin_review_findings_run_created", "review_run_id", "created_at"),
        Index("ix_desktop_plugin_review_findings_rule_severity", "rule_id", "severity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    review_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("desktop_plugin_review_runs.id", ondelete="CASCADE"), index=True
    )
    dynamic_task_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("desktop_plugin_dynamic_review_tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    stage: Mapped[DesktopPluginReviewStage] = mapped_column(
        Enum(DesktopPluginReviewStage, native_enum=False, length=32), index=True
    )
    rule_id: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[DesktopPluginFindingSeverity] = mapped_column(
        Enum(DesktopPluginFindingSeverity, native_enum=False, length=16), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    developer_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DesktopPluginRunnerAgent(Base):
    __tablename__ = "desktop_plugin_runner_agents"
    __table_args__ = (
        UniqueConstraint("certificate_fingerprint", name="uq_desktop_plugin_runner_certificate"),
        Index("ix_desktop_plugin_runner_status_heartbeat", "status", "last_heartbeat_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128))
    architecture: Mapped[str] = mapped_column(String(16), index=True)
    certificate_fingerprint: Mapped[str] = mapped_column(String(64))
    secret_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[DesktopPluginRunnerStatus] = mapped_column(
        Enum(DesktopPluginRunnerStatus, native_enum=False, length=16),
        default=DesktopPluginRunnerStatus.OFFLINE,
        index=True,
    )
    policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    probe_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DesktopPluginDynamicReviewTask(Base):
    __tablename__ = "desktop_plugin_dynamic_review_tasks"
    __table_args__ = (
        UniqueConstraint(
            "review_run_id", "artifact_id", name="uq_desktop_plugin_dynamic_task_run_artifact"
        ),
        Index("ix_desktop_plugin_dynamic_task_status_lease", "status", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    review_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("desktop_plugin_review_runs.id", ondelete="CASCADE"), index=True
    )
    artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("desktop_plugin_artifacts.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[DesktopPluginDynamicTaskStatus] = mapped_column(
        Enum(DesktopPluginDynamicTaskStatus, native_enum=False, length=32),
        default=DesktopPluginDynamicTaskStatus.QUEUED,
        index=True,
    )
    runner_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("desktop_plugin_runner_agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    task_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    task_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    fresh_environment: Mapped[bool] = mapped_column(Boolean, default=False)
    destruction_proof_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DesktopPluginInstallEvent(Base):
    __tablename__ = "desktop_plugin_install_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_desktop_plugin_install_events_event_id"),
        Index("ix_desktop_plugin_install_events_plugin_created", "plugin_slug", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(String(64))
    plugin_slug: Mapped[str] = mapped_column(String(128), index=True)
    semver: Mapped[str] = mapped_column(String(32))
    architecture: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(32))
    kind: Mapped[DesktopPluginInstallEventKind] = mapped_column(
        Enum(DesktopPluginInstallEventKind, native_enum=False, length=24), index=True
    )
    result: Mapped[str] = mapped_column(String(32), default="success")
    client_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
