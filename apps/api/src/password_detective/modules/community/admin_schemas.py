from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from password_detective.db.models.community import (
    CommunityBoardStatus,
    CommunityContentStatus,
    CommunityModerationAction,
    CommunityReportDecision,
    CommunityReportReason,
    CommunityReportStatus,
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
