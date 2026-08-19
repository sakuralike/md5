from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from password_detective.db.models.reward_catalog import RewardCatalogKind, RewardCatalogStatus


def _plain_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if any(ord(character) < 32 and character not in {"\n", "\r", "\t"} for character in normalized):
        raise ValueError(f"{field_name}不能包含控制字符")
    if any(character in normalized for character in ("<", ">")):
        raise ValueError(f"{field_name}不能包含 HTML 标签")
    if "http://" in normalized.lower() or "https://" in normalized.lower():
        raise ValueError(f"{field_name}不能包含外部链接")
    if "utm_" in normalized.lower():
        raise ValueError(f"{field_name}不能包含外部追踪参数")
    return normalized


class RewardCatalogItemResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    kind: RewardCatalogKind
    cost_points: int
    per_user_limit: int
    stock_status: Literal["available", "limited", "out_of_stock"]


class RewardCatalogResponse(BaseModel):
    items: list[RewardCatalogItemResponse]
    available_points: int | None


class AdminRewardCatalogItemResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    kind: RewardCatalogKind
    cost_points: int
    stock: int
    per_user_limit: int
    stock_status: Literal["available", "limited", "out_of_stock"]
    status: RewardCatalogStatus
    version: int
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class AdminRewardCatalogListResponse(BaseModel):
    items: list[AdminRewardCatalogItemResponse]
    page: int
    page_size: int
    total: int


class RewardCatalogCreateRequest(BaseModel):
    slug: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=2, max_length=2000)
    kind: Literal["virtual"] = "virtual"
    cost_points: int = Field(ge=1, le=1_000_000_000)
    stock: int = Field(ge=0, le=1_000_000_000)
    per_user_limit: int = Field(ge=1, le=100_000)
    status: RewardCatalogStatus = RewardCatalogStatus.DRAFT
    reason_code: str = Field(min_length=2, max_length=100)

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("name", "description", "reason_code")
    @classmethod
    def normalize_text(cls, value: str, info: ValidationInfo) -> str:
        return _plain_text(value, field_name=str(info.field_name))


class RewardCatalogUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=2, max_length=2000)
    kind: Literal["virtual"] = "virtual"
    cost_points: int = Field(ge=1, le=1_000_000_000)
    stock: int = Field(ge=0, le=1_000_000_000)
    per_user_limit: int = Field(ge=1, le=100_000)
    status: RewardCatalogStatus
    expected_version: int = Field(ge=1)
    reason_code: str = Field(min_length=2, max_length=100)

    @field_validator("name", "description", "reason_code")
    @classmethod
    def normalize_text(cls, value: str, info: ValidationInfo) -> str:
        return _plain_text(value, field_name=str(info.field_name))
