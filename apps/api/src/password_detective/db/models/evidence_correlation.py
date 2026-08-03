from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class EvidenceCorrelationAssessment(Base):
    """Append-only aggregate snapshot of candidate-local account correlation analysis."""

    __tablename__ = "evidence_correlation_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("password_candidates.id", ondelete="CASCADE"), index=True
    )
    trigger_evidence_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("verification_evidence_events.id", ondelete="RESTRICT"),
        unique=True,
    )
    rule_version: Mapped[str] = mapped_column(String(32), index=True)
    feedback_count: Mapped[int] = mapped_column(Integer)
    independent_group_count: Mapped[int] = mapped_column(Integer)
    correlated_group_count: Mapped[int] = mapped_column(Integer)
    downweighted_feedback_count: Mapped[int] = mapped_column(Integer)
    raw_success_weight: Mapped[float] = mapped_column(Float)
    effective_success_weight: Mapped[float] = mapped_column(Float)
    raw_failure_weight: Mapped[float] = mapped_column(Float)
    effective_failure_weight: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
