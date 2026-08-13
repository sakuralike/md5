from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class HashVoteOutcome(StrEnum):
    USEFUL = "useful"
    NOT_USEFUL = "not_useful"


class HashLike(Base):
    __tablename__ = "hash_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint_id", name="uq_hash_like_user_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    fingerprint_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("archive_fingerprints.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class HashVote(Base):
    __tablename__ = "hash_votes"
    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint_id", name="uq_hash_vote_user_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    fingerprint_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("archive_fingerprints.id", ondelete="CASCADE"), index=True
    )
    outcome: Mapped[HashVoteOutcome] = mapped_column(
        Enum(HashVoteOutcome, native_enum=False, length=16), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class HashComment(Base):
    __tablename__ = "hash_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    fingerprint_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("archive_fingerprints.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("hash_comments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content: Mapped[str] = mapped_column(Text)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class HashCommentLike(Base):
    __tablename__ = "hash_comment_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "comment_id", name="uq_hash_comment_like_user_comment"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    comment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hash_comments.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
