from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from password_detective.db.models.community import (
    CommunityActivityFeed,
    CommunityActivityKind,
    CommunityActivitySource,
    CommunityBoardStatus,
    CommunityGroupMembershipStatus,
    CommunityGroupRole,
    CommunityGroupStatus,
    CommunityGroupVisibility,
    CommunityInteractionPolicy,
    CommunityNotificationKind,
    CommunityNotificationSource,
    CommunityRelationVisibility,
    CommunityReportReason,
    CommunityReportStatus,
)
from password_detective.db.models.user import UserRole


def _normalize(value: str, empty_message: str) -> str:
    normalized = value.replace("\x00", "").strip()
    if not normalized:
        raise ValueError(empty_message)
    return normalized


class CommunityBoard(BaseModel):
    code: str
    name: str
    description: str
    sort_order: int = 0
    minimum_role: UserRole = UserRole.USER
    status: CommunityBoardStatus = CommunityBoardStatus.ACTIVE
    is_read_only: bool = False
    post_count: int = 0


class CommunityBoardListResponse(BaseModel):
    items: list[CommunityBoard]


class CommunityGroupCreateRequest(BaseModel):
    slug: str = Field(min_length=3, max_length=48, pattern=r"^[a-z0-9][a-z0-9-]{2,47}$")
    name: str = Field(min_length=2, max_length=64)
    description: str = Field(default="", max_length=500)
    visibility: CommunityGroupVisibility

    @field_validator("name", "description")
    @classmethod
    def normalize_group_text(cls, value: str) -> str:
        return value.replace("\x00", "").strip()


class CommunityGroupUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    description: str = Field(default="", max_length=500)
    visibility: CommunityGroupVisibility
    status: CommunityGroupStatus = CommunityGroupStatus.ACTIVE

    @field_validator("name", "description")
    @classmethod
    def normalize_group_text(cls, value: str) -> str:
        return value.replace("\x00", "").strip()


class CommunityGroupMember(BaseModel):
    username: str
    role: CommunityGroupRole
    status: CommunityGroupMembershipStatus


class CommunityGroupSummary(BaseModel):
    slug: str
    name: str
    description: str
    visibility: CommunityGroupVisibility
    status: CommunityGroupStatus
    member_count: int
    post_count: int
    viewer_role: CommunityGroupRole | None = None
    viewer_membership_status: CommunityGroupMembershipStatus | None = None


class CommunityGroupListResponse(BaseModel):
    items: list[CommunityGroupSummary]


class CommunityGroupDetail(CommunityGroupSummary):
    owner_username: str
    members: list[CommunityGroupMember]
    posts: CommunityPostListResponse | None = None


class CommunityGroupMembershipResponse(BaseModel):
    group: CommunityGroupSummary
    message: str


class CommunityGroupMemberDecisionRequest(BaseModel):
    decision: str = Field(pattern=r"^(approve|reject|remove|invite)$")
    role: CommunityGroupRole = CommunityGroupRole.MEMBER


class CommunityAuthor(BaseModel):
    user_id: str
    username: str
    role: UserRole


class CommunityPostCreateRequest(BaseModel):
    board_code: str
    group_slug: str | None = None
    title: str = Field(min_length=4, max_length=120)
    content: str = Field(min_length=20, max_length=10000)
    rules_accepted: bool

    @field_validator("title", "content")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _normalize(value, "内容不能为空")


class CommunityPostUpdateRequest(BaseModel):
    title: str = Field(min_length=4, max_length=120)
    content: str = Field(min_length=20, max_length=10000)
    rules_accepted: bool
    expected_version: int = Field(ge=1)

    @field_validator("title", "content")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _normalize(value, "内容不能为空")


class CommunityCommentCreateRequest(BaseModel):
    content: str = Field(min_length=2, max_length=2000)
    parent_id: str | None = Field(default=None, max_length=36)
    rules_accepted: bool

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return _normalize(value, "回复不能为空")


