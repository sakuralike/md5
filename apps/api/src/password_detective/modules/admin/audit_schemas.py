from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, JsonValue

from password_detective.db.models.user import UserRole


class AdminAuditLogEntry(BaseModel):
    id: str
    actor_id: str | None
    actor_username: str | None
    actor_role: UserRole | None
    action: str
    target_type: str
    target_id: str | None
    result: str
    ip_prefix: str | None
    request_id: str | None
    details: dict[str, JsonValue]
    created_at: datetime


class AdminAuditLogListResponse(BaseModel):
    items: list[AdminAuditLogEntry]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
