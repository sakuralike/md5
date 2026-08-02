from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class CandidateStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


class PasswordCandidate(Base):
    __tablename__ = "password_candidates"
    __table_args__ = (
        UniqueConstraint(
            "archive_id", "secret_dedup_tag", name="uq_password_candidates_archive_dedup"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    archive_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("archives.id", ondelete="CASCADE"), index=True
    )
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    secret_nonce: Mapped[str] = mapped_column(String(64))
    secret_key_version: Mapped[str] = mapped_column(String(32))
    secret_dedup_tag: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[CandidateStatus] = mapped_column(
        Enum(CandidateStatus, native_enum=False, length=16),
        default=CandidateStatus.PENDING,
        index=True,
    )
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    archive = relationship("Archive", back_populates="candidates")
    submissions = relationship(
        "Submission", back_populates="candidate", cascade="all, delete-orphan"
    )
