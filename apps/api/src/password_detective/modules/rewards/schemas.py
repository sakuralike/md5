from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from password_detective.db.models.reward_catalog import RewardCatalogKind, RewardCatalogStatus
from password_detective.db.models.reward_order import (
    RewardActorType,
    RewardDeliveryKind,
    RewardFulfillmentStatus,
    RewardInventoryEventType,
    RewardOrderStatus,
)

RewardEntitlementKey = Literal[
    "community_supporter",
    "priority_case_review",
    "daily_reveal_boost",
]
RewardInventoryReason = Literal["initial_stock", "restock", "correction", "campaign"]


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
    category: str
    tags: list[str]
    entitlement_key: str
    entitlement_duration_days: int | None
    redeem_start_at: datetime | None
    redeem_end_at: datetime | None
    stock_status: Literal["available", "limited", "out_of_stock"]
    redeem_status: Literal["available", "scheduled", "ended", "out_of_stock"]


class RewardCatalogResponse(BaseModel):
    items: list[RewardCatalogItemResponse]
    available_points: int | None
    categories: list[str]
    tags: list[str]


class AdminRewardCatalogItemResponse(RewardCatalogItemResponse):
    stock: int
    sort_weight: int
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


class _RewardCatalogWriteBase(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=2, max_length=2000)
    kind: Literal["virtual"] = "virtual"
    cost_points: int = Field(ge=1, le=1_000_000_000)
    per_user_limit: int = Field(ge=1, le=100_000)
    category: str = Field(
        default="general",
        min_length=2,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9_-]+$",
    )
    tags: list[str] = Field(default_factory=list, max_length=8)
    sort_weight: int = Field(default=0, ge=-100_000, le=100_000)
    entitlement_key: RewardEntitlementKey = "community_supporter"
    entitlement_duration_days: int | None = Field(default=None, ge=1, le=3650)
    redeem_start_at: datetime | None = None
    redeem_end_at: datetime | None = None
    status: RewardCatalogStatus
    reason_code: str = Field(min_length=2, max_length=100)

    @field_validator("name", "description", "reason_code")
    @classmethod
    def normalize_text(cls, value: str, info: ValidationInfo) -> str:
        return _plain_text(value, field_name=str(info.field_name))

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            tag = value.strip().lower()
            valid = 1 <= len(tag) <= 24 and all(
                character.isalnum() or character in "_-" for character in tag
            )
            if not valid:
                raise ValueError("标签只能包含字母、数字、下划线和连字符，长度为 1 至 24")
            if tag not in normalized:
                normalized.append(tag)
        return normalized

    @model_validator(mode="after")
    def validate_redeem_window(self) -> _RewardCatalogWriteBase:
        if (
            self.redeem_start_at
            and self.redeem_end_at
            and self.redeem_end_at <= self.redeem_start_at
        ):
            raise ValueError("兑换结束时间必须晚于开始时间")
        return self


class RewardCatalogCreateRequest(_RewardCatalogWriteBase):
    slug: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    stock: int = Field(ge=0, le=1_000_000_000)
    status: RewardCatalogStatus = RewardCatalogStatus.DRAFT

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        return value.strip().lower()


class RewardCatalogUpdateRequest(_RewardCatalogWriteBase):
    expected_version: int = Field(ge=1)


class RewardOrderCreateRequest(BaseModel):
    catalog_item_id: str = Field(min_length=1, max_length=36)
    quantity: int = Field(default=1, ge=1, le=10)


class RewardFulfillmentSummary(BaseModel):
    status: RewardFulfillmentStatus
    attempt_no: int
    result_code: str | None
    safe_message: str | None
    completed_at: datetime | None


class RewardOrderSummaryResponse(BaseModel):
    id: str
    order_no: str
    status: RewardOrderStatus
    catalog_item_id: str
    item_slug: str
    item_name: str
    quantity: int
    unit_cost_points: int
    total_cost_points: int
    created_at: datetime
    updated_at: datetime
    fulfilled_at: datetime | None
    cancelled_at: datetime | None
    compensated_at: datetime | None
    fulfillment: RewardFulfillmentSummary | None


class RewardOrderListResponse(BaseModel):
    items: list[RewardOrderSummaryResponse]
    page: int
    page_size: int
    total: int


class RewardOrderTimelineEvent(BaseModel):
    id: str
    from_status: RewardOrderStatus | None
    to_status: RewardOrderStatus
    event_type: str
    reason_code: str
    created_at: datetime


class RewardEntitlementGrantResponse(BaseModel):
    entitlement_key: str
    status: str
    starts_at: datetime
    expires_at: datetime | None


class RewardOrderDetailResponse(RewardOrderSummaryResponse):
    available_points: int
    timeline: list[RewardOrderTimelineEvent]
    entitlement: RewardEntitlementGrantResponse | None


class RewardOrderCreateResponse(RewardOrderDetailResponse):
    pass


class RewardInventoryAdjustmentRequest(BaseModel):
    delta: int = Field(ge=-1_000_000_000, le=1_000_000_000)
    reason_code: RewardInventoryReason
    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=300)

    @field_validator("delta")
    @classmethod
    def reject_zero_delta(cls, value: int) -> int:
        if value == 0:
            raise ValueError("库存调整量不能为 0")
        return value

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        return _plain_text(value, field_name="note") if value is not None else None


class RewardInventoryEventResponse(BaseModel):
    id: str
    catalog_item_id: str
    order_id: str | None
    event_type: RewardInventoryEventType
    delta: int
    stock_before: int
    stock_after: int
    actor_type: RewardActorType
    actor_id: str | None
    reason_code: str
    note: str | None
    created_at: datetime


class RewardInventoryEventListResponse(BaseModel):
    items: list[RewardInventoryEventResponse]
    page: int
    page_size: int
    total: int


class RewardAdminOrderActionRequest(BaseModel):
    expected_version: int = Field(ge=1)
    reason_code: str = Field(min_length=2, max_length=100)

    @field_validator("reason_code")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _plain_text(value, field_name="reason_code")


class RewardAdminFulfillmentResponse(BaseModel):
    id: str
    attempt_no: int
    delivery_kind: RewardDeliveryKind
    status: RewardFulfillmentStatus
    retry_count: int
    result_code: str | None
    safe_message: str | None
    next_retry_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class RewardAdminOrderResponse(RewardOrderSummaryResponse):
    user_id: str
    version: int
    failure_code: str | None
    points_ledger_entry_id: str
    compensation_ledger_entry_id: str | None
    fulfillments: list[RewardAdminFulfillmentResponse]
    inventory_events: list[RewardInventoryEventResponse]
    timeline: list[RewardOrderTimelineEvent]


class RewardAdminOrderListResponse(BaseModel):
    items: list[RewardAdminOrderResponse]
    page: int
    page_size: int
    total: int


class RewardOperationsStatsResponse(BaseModel):
    total_orders: int
    pending_orders: int
    fulfilled_orders: int
    failed_orders: int
    cancelled_orders: int
    redeemed_points: int
    compensated_points: int
    fulfillment_success_rate: float
    low_stock_items: int
