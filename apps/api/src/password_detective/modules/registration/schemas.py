from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

RegistrationMode = Literal["open", "invite_only"]
RegistrationInviteStatus = Literal["active", "exhausted", "expired", "revoked"]


class RegistrationPolicyResponse(BaseModel):
    mode: RegistrationMode = "open"


class RegistrationPolicyUpdate(BaseModel):
    mode: RegistrationMode


class RegistrationInviteCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    max_uses: int = Field(default=1, ge=1, le=10_000)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def normalize_label(self) -> RegistrationInviteCreateRequest:
        self.label = self.label.strip()
        if not self.label:
            raise ValueError("邀请码名称不能为空")
        return self


class RegistrationInviteResponse(BaseModel):
    id: str
    label: str
    max_uses: int
    use_count: int
    remaining_uses: int
    status: RegistrationInviteStatus
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class RegistrationInviteCreatedResponse(RegistrationInviteResponse):
    code: str


class RegistrationInviteListResponse(BaseModel):
    items: list[RegistrationInviteResponse]
    total: int

