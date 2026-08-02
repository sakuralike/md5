from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class TrustCaseKind(StrEnum):
    REPORT = "report"
    APPEAL = "appeal"


class TrustCaseStatus(StrEnum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class TrustCase(Base):
    __tablename__ = "trust_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[TrustCaseKind] = mapped_column(
        Enum(TrustCaseKind, native_enum=False, length=16), index=True
    )
    status: Mapped[TrustCaseStatus] = mapped_column(
        Enum(TrustCaseStatus, native_enum=False, length=16),
        default=TrustCaseStatus.OPEN,
        index=True,
    )
    reporter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("password_candidates.id", ondelete="CASCADE"), index=True
    )
    related_case_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trust_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reason_code: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        "TrustCaseEvent",
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="TrustCaseEvent.created_at",
    )


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
    next_status: Mapped[TrustCaseStatus] = mapped_column(
        Enum(TrustCaseStatus, native_enum=False, length=16)
    )
    action: Mapped[str] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )

    case = relationship("TrustCase", back_populates="events")
