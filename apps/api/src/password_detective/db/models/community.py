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


class CommunityNotificationKind(StrEnum):
    MENTION = "mention"


class CommunityNotificationSource(StrEnum):
    POST = "post"
    COMMENT = "comment"


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
    like_count: Mapped[int] = mapped_column(Integer, default=0)
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
    like_count: Mapped[int] = mapped_column(Integer, default=0)
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


class CommunityPostLike(Base):
    __tablename__ = "community_post_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="uq_community_post_like_user_post"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_posts.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class CommunityCommentLike(Base):
    __tablename__ = "community_comment_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "comment_id", name="uq_community_comment_like_user_comment"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    comment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_comments.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class CommunityPostBookmark(Base):
    __tablename__ = "community_post_bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="uq_community_post_bookmark_user_post"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_posts.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
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


class CommunityNotification(Base):
    __tablename__ = "community_notifications"
    __table_args__ = (
        UniqueConstraint(
            "recipient_id",
            "kind",
            "source_type",
            "source_id",
            name="uq_community_notification_delivery",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recipient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[CommunityNotificationKind] = mapped_column(
        Enum(CommunityNotificationKind, native_enum=False, length=24), index=True
    )
    source_type: Mapped[CommunityNotificationSource] = mapped_column(
        Enum(CommunityNotificationSource, native_enum=False, length=16), index=True
    )
    source_id: Mapped[str] = mapped_column(String(36))
    post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_posts.id", ondelete="CASCADE"), index=True
    )
    comment_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("community_comments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    preview: Mapped[str] = mapped_column(String(180))
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class CommunityRelationVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class CommunityInteractionPolicy(StrEnum):
    EVERYONE = "everyone"
    FOLLOWING = "following"
    NOBODY = "nobody"


class CommunityPublicProfile(Base):
    __tablename__ = "community_public_profiles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(48))
    bio: Mapped[str] = mapped_column(String(300), default="")
    avatar_seed: Mapped[str] = mapped_column(String(32))
    follower_visibility: Mapped[CommunityRelationVisibility] = mapped_column(
        Enum(CommunityRelationVisibility, native_enum=False, length=16),
        default=CommunityRelationVisibility.PUBLIC,
    )
    following_visibility: Mapped[CommunityRelationVisibility] = mapped_column(
        Enum(CommunityRelationVisibility, native_enum=False, length=16),
        default=CommunityRelationVisibility.PUBLIC,
    )
    message_policy: Mapped[CommunityInteractionPolicy] = mapped_column(
        Enum(CommunityInteractionPolicy, native_enum=False, length=16),
        default=CommunityInteractionPolicy.FOLLOWING,
    )
    mention_policy: Mapped[CommunityInteractionPolicy] = mapped_column(
        Enum(CommunityInteractionPolicy, native_enum=False, length=16),
        default=CommunityInteractionPolicy.EVERYONE,
    )
    follower_count: Mapped[int] = mapped_column(Integer, default=0)
    following_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunityUserFollow(Base):
    __tablename__ = "community_user_follows"
    __table_args__ = (
        UniqueConstraint("follower_id", "followed_id", name="uq_community_user_follow_pair"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    follower_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    followed_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class CommunityUserBlock(Base):
    __tablename__ = "community_user_blocks"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_community_user_block_pair"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    blocker_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    blocked_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class CommunityUserMute(Base):
    __tablename__ = "community_user_mutes"
    __table_args__ = (
        UniqueConstraint("user_id", "muted_user_id", name="uq_community_user_mute_pair"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    muted_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
