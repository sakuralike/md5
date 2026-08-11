from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class CommunityBoardCode(StrEnum):
    GENERAL = "general"
    RECOVERY_GUIDES = "recovery_guides"
    VERIFICATION = "verification"
    SECURITY = "security"


class CommunityContentStatus(StrEnum):
    PUBLISHED = "published"
    REMOVED = "removed"


class CommunityPost(Base):
    __tablename__ = "community_posts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    board_code: Mapped[CommunityBoardCode] = mapped_column(
        Enum(CommunityBoardCode, native_enum=False, length=32), index=True
    )
    author_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[CommunityContentStatus] = mapped_column(
        Enum(CommunityContentStatus, native_enum=False, length=16),
        default=CommunityContentStatus.PUBLISHED,
        index=True,
    )
    is_pinned: Mapped[bool] = mapped_column(default=False, index=True)
    is_locked: Mapped[bool] = mapped_column(default=False, index=True)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunityComment(Base):
    __tablename__ = "community_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_posts.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("community_comments.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[CommunityContentStatus] = mapped_column(
        Enum(CommunityContentStatus, native_enum=False, length=16),
        default=CommunityContentStatus.PUBLISHED,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
