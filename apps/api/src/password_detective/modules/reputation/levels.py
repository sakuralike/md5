from __future__ import annotations

import hashlib
import json

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.models.system_setting import SystemSetting
from password_detective.db.models.user import User
from password_detective.db.models.user_growth_event import UserGrowthEvent
from password_detective.db.models.user_level_profile import UserLevelProfile
from password_detective.modules.admin.setting_schemas import (
    UserLevelDefinition,
    default_user_levels,
)
from password_detective.modules.reputation.schemas import (
    GrowthEventItem,
    GrowthEventsResponse,
    UserLevelCatalogResponse,
    UserLevelEntitlements,
    UserLevelProfileResponse,
    UserLevelSummary,
)
from password_detective.modules.rewards.entitlements import reward_daily_reveal_bonus

GROWTH_RULE_VERSION = "growth-v1"
DAILY_ACTIVITY_GROWTH = 5
VERIFIED_CONTRIBUTION_GROWTH = 100
ACCEPTED_VERIFICATION_GROWTH = 25
_LEVEL_ADAPTER = TypeAdapter(list[UserLevelDefinition])


def get_level_definitions(db: Session) -> list[UserLevelDefinition]:
    record = db.get(SystemSetting, "user_levels")
    raw = record.value_json.get("value") if record is not None else None
    if isinstance(raw, list):
        try:
            definitions = _LEVEL_ADAPTER.validate_python(raw)
            if definitions:
                return definitions
        except ValidationError:
            pass
    return default_user_levels()


def level_rule_hash(definitions: list[UserLevelDefinition]) -> str:
    payload = json.dumps(
        [item.model_dump(mode="json") for item in definitions],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _summary(item: UserLevelDefinition) -> UserLevelSummary:
    return UserLevelSummary(
        code=item.code,
        name=item.name,
        description=item.description,
        min_growth_points=item.min_growth_points,
        entitlements=UserLevelEntitlements(
            daily_reveal_quota=item.daily_reveal_quota,
            can_submit=item.can_submit,
        ),
    )


def _current_and_next(
    definitions: list[UserLevelDefinition], growth_points: int
) -> tuple[UserLevelDefinition, UserLevelDefinition | None]:
    current = definitions[0]
    next_level: UserLevelDefinition | None = None
    for index, definition in enumerate(definitions):
        if growth_points >= definition.min_growth_points:
            current = definition
            next_level = definitions[index + 1] if index + 1 < len(definitions) else None
        else:
            next_level = definition
            break
    return current, next_level


def _growth_points(db: Session, user_id: str) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(UserGrowthEvent.amount), 0)).where(
            UserGrowthEvent.user_id == user_id
        )
    )
    return max(int(total or 0), 0)


def sync_level_profile(db: Session, *, user_id: str) -> UserLevelProfile:
    definitions = get_level_definitions(db)
    growth_points = _growth_points(db, user_id)
    current, _ = _current_and_next(definitions, growth_points)
    rule_hash = level_rule_hash(definitions)
    profile = db.get(UserLevelProfile, user_id)
    if profile is None:
        profile = UserLevelProfile(
            user_id=user_id,
            growth_points=growth_points,
            level_code=current.code,
            level_name=current.name,
            level_rule_hash=rule_hash,
            evaluated_at=utc_now(),
        )
        db.add(profile)
    else:
        profile.growth_points = growth_points
        profile.level_code = current.code
        profile.level_name = current.name
        profile.level_rule_hash = rule_hash
        profile.evaluated_at = utc_now()
    db.flush()
    return profile


def record_growth_event(
    db: Session,
    *,
    user_id: str,
    amount: int,
    event_type: str,
    reference_id: str,
    reason_code: str,
    rule_version: str = GROWTH_RULE_VERSION,
) -> UserGrowthEvent:
    existing = db.scalar(
        select(UserGrowthEvent).where(
            UserGrowthEvent.user_id == user_id,
            UserGrowthEvent.event_type == event_type,
            UserGrowthEvent.reference_id == reference_id,
        )
    )
    if existing is not None:
        return existing
    event = UserGrowthEvent(
        user_id=user_id,
        amount=amount,
        event_type=event_type,
        reference_id=reference_id,
        reason_code=reason_code,
        rule_version=rule_version,
    )
    try:
        with db.begin_nested():
            db.add(event)
            db.flush()
    except IntegrityError:
        concurrent = db.scalar(
            select(UserGrowthEvent).where(
                UserGrowthEvent.user_id == user_id,
                UserGrowthEvent.event_type == event_type,
                UserGrowthEvent.reference_id == reference_id,
            )
        )
        if concurrent is None:
            raise
        return concurrent
    sync_level_profile(db, user_id=user_id)
    return event


