from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base
from password_detective.db.models.reward_catalog import RewardCatalogKind


class RewardOrderStatus(StrEnum):
    PENDING_FULFILLMENT = "pending_fulfillment"
    PROCESSING = "processing"
    FULFILLED = "fulfilled"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RewardActorType(StrEnum):
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class RewardInventoryEventType(StrEnum):
    REDEEMED = "redeemed"
    RELEASED = "released"
    ADMIN_ADJUSTED = "admin_adjusted"


class RewardDeliveryKind(StrEnum):
    INTERNAL_ENTITLEMENT = "internal_entitlement"


class RewardFulfillmentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    RETRYABLE = "retryable"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RewardEntitlementStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    FAILED = "failed"


class RewardOrder(Base):
    __tablename__ = "reward_orders"
    __table_args__ = (UniqueConstraint("order_no", name="uq_reward_orders_order_no"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_no: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[RewardOrderStatus] = mapped_column(
        Enum(RewardOrderStatus, native_enum=False, length=32),
        default=RewardOrderStatus.PENDING_FULFILLMENT,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cost_points: Mapped[int] = mapped_column(Integer)
    total_cost_points: Mapped[int] = mapped_column(Integer)
    catalog_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reward_catalog_items.id", ondelete="RESTRICT"), index=True
    )
    catalog_version: Mapped[int] = mapped_column(Integer)
    item_slug_snapshot: Mapped[str] = mapped_column(String(64))
    item_name_snapshot: Mapped[str] = mapped_column(String(100))
    entitlement_key_snapshot: Mapped[str] = mapped_column(String(64))
    entitlement_duration_days_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    points_ledger_entry_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("points_ledger.id", ondelete="RESTRICT"), unique=True
    )
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    compensation_ledger_entry_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("points_ledger.id", ondelete="RESTRICT"), unique=True, nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    compensated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RewardOrderItem(Base):
    __tablename__ = "reward_order_items"
    __table_args__ = (
        CheckConstraint(
            "kind_snapshot = 'VIRTUAL'",
            name="ck_reward_order_items_virtual_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reward_orders.id", ondelete="CASCADE"), index=True
    )
    catalog_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reward_catalog_items.id", ondelete="RESTRICT"), index=True
    )
    item_slug_snapshot: Mapped[str] = mapped_column(String(64))
    item_name_snapshot: Mapped[str] = mapped_column(String(100))
    kind_snapshot: Mapped[RewardCatalogKind] = mapped_column(
        Enum(RewardCatalogKind, native_enum=False, length=16)
    )
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cost_points: Mapped[int] = mapped_column(Integer)
    total_cost_points: Mapped[int] = mapped_column(Integer)
    catalog_version: Mapped[int] = mapped_column(Integer)


class RewardInventoryEvent(Base):
    __tablename__ = "reward_inventory_events"
    __table_args__ = (
        UniqueConstraint("event_type", "reference_key", name="uq_reward_inventory_event_ref"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    catalog_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reward_catalog_items.id", ondelete="RESTRICT"), index=True
    )
    order_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("reward_orders.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    event_type: Mapped[RewardInventoryEventType] = mapped_column(
        Enum(RewardInventoryEventType, native_enum=False, length=24), index=True
    )
    delta: Mapped[int] = mapped_column(Integer)
    stock_before: Mapped[int] = mapped_column(Integer)
    stock_after: Mapped[int] = mapped_column(Integer)
    actor_type: Mapped[RewardActorType] = mapped_column(
        Enum(RewardActorType, native_enum=False, length=16)
    )
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    reason_code: Mapped[str] = mapped_column(String(100))
    reference_key: Mapped[str] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class RewardOrderEvent(Base):
    __tablename__ = "reward_order_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reward_orders.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[RewardOrderStatus | None] = mapped_column(
        Enum(RewardOrderStatus, native_enum=False, length=32), nullable=True
    )
    to_status: Mapped[RewardOrderStatus] = mapped_column(
        Enum(RewardOrderStatus, native_enum=False, length=32), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor_type: Mapped[RewardActorType] = mapped_column(
        Enum(RewardActorType, native_enum=False, length=16)
    )
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason_code: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class RewardFulfillment(Base):
    __tablename__ = "reward_fulfillments"
    __table_args__ = (
        UniqueConstraint("order_id", "attempt_no", name="uq_reward_fulfillment_attempt"),
        CheckConstraint(
            "delivery_kind = 'INTERNAL_ENTITLEMENT'",
            name="ck_reward_fulfillments_internal_entitlement",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reward_orders.id", ondelete="CASCADE"), index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer)
    delivery_kind: Mapped[RewardDeliveryKind] = mapped_column(
        Enum(RewardDeliveryKind, native_enum=False, length=32),
        default=RewardDeliveryKind.INTERNAL_ENTITLEMENT,
    )
    status: Mapped[RewardFulfillmentStatus] = mapped_column(
        Enum(RewardFulfillmentStatus, native_enum=False, length=16),
        default=RewardFulfillmentStatus.PENDING,
        index=True,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    result_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    safe_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RewardEntitlementGrant(Base):
    __tablename__ = "reward_entitlement_grants"
    __table_args__ = (
        UniqueConstraint("order_id", "entitlement_key", name="uq_reward_entitlement_order_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reward_orders.id", ondelete="RESTRICT"), index=True
    )
    entitlement_key: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[RewardEntitlementStatus] = mapped_column(
        Enum(RewardEntitlementStatus, native_enum=False, length=16),
        default=RewardEntitlementStatus.ACTIVE,
        index=True,
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
