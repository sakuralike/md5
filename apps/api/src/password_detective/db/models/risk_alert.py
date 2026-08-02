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
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
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
    events = relationship(
        "RiskAlertEvent",
        back_populates="alert",
        cascade="all, delete-orphan",
        order_by="RiskAlertEvent.created_at",
    )


class RiskAlertEvent(Base):
    """Append-only alert detection and administration timeline."""

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
    action: Mapped[str] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )

    alert = relationship("RiskAlert", back_populates="events")