class CommunityCommentUpdateRequest(BaseModel):
    content: str = Field(min_length=2, max_length=2000)
    rules_accepted: bool
    expected_version: int = Field(ge=1)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return _normalize(value, "回复不能为空")


class CommunityReportCreateRequest(BaseModel):
    post_id: str = Field(min_length=1, max_length=36)
    comment_id: str | None = Field(default=None, max_length=36)
    reason: CommunityReportReason
    details: str = Field(min_length=10, max_length=1000)

    @field_validator("details")
    @classmethod
    def normalize_details(cls, value: str) -> str:
        return _normalize(value, "举报说明不能为空")


class CommunityReportResponse(BaseModel):
    id: str
    post_id: str
    comment_id: str | None
    reason: CommunityReportReason
    status: CommunityReportStatus
    created_at: datetime


class CommunityPostSummary(BaseModel):
    id: str
    board_code: str
    group_slug: str | None = None
    title: str
    content_preview: str
    author: CommunityAuthor
    is_pinned: bool
    is_locked: bool
    reply_count: int
    like_count: int = 0
    version: int
    edited_at: datetime | None
    last_activity_at: datetime
    created_at: datetime


class CommunityPostListResponse(BaseModel):
    items: list[CommunityPostSummary]
    page: int
    page_size: int
    total: int
    next_cursor: str | None = None
    has_more: bool = False


class CommunityCommentResponse(BaseModel):
    id: str
    parent_id: str | None
    root_id: str | None
    reply_to_user_id: str | None
    content: str
    author: CommunityAuthor
    like_count: int = 0
    viewer_has_liked: bool = False
    version: int
    edited_at: datetime | None
    created_at: datetime


class CommunityCommentListResponse(BaseModel):
    items: list[CommunityCommentResponse]
    next_cursor: str | None = None
    has_more: bool = False


class CommunityPostDetail(BaseModel):
    id: str
    board_code: str
    group_slug: str | None = None
    title: str
    content: str
    author: CommunityAuthor
    is_pinned: bool
    is_locked: bool
    reply_count: int
    like_count: int = 0
    viewer_has_liked: bool = False
    viewer_has_bookmarked: bool = False
    version: int
    edited_at: datetime | None
    last_activity_at: datetime
    created_at: datetime
    comments: list[CommunityCommentResponse]


class CommunityHomeResponse(BaseModel):
    boards: list[CommunityBoard]
    posts: CommunityPostListResponse


class CommunityPostInteractionResponse(BaseModel):
    post_id: str
    like_count: int = 0
    viewer_has_liked: bool = False
    viewer_has_bookmarked: bool = False


class CommunityCommentLikeResponse(BaseModel):
    comment_id: str
    like_count: int = 0
    viewer_has_liked: bool = False


class CommunityBookmarkItem(BaseModel):
    post_id: str
    bookmarked_at: datetime
    post: CommunityPostSummary | None


class CommunityBookmarkListResponse(BaseModel):
    items: list[CommunityBookmarkItem]
    next_cursor: str | None = None
    has_more: bool = False


class CommunityMutationResponse(BaseModel):
    message: str
    version: int


class CommunityNotificationResponse(BaseModel):
    id: str
    kind: CommunityNotificationKind
    source_type: CommunityNotificationSource
    source_id: str
    post_id: str | None
    comment_id: str | None
    preview: str
    actor: CommunityAuthor
    read_at: datetime | None
    created_at: datetime


class CommunityNotificationListResponse(BaseModel):
    items: list[CommunityNotificationResponse]
    unread_count: int
    next_cursor: str | None = None
    has_more: bool = False


class CommunityNotificationStreamReady(BaseModel):
    event_id: str | None = None
    unread_count: int


class CommunityNotificationStreamEvent(BaseModel):
    event_id: str
    notification: CommunityNotificationResponse
    unread_count: int


class CommunityNotificationReadResponse(BaseModel):
    message: str
    unread_count: int


class CommunityNotificationPreferenceItem(BaseModel):
    kind: CommunityNotificationKind
    in_app_enabled: bool = True
    email_digest_enabled: bool = False


