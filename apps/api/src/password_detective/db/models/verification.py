from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base
from password_detective.db.models.password_candidate import CandidateStatus


class FeedbackOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class VerificationSource(StrEnum):
    WEB_FEEDBACK = "web_feedback"
    DESKTOP_RECEIPT = "desktop_receipt"


class CandidateFeedback(Base):
    """Current effective feedback; immutable revisions live in VerificationEvidenceEvent."""

    __tablename__ = "candidate_feedbacks"
    __table_args__ = (
        UniqueConstraint("candidate_id", "user_id", name="uq_candidate_feedback_candidate_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("password_candidates.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    outcome: Mapped[FeedbackOutcome] = mapped_column(
        Enum(FeedbackOutcome, native_enum=False, length=16), index=True
    )
    source: Mapped[VerificationSource] = mapped_column(
        Enum(VerificationSource, native_enum=False, length=32),
        default=VerificationSource.WEB_FEEDBACK,
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    rule_version: Mapped[str] = mapped_column(String(32))
    installation_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ip_prefix: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    candidate = relationship("PasswordCandidate", back_populates="feedbacks")
    events = relationship(
        "VerificationEvidenceEvent", back_populates="feedback", cascade="all, delete-orphan"
    )


class VerificationEvidenceEvent(Base):
    """Append-only evidence history for feedback creation and modification."""

    __tablename__ = "verification_evidence_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    feedback_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidate_feedbacks.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("password_candidates.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    previous_outcome: Mapped[FeedbackOutcome | None] = mapped_column(
        Enum(FeedbackOutcome, native_enum=False, length=16), nullable=True
    )
    outcome: Mapped[FeedbackOutcome] = mapped_column(
        Enum(FeedbackOutcome, native_enum=False, length=16), index=True
    )
    source: Mapped[VerificationSource] = mapped_column(
        Enum(VerificationSource, native_enum=False, length=32)
    )
    weight: Mapped[float] = mapped_column(Float)
    rule_version: Mapped[str] = mapped_column(String(32), index=True)
    installation_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_prefix: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    feedback = relationship("CandidateFeedback", back_populates="events")


class RecordStateEvent(Base):
    """Append-only record of automatic candidate state transitions."""

    __tablename__ = "record_state_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("password_candidates.id", ondelete="CASCADE"), index=True
    )
    previous_status: Mapped[CandidateStatus] = mapped_column(
        Enum(CandidateStatus, native_enum=False, length=16)
    )
    next_status: Mapped[CandidateStatus] = mapped_column(
        Enum(CandidateStatus, native_enum=False, length=16), index=True
    )
    reason_code: Mapped[str] = mapped_column(String(64), index=True)
    rule_version: Mapped[str] = mapped_column(String(32), index=True)
    trigger_evidence_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("verification_evidence_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    independent_success_count: Mapped[int] = mapped_column(Integer)
    independent_failure_count: Mapped[int] = mapped_column(Integer)
    success_weight: Mapped[float] = mapped_column(Float)
    failure_weight: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    candidate = relationship("PasswordCandidate", back_populates="state_events")
