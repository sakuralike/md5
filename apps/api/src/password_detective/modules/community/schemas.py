from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from password_detective.db.models.community import (
    CommunityBoardCode,
    CommunityNotificationKind,
    CommunityNotificationSource,
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
    code: CommunityBoardCode
    name: str
    description: str
    post_count: int


class CommunityBoardListResponse(BaseModel):
    items: list[CommunityBoard]


class CommunityAuthor(BaseModel):
    user_id: str
    username: str
    role: UserRole


class CommunityPostCreateRequest(BaseModel):
    board_code: CommunityBoardCode
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
    board_code: CommunityBoardCode
    title: str
    content_preview: str
    author: CommunityAuthor
    is_pinned: bool
    is_locked: bool
    reply_count: int
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
    version: int
    edited_at: datetime | None
    created_at: datetime


class CommunityCommentListResponse(BaseModel):
    items: list[CommunityCommentResponse]
    next_cursor: str | None = None
    has_more: bool = False


class CommunityPostDetail(BaseModel):
    id: str
    board_code: CommunityBoardCode
    title: str
    content: str
    author: CommunityAuthor
    is_pinned: bool
    is_locked: bool
    reply_count: int
    version: int
    edited_at: datetime | None
    last_activity_at: datetime
    created_at: datetime
    comments: list[CommunityCommentResponse]


class CommunityHomeResponse(BaseModel):
    boards: list[CommunityBoard]
    posts: CommunityPostListResponse


class CommunityMutationResponse(BaseModel):
    message: str
    version: int

class CommunityNotificationResponse(BaseModel):
    id: str
    kind: CommunityNotificationKind
    source_type: CommunityNotificationSource
    source_id: str
    post_id: str
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


class CommunityNotificationReadResponse(BaseModel):
    message: str
    unread_count: int
