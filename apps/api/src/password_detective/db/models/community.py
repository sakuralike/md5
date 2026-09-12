from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class CommunityBoardCode(StrEnum):
    GENERAL = "general"
    RECOVERY_GUIDES = "recovery_guides"
    VERIFICATION = "verification"
    SECURITY = "security"


class CommunityBoardStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class CommunityGroupVisibility(StrEnum):
    PUBLIC = "public"
    APPROVAL = "approval"
    PRIVATE = "private"


class CommunityGroupStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class CommunityGroupRole(StrEnum):
    OWNER = "owner"
    MODERATOR = "moderator"
    MEMBER = "member"


class CommunityGroupMembershipStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    REMOVED = "removed"


class CommunityBoard(Base):
    __tablename__ = "community_boards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(48))
    description: Mapped[str] = mapped_column(String(300), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    minimum_role: Mapped[str] = mapped_column(String(32), default="user")
    status: Mapped[CommunityBoardStatus] = mapped_column(
        Enum(CommunityBoardStatus, native_enum=False, length=16),
        default=CommunityBoardStatus.ACTIVE,
        index=True,
    )
    is_read_only: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunityGroup(Base):
    __tablename__ = "community_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(500), default="")
    visibility: Mapped[CommunityGroupVisibility] = mapped_column(
        Enum(CommunityGroupVisibility, native_enum=False, length=16), index=True
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[CommunityGroupStatus] = mapped_column(
        Enum(CommunityGroupStatus, native_enum=False, length=16),
        default=CommunityGroupStatus.ACTIVE,
        index=True,
    )
    member_count: Mapped[int] = mapped_column(Integer, default=1)
    post_count: Mapped[int] = mapped_column(Integer, default=0)
    seo_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    seo_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    seo_keywords: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    seo_canonical_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    og_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    seo_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunityGroupMembership(Base):
    __tablename__ = "community_group_memberships"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_community_group_membership"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_groups.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[CommunityGroupRole] = mapped_column(
        Enum(CommunityGroupRole, native_enum=False, length=16),
        default=CommunityGroupRole.MEMBER,
        index=True,
    )
    status: Mapped[CommunityGroupMembershipStatus] = mapped_column(
        Enum(CommunityGroupMembershipStatus, native_enum=False, length=16),
        default=CommunityGroupMembershipStatus.PENDING,
        index=True,
    )
    decided_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunityGroupGovernanceEvent(Base):
    __tablename__ = "community_group_governance_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_groups.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    subject_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(48), index=True)
    before_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


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
    REPLY = "reply"
    FOLLOW = "follow"
    LIKE_SUMMARY = "like_summary"
    GROUP_APPLICATION = "group_application"
    GROUP_DECISION = "group_decision"
    GROUP_ROLE_CHANGE = "group_role_change"
    DIRECT_MESSAGE = "direct_message"
    PLUGIN_REVIEW = "plugin_review"


class CommunityNotificationOutboxStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class CommunityNotificationEmailDigestStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SUPPRESSED = "suppressed"


class CommunityNotificationSource(StrEnum):
    POST = "post"
    COMMENT = "comment"
    USER = "user"
    GROUP = "group"
    DIRECT_MESSAGE = "direct_message"


class CommunityDirectEventType(StrEnum):
    MESSAGE_CREATED = "message.created"
    CONVERSATION_READ = "conversation.read"
    UNREAD_CHANGED = "unread.changed"


class CommunityDirectMessageReportStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class CommunityDirectMessageReportDecision(StrEnum):
    DISMISS = "dismiss"
    REMOVE_MESSAGE = "remove_message"


class CommunityDirectConversation(Base):
    __tablename__ = "community_direct_conversations"
    __table_args__ = (
        UniqueConstraint(
            "participant_low_id",
            "participant_high_id",
            name="uq_community_direct_conversation_pair",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_low_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    participant_high_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True
    )


class CommunityDirectConversationMember(Base):
    __tablename__ = "community_direct_conversation_members"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_community_direct_member"),
        Index(
            "ix_community_direct_member_user_updated",
            "user_id",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_direct_conversations.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    last_read_sequence: Mapped[int] = mapped_column(Integer, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    muted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunityDirectStreamPosition(Base):
    __tablename__ = "community_direct_stream_positions"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_sequence: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunityDirectEvent(Base):
    __tablename__ = "community_direct_events"
    __table_args__ = (
        UniqueConstraint(
            "recipient_id",
            "sequence",
            name="uq_community_direct_event_recipient_sequence",
        ),
        Index(
            "ix_community_direct_event_recipient_sequence",
            "recipient_id",
            "sequence",
        ),
        Index(
            "ix_community_direct_event_conversation_created",
            "conversation_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recipient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE")
    )
    sequence: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[CommunityDirectEventType] = mapped_column(
        Enum(CommunityDirectEventType, native_enum=False, length=32)
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_direct_conversations.id", ondelete="CASCADE"),
    )
    actor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    message_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("community_direct_messages.id", ondelete="CASCADE"),
        nullable=True,
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CommunityDirectMessage(Base):
    __tablename__ = "community_direct_messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "sequence",
            name="uq_community_direct_message_sequence",
        ),
        UniqueConstraint(
            "sender_id",
            "client_message_id",
            name="uq_community_direct_sender_client_message",
        ),
        Index(
            "ix_community_direct_message_conversation_sequence",
            "conversation_id",
            "sequence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_direct_conversations.id", ondelete="CASCADE"),
        index=True,
    )
    sender_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    ciphertext: Mapped[str] = mapped_column(Text)
    nonce: Mapped[str] = mapped_column(String(32))
    key_version: Mapped[str] = mapped_column(String(32))
    client_message_id: Mapped[str] = mapped_column(String(72))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommunityDirectMessageReport(Base):
    __tablename__ = "community_direct_message_reports"
    __table_args__ = (
        Index(
            "ix_community_direct_message_report_reporter_message_status",
            "reporter_id",
            "message_id",
            "status",
        ),
        Index(
            "ix_community_direct_message_report_status_created",
            "status",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reporter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("community_direct_messages.id", ondelete="SET NULL"), nullable=True
    )
    conversation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("community_direct_conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sender_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reason: Mapped[CommunityReportReason] = mapped_column(
        Enum(CommunityReportReason, native_enum=False, length=24), index=True
    )
    details: Mapped[str] = mapped_column(Text)
    status: Mapped[CommunityDirectMessageReportStatus] = mapped_column(
        Enum(CommunityDirectMessageReportStatus, native_enum=False, length=16),
        default=CommunityDirectMessageReportStatus.OPEN,
        index=True,
    )
    decision: Mapped[CommunityDirectMessageReportDecision | None] = mapped_column(
        Enum(CommunityDirectMessageReportDecision, native_enum=False, length=24), nullable=True
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


class CommunityDirectMessageCooldown(Base):
    __tablename__ = "community_direct_message_cooldowns"
    __table_args__ = (
        Index(
            "ix_community_direct_message_cooldown_until",
            "until",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    reason: Mapped[str] = mapped_column(String(64))
    until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    triggered_message_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunityActivityKind(StrEnum):
    POST_PUBLISHED = "post_published"
    COMMENT_PUBLISHED = "comment_published"
    GROUP_JOINED = "group_joined"
    USER_FOLLOWED = "user_followed"


class CommunityActivitySource(StrEnum):
    POST = "post"
    COMMENT = "comment"
    GROUP_MEMBERSHIP = "group_membership"
    USER_FOLLOW = "user_follow"


class CommunityActivityFeed(StrEnum):
    LATEST = "latest"
    FOLLOWING = "following"
    GROUPS = "groups"


class CommunityPost(Base):
    __tablename__ = "community_posts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    board_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_boards.id", ondelete="RESTRICT"), index=True
    )
    board_code: Mapped[str] = mapped_column(String(32), index=True)
    group_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("community_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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
    seo_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    seo_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    seo_keywords: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    seo_canonical_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    og_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    seo_version: Mapped[int] = mapped_column(Integer, default=1)
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
    post_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("community_posts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
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
    delivery_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class CommunityNotificationOutbox(Base):
    """Durable community notification event used for SSE replay and later channels."""

    __tablename__ = "community_notification_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    notification_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_notifications.id", ondelete="CASCADE"), index=True
    )
    recipient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    status: Mapped[CommunityNotificationOutboxStatus] = mapped_column(
        Enum(CommunityNotificationOutboxStatus, native_enum=False, length=16),
        default=CommunityNotificationOutboxStatus.PENDING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    replay_count: Mapped[int] = mapped_column(Integer, default=0)
    last_replayed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_replayed_by_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunityNotificationEmailDigest(Base):
    __tablename__ = "community_notification_email_digests"
    __table_args__ = (
        UniqueConstraint(
            "recipient_id",
            "window_started_at",
            name="uq_community_notification_email_digest_window",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recipient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    window_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[CommunityNotificationEmailDigestStatus] = mapped_column(
        Enum(CommunityNotificationEmailDigestStatus, native_enum=False, length=16),
        default=CommunityNotificationEmailDigestStatus.PENDING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suppressed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunityNotificationEmailDigestItem(Base):
    __tablename__ = "community_notification_email_digest_items"
    __table_args__ = (
        UniqueConstraint(
            "digest_id",
            "notification_id",
            "delivery_version",
            name="uq_community_notification_email_digest_item_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    digest_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_notification_email_digests.id", ondelete="CASCADE"),
        index=True,
    )
    notification_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_notifications.id", ondelete="CASCADE"),
        index=True,
    )
    delivery_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CommunityNotificationPreference(Base):
    __tablename__ = "community_notification_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", name="uq_community_notification_preference"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[CommunityNotificationKind] = mapped_column(
        Enum(CommunityNotificationKind, native_enum=False, length=24), index=True
    )
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    email_digest_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunityActivityPreference(Base):
    __tablename__ = "community_activity_preferences"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    share_group_joins: Mapped[bool] = mapped_column(Boolean, default=True)
    share_follows: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunityActivityEvent(Base):
    __tablename__ = "community_activity_events"
    __table_args__ = (
        UniqueConstraint("kind", "source_type", "source_id", name="uq_community_activity_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[CommunityActivityKind] = mapped_column(
        Enum(CommunityActivityKind, native_enum=False, length=24), index=True
    )
    source_type: Mapped[CommunityActivitySource] = mapped_column(
        Enum(CommunityActivitySource, native_enum=False, length=24), index=True
    )
    source_id: Mapped[str] = mapped_column(String(36))
    post_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("community_posts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    comment_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("community_comments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    group_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("community_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    preview: Mapped[str] = mapped_column(String(180))
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
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


class CommunityAvatarKind(StrEnum):
    GENERATED = "generated"
    UPLOAD = "upload"
    GRAVATAR = "gravatar"


class CommunityPublicProfile(Base):
    __tablename__ = "community_public_profiles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(48))
    bio: Mapped[str] = mapped_column(String(300), default="")
    avatar_seed: Mapped[str] = mapped_column(String(32))
    avatar_kind: Mapped[CommunityAvatarKind] = mapped_column(
        Enum(CommunityAvatarKind, native_enum=False, length=16),
        default=CommunityAvatarKind.GENERATED,
        index=True,
    )
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    gravatar_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
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


class CommunitySearchSource(StrEnum):
    POST = "post"
    USER = "user"
    BOARD = "board"
    GROUP = "group"


class CommunitySearchOutboxStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class CommunitySearchRebuildStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CommunitySearchDocument(Base):
    __tablename__ = "community_search_documents"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_community_search_document_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_type: Mapped[CommunitySearchSource] = mapped_column(
        Enum(CommunitySearchSource, native_enum=False, length=16), index=True
    )
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    document_version: Mapped[int] = mapped_column(BigInteger, default=1)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text, default="")
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    board_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    group_slug: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    author_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunitySearchOutbox(Base):
    __tablename__ = "community_search_outbox"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_community_search_outbox_dedupe"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(16))
    source_type: Mapped[CommunitySearchSource] = mapped_column(
        Enum(CommunitySearchSource, native_enum=False, length=16), index=True
    )
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    document_version: Mapped[int] = mapped_column(BigInteger, default=1)
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    status: Mapped[CommunitySearchOutboxStatus] = mapped_column(
        Enum(CommunitySearchOutboxStatus, native_enum=False, length=16),
        default=CommunitySearchOutboxStatus.PENDING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CommunitySearchRebuildRun(Base):
    __tablename__ = "community_search_rebuild_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(64), default="all")
    status: Mapped[CommunitySearchRebuildStatus] = mapped_column(
        Enum(CommunitySearchRebuildStatus, native_enum=False, length=16),
        default=CommunitySearchRebuildStatus.PENDING,
        index=True,
    )
    cursor: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expected_count: Mapped[int] = mapped_column(Integer, default=0)
    indexed_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, default=0)
    extra_count: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(String(256), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