class CommunityNotificationPreferencesResponse(BaseModel):
    items: list[CommunityNotificationPreferenceItem]


class CommunityNotificationPreferencesUpdateRequest(BaseModel):
    items: list[CommunityNotificationPreferenceItem] = Field(min_length=1, max_length=16)


class CommunityActivityPreferenceResponse(BaseModel):
    share_group_joins: bool = True
    share_follows: bool = True


class CommunityActivityPreferenceUpdateRequest(BaseModel):
    share_group_joins: bool
    share_follows: bool


class CommunityActivityItem(BaseModel):
    id: str
    kind: CommunityActivityKind
    source_type: CommunityActivitySource
    source_id: str
    actor: CommunityAuthor
    preview: str
    post_id: str | None = None
    post_title: str | None = None
    comment_id: str | None = None
    group_slug: str | None = None
    group_name: str | None = None
    target_username: str | None = None
    created_at: datetime


class CommunityActivityListResponse(BaseModel):
    feed: CommunityActivityFeed
    items: list[CommunityActivityItem]
    next_cursor: str | None = None
    has_more: bool = False


class CommunityPublicLevel(BaseModel):
    code: str
    name: str


class CommunityProfileStats(BaseModel):
    post_count: int
    comment_count: int
    follower_count: int
    following_count: int


class CommunityRelationshipState(BaseModel):
    viewer_is_self: bool = False
    viewer_is_following: bool = False
    follows_viewer: bool = False
    viewer_is_blocking: bool = False
    viewer_is_blocked: bool = False
    viewer_is_muting: bool = False


class CommunityPublicCommentSummary(BaseModel):
    id: str
    post_id: str
    post_title: str
    content_preview: str
    like_count: int
    created_at: datetime


class CommunityPublicProfileResponse(BaseModel):
    username: str
    display_name: str
    bio: str
    avatar_seed: str
    role: UserRole
    level: CommunityPublicLevel
    registered_month: str
    stats: CommunityProfileStats
    relationship: CommunityRelationshipState
    recent_posts: list[CommunityPostSummary]
    recent_comments: list[CommunityPublicCommentSummary]


class CommunityOwnProfileResponse(CommunityPublicProfileResponse):
    follower_visibility: CommunityRelationVisibility
    following_visibility: CommunityRelationVisibility
    message_policy: CommunityInteractionPolicy
    mention_policy: CommunityInteractionPolicy


class CommunityProfileUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=48)
    bio: str = Field(default="", max_length=300)
    regenerate_avatar: bool = False

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        return _normalize(value, "公开显示名不能为空")

    @field_validator("bio")
    @classmethod
    def normalize_bio(cls, value: str) -> str:
        return value.replace("\x00", "").strip()


class CommunityPrivacyUpdateRequest(BaseModel):
    follower_visibility: CommunityRelationVisibility
    following_visibility: CommunityRelationVisibility
    message_policy: CommunityInteractionPolicy
    mention_policy: CommunityInteractionPolicy


class CommunityMuteRequest(BaseModel):
    expires_at: datetime | None = None


class CommunityRelationshipMutationResponse(BaseModel):
    username: str
    relationship: CommunityRelationshipState
    message: str


class CommunityRelationUser(BaseModel):
    username: str
    display_name: str
    avatar_seed: str
    role: UserRole
    level: CommunityPublicLevel


class CommunityRelationListResponse(BaseModel):
    items: list[CommunityRelationUser]
    next_cursor: str | None = None
    has_more: bool = False


class CommunitySearchResultItem(BaseModel):
    type: str
    source_id: str
    title: str
    preview: str
    username: str | None = None
    board_code: str | None = None
    group_slug: str | None = None
    updated_at: datetime


class CommunitySearchProviderState(BaseModel):
    mode: str
    degraded: bool


class CommunitySearchResponse(BaseModel):
    query: str
    items: list[CommunitySearchResultItem]
    page: int
    page_size: int
    total: int
    provider: CommunitySearchProviderState
