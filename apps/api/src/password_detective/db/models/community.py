from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
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


class CommunityReportReason(StrEnum):
    SPAM = "spam"
    HARASSMENT = "harassment"
    PRIVACY = "privacy"
    UNSAFE = "unsafe"
    OTHER = "other"


class CommunityReportStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class CommunityReportDecision(StrEnum):
    DISMISS = "dismiss"
    REMOVE_CONTENT = "remove_content"
    REMOVE_AND_LOCK = "remove_and_lock"


class CommunityModerationAction(StrEnum):
    LOCK = "lock"
    UNLOCK = "unlock"
    PIN = "pin"
    UNPIN = "unpin"
    REMOVE = "remove"
    RESTORE = "restore"


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
    version: Mapped[int] = mapped_column(Integer, default=1)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_author_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunityPostRevision(Base):
    __tablename__ = "community_post_revisions"
    __table_args__ = (
        UniqueConstraint("post_id", "version", name="uq_community_post_revision_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_posts.id", ondelete="CASCADE"), index=True
    )
    editor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    title_snapshot: Mapped[str] = mapped_column(String(120))
    content_snapshot: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(64), default="author_edit")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
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
    root_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("community_comments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reply_to_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[CommunityContentStatus] = mapped_column(
        Enum(CommunityContentStatus, native_enum=False, length=16),
        default=CommunityContentStatus.PUBLISHED,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_author_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunityReport(Base):
    __tablename__ = "community_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reporter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_posts.id", ondelete="CASCADE"), index=True
    )
    comment_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("community_comments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    reason: Mapped[CommunityReportReason] = mapped_column(
        Enum(CommunityReportReason, native_enum=False, length=24), index=True
    )
    details: Mapped[str] = mapped_column(Text)
    status: Mapped[CommunityReportStatus] = mapped_column(
        Enum(CommunityReportStatus, native_enum=False, length=16),
        default=CommunityReportStatus.OPEN,
        index=True,
    )
    decision: Mapped[CommunityReportDecision | None] = mapped_column(
        Enum(CommunityReportDecision, native_enum=False, length=24), nullable=True
    )
    resolved_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