def get_user_level_profile(db: Session, *, user_id: str) -> UserLevelProfileResponse:
    definitions = get_level_definitions(db)
    growth_points = _growth_points(db, user_id)
    current, next_level = _current_and_next(definitions, growth_points)
    if next_level is None:
        progress_percent = 100
        points_to_next = 0
    else:
        span = next_level.min_growth_points - current.min_growth_points
        completed = growth_points - current.min_growth_points
        progress_percent = min(max(int(completed * 100 / span), 0), 100)
        points_to_next = max(next_level.min_growth_points - growth_points, 0)
    return UserLevelProfileResponse(
        growth_points=growth_points,
        current=_summary(current),
        next=_summary(next_level) if next_level is not None else None,
        progress_percent=progress_percent,
        points_to_next_level=points_to_next,
        rule_hash=level_rule_hash(definitions),
    )


def get_level_catalog(db: Session) -> UserLevelCatalogResponse:
    definitions = get_level_definitions(db)
    return UserLevelCatalogResponse(
        items=[_summary(item) for item in definitions],
        rule_hash=level_rule_hash(definitions),
    )


def list_growth_events(
    db: Session, *, user_id: str, page: int, page_size: int
) -> GrowthEventsResponse:
    total = db.scalar(
        select(func.count(UserGrowthEvent.id)).where(UserGrowthEvent.user_id == user_id)
    ) or 0
    records = db.scalars(
        select(UserGrowthEvent)
        .where(UserGrowthEvent.user_id == user_id)
        .order_by(desc(UserGrowthEvent.created_at), desc(UserGrowthEvent.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return GrowthEventsResponse(
        items=[GrowthEventItem.model_validate(record, from_attributes=True) for record in records],
        page=page,
        page_size=page_size,
        total=total,
    )


def rebuild_all_level_profiles(db: Session) -> int:
    definitions = get_level_definitions(db)
    rule_hash = level_rule_hash(definitions)
    evaluated_at = utc_now()
    growth_by_user = {
        user_id: max(int(total or 0), 0)
        for user_id, total in db.execute(
            select(UserGrowthEvent.user_id, func.sum(UserGrowthEvent.amount)).group_by(
                UserGrowthEvent.user_id
            )
        )
    }
    profiles = {
        profile.user_id: profile for profile in db.scalars(select(UserLevelProfile))
    }
    user_ids = list(db.scalars(select(User.id)))
    for user_id in user_ids:
        growth_points = growth_by_user.get(user_id, 0)
        current, _ = _current_and_next(definitions, growth_points)
        profile = profiles.get(user_id)
        if profile is None:
            db.add(
                UserLevelProfile(
                    user_id=user_id,
                    growth_points=growth_points,
                    level_code=current.code,
                    level_name=current.name,
                    level_rule_hash=rule_hash,
                    evaluated_at=evaluated_at,
                )
            )
            continue
        profile.growth_points = growth_points
        profile.level_code = current.code
        profile.level_name = current.name
        profile.level_rule_hash = rule_hash
        profile.evaluated_at = evaluated_at
    db.flush()
    return len(user_ids)


def daily_reveal_quota_for_user(db: Session, *, user_id: str, baseline: int) -> int:
    profile = get_user_level_profile(db, user_id=user_id)
    base_quota = max(baseline, profile.current.entitlements.daily_reveal_quota)
    return base_quota + reward_daily_reveal_bonus(db, user_id=user_id)


def require_submission_entitlement(db: Session, *, user_id: str) -> None:
    profile = get_user_level_profile(db, user_id=user_id)
    if not profile.current.entitlements.can_submit:
        raise AppError(
            "level.submission_not_allowed",
            "当前用户等级没有数据提交权限",
            status_code=403,
            details={"level_code": profile.current.code},
        )
