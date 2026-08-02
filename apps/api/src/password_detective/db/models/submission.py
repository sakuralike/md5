from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class SubmissionSource(StrEnum):
    WEB = "web"
    DESKTOP = "desktop"
    ADMIN = "admin"


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("password_candidates.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[SubmissionSource] = mapped_column(
        Enum(SubmissionSource, native_enum=False, length=16), default=SubmissionSource.WEB
    )
    authorization_version: Mapped[str] = mapped_column(String(32))
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), index=True)
    ip_prefix: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    candidate = relationship("PasswordCandidate", back_populates="submissions")
