from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class FingerprintAlgorithm(StrEnum):
    MD5 = "md5"
    SHA1 = "sha1"
    SHA256 = "sha256"
    SHA512 = "sha512"


class ArchiveFingerprint(Base):
    __tablename__ = "archive_fingerprints"
    __table_args__ = (
        UniqueConstraint("algorithm", "digest", name="uq_archive_fingerprints_algorithm_digest"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    archive_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("archives.id", ondelete="CASCADE"), index=True
    )
    algorithm: Mapped[FingerprintAlgorithm] = mapped_column(
        Enum(FingerprintAlgorithm, native_enum=False, length=16), index=True
    )
    digest: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    archive = relationship("Archive", back_populates="fingerprints")
