from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from password_detective.db.models.community import (
    CommunityBoardStatus,
    CommunityContentStatus,
    CommunityModerationAction,
    CommunityNotificationKind,
    CommunityNotificationOutboxStatus,
    CommunityNotificationSource,
    CommunityReportDecision,
    CommunityReportReason,
    CommunityReportStatus,
    CommunitySearchRebuildStatus,
)
from password_detective.db.models.user import UserRole


class AdminCommunityReportSummary(BaseModel):
    id: str
    reporter_username: str
    post_id: str
    post_title: str
    comment_id: str | None
    target_type: str
    target_excerpt: str
    reason: CommunityReportReason
    details: str
    status: CommunityReportStatus
    decision: CommunityReportDecision | None
    resolution_note: str | None
    resolved_by_username: str | None
    created_at: datetime
    resolved_at: datetime | None


class AdminCommunityReportListResponse(BaseModel):
    items: list[AdminCommunityReportSummary]
    page: int
    page_size: int
    total: int


class AdminCommunityReportResolveRequest(BaseModel):
    decision: CommunityReportDecision
    note: str = Field(min_length=4, max_length=1000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        normalized = value.replace("\x00", "").strip()
        if not normalized:
            raise ValueError("处理说明不能为空")
        return normalized


class AdminCommunityPostModerateRequest(BaseModel):
    action: CommunityModerationAction
    note: str = Field(min_length=4, max_length=1000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        normalized = value.replace("\x00", "").strip()
        if not normalized:
            raise ValueError("处理说明不能为空")
        return normalized


class AdminCommunityPostState(BaseModel):
    id: str
    board_code: str
    title: str
    status: CommunityContentStatus
    is_pinned: bool
    is_locked: bool
    reply_count: int
    updated_at: datetime


class AdminCommunityReportMutationResponse(BaseModel):
    report: AdminCommunityReportSummary
    post: AdminCommunityPostState
    audit_id: str
    request_id: str | None


class AdminCommunityPostMutationResponse(BaseModel):
    post: AdminCommunityPostState
    audit_id: str
    request_id: str | None


class AdminCommunityBoardCreateRequest(BaseModel):
    code: str = Field(min_length=3, max_length=32, pattern=r"^[a-z0-9][a-z0-9_]{2,31}$")
    name: str = Field(min_length=2, max_length=48)
    description: str = Field(default="", max_length=300)
    sort_order: int = Field(default=0, ge=-10000, le=10000)
    minimum_role: UserRole = UserRole.USER
    is_read_only: bool = False
    status: CommunityBoardStatus = CommunityBoardStatus.ACTIVE

    @field_validator("name", "description")
    @classmethod
    def normalize_board_text(cls, value: str) -> str:
        return value.replace("\x00", "").strip()


class AdminCommunityBoardUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=48)
    description: str = Field(default="", max_length=300)
    sort_order: int = Field(default=0, ge=-10000, le=10000)
    minimum_role: UserRole = UserRole.USER
    is_read_only: bool = False
    status: CommunityBoardStatus = CommunityBoardStatus.ACTIVE

    @field_validator("name", "description")
    @classmethod
    def normalize_board_text(cls, value: str) -> str:
        return value.replace("\x00", "").strip()


class AdminCommunityBoardResponse(BaseModel):
    code: str
    name: str
    description: str
    sort_order: int
    minimum_role: UserRole
    is_read_only: bool
    status: CommunityBoardStatus
    post_count: int
    created_at: datetime
    updated_at: datetime


class AdminCommunityBoardListResponse(BaseModel):
    items: list[AdminCommunityBoardResponse]


class AdminCommunityBoardMutationResponse(BaseModel):
    board: AdminCommunityBoardResponse
    audit_id: str
    request_id: str | None


class AdminCommunityNotificationOutboxItem(BaseModel):
    id: str
    notification_id: str
    recipient_username: str
    actor_username: str
    kind: CommunityNotificationKind
    source_type: CommunityNotificationSource
    status: CommunityNotificationOutboxStatus
    attempts: int
    available_at: datetime
    delivered_at: datetime | None
    failed_at: datetime | None
    last_error_code: str | None
    replay_count: int
    last_replayed_at: datetime | None
    last_replayed_by_username: str | None
    created_at: datetime
    updated_at: datetime


class AdminCommunityNotificationOutboxListResponse(BaseModel):
    items: list[AdminCommunityNotificationOutboxItem]
    page: int
    page_size: int
    total: int


class AdminCommunityNotificationOutboxMetrics(BaseModel):
    generated_at: datetime
    pending_count: int
    delivered_count: int
    failed_count: int
    failed_last_24_hours: int
    retry_due_count: int
    oldest_pending_seconds: int | None


class AdminCommunityNotificationReplayRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    reauth_token: str = Field(min_length=16, max_length=256)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.replace("\x00", "").strip()
        if len(normalized) < 3:
            raise ValueError("重放原因至少需要 3 个字符")
        return normalized


class AdminCommunityNotificationReplayResponse(BaseModel):
    event: AdminCommunityNotificationOutboxItem
    audit_id: str
    request_id: str | None


class AdminCommunitySearchProviderHealth(BaseModel):
    mode: str
    degraded: bool


class AdminCommunitySearchRebuildSummary(BaseModel):
    status: CommunitySearchRebuildStatus
    expected_count: int
    indexed_count: int
    missing_count: int
    extra_count: int
    started_at: datetime | None
    finished_at: datetime | None


class AdminCommunitySearchHealthResponse(BaseModel):
    generated_at: datetime
    provider: AdminCommunitySearchProviderHealth
    pending_count: int
    delivered_count: int
    failed_count: int
    retry_due_count: int
    oldest_pending_seconds: int | None
    last_delivered_at: datetime | None
    delivery_latency_buckets: dict[str, int]
    last_rebuild: AdminCommunitySearchRebuildSummary | None
