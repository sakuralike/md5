from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class RiskAlertKind(StrEnum):
    FAILURE_SURGE = "failure_surge"


class RiskAlertSeverity(StrEnum):
    HIGH = "high"


class RiskAlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class RiskAlertNotificationKind(StrEnum):
    DETECTED = "detected"
    ASSIGNED = "assigned"
    ACKNOWLEDGEMENT_OVERDUE = "acknowledgement_overdue"
    RESOLUTION_OVERDUE = "resolution_overdue"
    RESOLVED = "resolved"
    REOPENED = "reopened"


class RiskAlertNotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class RiskAlert(Base):
    """Current risk-alert projection. Detection and handling history lives in events."""

    __tablename__ = "risk_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("password_candidates.id", ondelete="CASCADE"), index=True
    )
    trigger_evidence_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("verification_evidence_events.id", ondelete="RESTRICT"),
        unique=True,
    )
    kind: Mapped[RiskAlertKind] = mapped_column(
        Enum(RiskAlertKind, native_enum=False, length=32), index=True
    )
    severity: Mapped[RiskAlertSeverity] = mapped_column(
        Enum(RiskAlertSeverity, native_enum=False, length=16), index=True
    )
    status: Mapped[RiskAlertStatus] = mapped_column(
        Enum(RiskAlertStatus, native_enum=False, length=16),
        default=RiskAlertStatus.OPEN,
        index=True,
    )
    rule_version: Mapped[str] = mapped_column(String(32), index=True)
    sla_rule_version: Mapped[str] = mapped_column(String(32), index=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledge_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolve_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    independent_failure_count: Mapped[int] = mapped_column(Integer)
    failure_weight: Mapped[float] = mapped_column(Float)
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
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
    resolved_by = relationship("User", foreign_keys=[resolved_by_id])
    events = relationship(
        "RiskAlertEvent",
        back_populates="alert",
        cascade="all, delete-orphan",
        order_by="RiskAlertEvent.created_at",
    )
    notifications = relationship(
        "RiskAlertNotification",
        back_populates="alert",
        cascade="all, delete-orphan",
        order_by="RiskAlertNotification.created_at",
    )


class RiskAlertEvent(Base):
    """Append-only alert detection, assignment and administration timeline."""

    __tablename__ = "risk_alert_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    alert_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("risk_alerts.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    previous_status: Mapped[RiskAlertStatus | None] = mapped_column(
        Enum(RiskAlertStatus, native_enum=False, length=16), nullable=True
    )
    next_status: Mapped[RiskAlertStatus] = mapped_column(
        Enum(RiskAlertStatus, native_enum=False, length=16)
    )
    previous_assignee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    next_assignee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )

    alert = relationship("RiskAlert", back_populates="events")


class RiskAlertNotification(Base):
    """Transactional outbox entry for minimum-disclosure operator notifications."""

    __tablename__ = "risk_alert_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    alert_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("risk_alerts.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("risk_alert_events.id", ondelete="SET NULL"), nullable=True
    )
    recipient_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[RiskAlertNotificationKind] = mapped_column(
        Enum(RiskAlertNotificationKind, native_enum=False, length=32), index=True
    )
    status: Mapped[RiskAlertNotificationStatus] = mapped_column(
        Enum(RiskAlertNotificationStatus, native_enum=False, length=16),
        default=RiskAlertNotificationStatus.PENDING,
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

    alert = relationship("RiskAlert", back_populates="notifications")
    recipient = relationship("User", foreign_keys=[recipient_user_id])
    last_replayed_by = relationship("User", foreign_keys=[last_replayed_by_id])
