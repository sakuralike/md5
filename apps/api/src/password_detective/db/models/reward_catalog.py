from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class RewardCatalogKind(StrEnum):
    VIRTUAL = "virtual"


class RewardCatalogStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"


class RewardCatalogItem(Base):
    __tablename__ = "reward_catalog_items"
    __table_args__ = (UniqueConstraint("slug", name="uq_reward_catalog_items_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    kind: Mapped[RewardCatalogKind] = mapped_column(
        Enum(RewardCatalogKind, native_enum=False, length=16),
        default=RewardCatalogKind.VIRTUAL,
    )
    cost_points: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer)
    per_user_limit: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(64), default="general", index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    sort_weight: Mapped[int] = mapped_column(Integer, default=0, index=True)
    entitlement_key: Mapped[str] = mapped_column(String(64), default="community_supporter")
    entitlement_duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    redeem_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    redeem_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    status: Mapped[RewardCatalogStatus] = mapped_column(
        Enum(RewardCatalogStatus, native_enum=False, length=16),
        default=RewardCatalogStatus.DRAFT,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    updated_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
