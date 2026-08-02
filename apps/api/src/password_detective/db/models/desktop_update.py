from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class DesktopReleaseChannel(StrEnum):
    STABLE = "stable"
    BETA = "beta"


class DesktopArchitecture(StrEnum):
    X64 = "x64"
    ARM64 = "arm64"


class DesktopReleaseStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


class CodeSignatureStatus(StrEnum):
    UNSIGNED = "unsigned"
    TEST_SIGNED = "test_signed"
    VERIFIED = "verified"


class DesktopRelease(Base):
    __tablename__ = "desktop_releases"
    __table_args__ = (
        UniqueConstraint(
            "channel",
            "platform",
            "architecture",
            "version",
            name="uq_desktop_releases_target_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    channel: Mapped[DesktopReleaseChannel] = mapped_column(
        Enum(DesktopReleaseChannel, native_enum=False, length=16), index=True
    )
    platform: Mapped[str] = mapped_column(String(16), default="windows", index=True)
    architecture: Mapped[DesktopArchitecture] = mapped_column(
        Enum(DesktopArchitecture, native_enum=False, length=16), index=True
    )
    version: Mapped[str] = mapped_column(String(32), index=True)
    minimum_supported_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[DesktopReleaseStatus] = mapped_column(
        Enum(DesktopReleaseStatus, native_enum=False, length=16),
        default=DesktopReleaseStatus.DRAFT,
        index=True,
    )
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    release_notes: Mapped[str] = mapped_column(Text, default="")
    artifact_filename: Mapped[str] = mapped_column(String(255))
    artifact_storage_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
    artifact_sha256: Mapped[str] = mapped_column(String(64))
    artifact_size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    code_signature_status: Mapped[CodeSignatureStatus] = mapped_column(
        Enum(CodeSignatureStatus, native_enum=False, length=24),
        default=CodeSignatureStatus.UNSIGNED,
    )
    signer_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signer_thumbprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
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
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
