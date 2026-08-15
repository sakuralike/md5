from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base
from password_detective.db.models.archive_fingerprint import FingerprintAlgorithm
from password_detective.db.models.verification import FeedbackOutcome


class InstallationStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class ReceiptProtocol(StrEnum):
    OFFICIAL_DESKTOP_V1 = "desktop-receipt-v1"
    THIRD_PARTY_DESKTOP_V1 = "third-party-desktop-receipt-v1"


class VerificationTrustChannel(StrEnum):
    OFFICIAL_DESKTOP = "official_desktop"
    THIRD_PARTY_PENDING = "third_party_pending"
    THIRD_PARTY_TRUSTED = "third_party_trusted"


class ClientInstallation(Base):
    __tablename__ = "client_installations"
    __table_args__ = (
        UniqueConstraint(
            "public_key_fingerprint",
            name="uq_client_installations_public_key_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    third_party_app_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("third_party_apps.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    receipt_protocol: Mapped[str] = mapped_column(
        String(48), default=ReceiptProtocol.OFFICIAL_DESKTOP_V1.value, index=True
    )
    operating_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    architecture: Mapped[str | None] = mapped_column(String(32), nullable=True)
    public_key_der: Mapped[bytes] = mapped_column(LargeBinary)
    public_key_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    key_algorithm: Mapped[str] = mapped_column(String(32), default="ecdsa-p256-sha256")
    status: Mapped[InstallationStatus] = mapped_column(
        Enum(InstallationStatus, native_enum=False, length=16),
        default=InstallationStatus.ACTIVE,
        index=True,
    )
    client_version: Mapped[str] = mapped_column(String(32))
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    receipt_count: Mapped[int] = mapped_column(Integer, default=0)
    first_ip_prefix: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_ip_prefix: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VerificationChallenge(Base):
    __tablename__ = "verification_challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    installation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("client_installations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    third_party_app_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("third_party_apps.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    receipt_protocol: Mapped[str] = mapped_column(
        String(48), default=ReceiptProtocol.OFFICIAL_DESKTOP_V1.value, index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("password_candidates.id", ondelete="CASCADE"), index=True
    )
    nonce_hash: Mapped[str] = mapped_column(String(64), unique=True)
    fingerprint_algorithm: Mapped[FingerprintAlgorithm] = mapped_column(
        Enum(FingerprintAlgorithm, native_enum=False, length=16)
    )
    fingerprint_digest: Mapped[str] = mapped_column(String(128))
    client_version: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class VerificationReceipt(Base):
    __tablename__ = "verification_receipts"
    __table_args__ = (
        UniqueConstraint("challenge_id", name="uq_verification_receipts_challenge_id"),
        UniqueConstraint("canonical_payload_hash", name="uq_verification_receipts_payload_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    challenge_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("verification_challenges.id", ondelete="CASCADE"), index=True
    )
    installation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("client_installations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    third_party_app_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("third_party_apps.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    receipt_protocol: Mapped[str] = mapped_column(
        String(48), default=ReceiptProtocol.OFFICIAL_DESKTOP_V1.value, index=True
    )
    trust_channel: Mapped[str] = mapped_column(
        String(32), default=VerificationTrustChannel.OFFICIAL_DESKTOP.value, index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("password_candidates.id", ondelete="CASCADE"), index=True
    )
    outcome: Mapped[FeedbackOutcome] = mapped_column(
        Enum(FeedbackOutcome, native_enum=False, length=16), index=True
    )
    archive_format: Mapped[str] = mapped_column(String(16))
    fingerprint_algorithm: Mapped[FingerprintAlgorithm] = mapped_column(
        Enum(FingerprintAlgorithm, native_enum=False, length=16)
    )
    fingerprint_digest: Mapped[str] = mapped_column(String(128))
    candidate_digest_hash: Mapped[str] = mapped_column(String(64))
    client_version: Mapped[str] = mapped_column(String(32))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    canonical_payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    signature: Mapped[str] = mapped_column(Text)
    evidence_event_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("verification_evidence_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
