from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class Archive(Base):
    __tablename__ = "archives"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    optional_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    optional_format: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    fingerprints = relationship(
        "ArchiveFingerprint", back_populates="archive", cascade="all, delete-orphan"
    )
    candidates = relationship(
        "PasswordCandidate", back_populates="archive", cascade="all, delete-orphan"
    )
