from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from password_detective.core.time import utc_now
from password_detective.db.models.reward_order import (
    RewardEntitlementGrant,
    RewardEntitlementStatus,
    RewardOrder,
)


def _active_grant_condition(now: datetime):
    return (
        RewardEntitlementGrant.status == RewardEntitlementStatus.ACTIVE,
        RewardEntitlementGrant.starts_at <= now,
        or_(
            RewardEntitlementGrant.expires_at.is_(None),
            RewardEntitlementGrant.expires_at > now,
        ),
        RewardEntitlementGrant.revoked_at.is_(None),
    )


def has_active_reward_entitlement(
    db: Session,
    *,
    user_id: str,
    entitlement_key: str,
    now: datetime | None = None,
) -> bool:
    current = now or utc_now()
    return (
        db.scalar(
            select(RewardEntitlementGrant.id)
            .where(
                RewardEntitlementGrant.user_id == user_id,
                RewardEntitlementGrant.entitlement_key == entitlement_key,
                *_active_grant_condition(current),
            )
            .limit(1)
        )
        is not None
    )


def reward_daily_reveal_bonus(
    db: Session,
    *,
    user_id: str,
    now: datetime | None = None,
) -> int:
    """Return one extra daily reveal per active boost unit."""
    current = now or utc_now()
    total = db.scalar(
        select(func.coalesce(func.sum(RewardOrder.quantity), 0))
        .select_from(RewardEntitlementGrant)
        .join(RewardOrder, RewardOrder.id == RewardEntitlementGrant.order_id)
        .where(
            RewardEntitlementGrant.user_id == user_id,
            RewardEntitlementGrant.entitlement_key == "daily_reveal_boost",
            *_active_grant_condition(current),
        )
    )
    return max(int(total or 0), 0)


def reward_priority_case_review_enabled(
    db: Session,
    *,
    user_id: str,
    now: datetime | None = None,
) -> bool:
    return has_active_reward_entitlement(
        db,
        user_id=user_id,
        entitlement_key="priority_case_review",
        now=now,
    )


def reward_community_supporter_enabled(
    db: Session,
    *,
    user_id: str,
    now: datetime | None = None,
) -> bool:
    return has_active_reward_entitlement(
        db,
        user_id=user_id,
        entitlement_key="community_supporter",
        now=now,
    )
