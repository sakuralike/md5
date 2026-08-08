from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class TrustCaseKind(StrEnum):
    REPORT = "report"
    APPEAL = "appeal"
    ACCOUNT_APPEAL = "account_appeal"


class TrustCaseSubjectType(StrEnum):
    CANDIDATE = "candidate"
    ACCOUNT = "account"
    RISK_ALERT = "risk_alert"


class TrustCaseNotificationKind(StrEnum):
    RESOLUTION = "resolution"


class TrustCaseNotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class TrustCaseStatus(StrEnum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class TrustCase(Base):
    __tablename__ = "trust_cases"
    __table_args__ = (
        CheckConstraint(
            "(subject_type = 'CANDIDATE' AND candidate_id IS NOT NULL "
            "AND target_user_id IS NULL AND risk_alert_id IS NULL) OR "
            "(subject_type = 'ACCOUNT' AND candidate_id IS NULL "
            "AND target_user_id IS NOT NULL AND risk_alert_id IS NULL) OR "
            "(subject_type = 'RISK_ALERT' AND candidate_id IS NULL "
            "AND target_user_id IS NULL AND risk_alert_id IS NOT NULL)",
            name="ck_trust_cases_single_subject",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[TrustCaseKind] = mapped_column(
        Enum(TrustCaseKind, native_enum=False, length=16), index=True
    )
    subject_type: Mapped[TrustCaseSubjectType] = mapped_column(
        Enum(TrustCaseSubjectType, native_enum=False, length=16), index=True
    )
    status: Mapped[TrustCaseStatus] = mapped_column(
        Enum(TrustCaseStatus, native_enum=False, length=16),
        default=TrustCaseStatus.OPEN,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reporter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    candidate_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("password_candidates.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    target_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    risk_alert_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("risk_alerts.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    related_case_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trust_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reason_code: Mapped[str] = mapped_column(String(64), index=True)
    requested_action: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resolved_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resolution_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    candidate = relationship("PasswordCandidate")
    target_user = relationship("User", foreign_keys=[target_user_id])
    risk_alert = relationship("RiskAlert")
    events = relationship(
        "TrustCaseEvent",
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="TrustCaseEvent.created_at",
    )
    notifications = relationship(
        "TrustCaseNotification",
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="TrustCaseNotification.created_at",
    )


class TrustCaseEffectType(StrEnum):
    ACCOUNT_STATUS = "account_status"
    CANDIDATE_STATUS = "candidate_status"
    REWARD_RECONCILIATION = "reward_reconciliation"


class TrustCaseEffect(Base):
    """Append-only record of side effects applied by an atomic case resolution."""

    __tablename__ = "trust_case_effects"
    __table_args__ = (
        UniqueConstraint(
            "case_id", "case_version", "effect_type", name="uq_trust_case_effect_version_type"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trust_cases.id", ondelete="CASCADE"), index=True
    )
    case_version: Mapped[int] = mapped_column(Integer)
    effect_type: Mapped[TrustCaseEffectType] = mapped_column(
        Enum(TrustCaseEffectType, native_enum=False, length=32), index=True
    )
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    previous_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class TrustCaseNotification(Base):
    """Transactional outbox entry for minimum-disclosure case result notifications."""

    __tablename__ = "trust_case_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trust_cases.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trust_case_events.id", ondelete="SET NULL"), nullable=True
    )
    recipient_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[TrustCaseNotificationKind] = mapped_column(
        Enum(TrustCaseNotificationKind, native_enum=False, length=32), index=True
    )
    status: Mapped[TrustCaseNotificationStatus] = mapped_column(
        Enum(TrustCaseNotificationStatus, native_enum=False, length=16),
        default=TrustCaseNotificationStatus.PENDING,
        index=True,
    )
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    replay_count: Mapped[int] = mapped_column(Integer, default=0)
    last_replayed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_replayed_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    case = relationship("TrustCase", back_populates="notifications")
    recipient = relationship("User", foreign_keys=[recipient_user_id])
    last_replayed_by = relationship("User", foreign_keys=[last_replayed_by_id])


class TrustCaseEvent(Base):
    __tablename__ = "trust_case_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trust_cases.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    previous_status: Mapped[TrustCaseStatus | None] = mapped_column(
        Enum(TrustCaseStatus, native_enum=False, length=16), nullable=True
    )
    previous_assignee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    next_status: Mapped[TrustCaseStatus] = mapped_column(
        Enum(TrustCaseStatus, native_enum=False, length=16)
    )
    next_assignee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )

    case = relationship("TrustCase", back_populates="events")
