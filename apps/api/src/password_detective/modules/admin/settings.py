from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.system_setting import SystemSetting
from password_detective.modules.admin.setting_schemas import (
    OperationalSettingsResponse,
    OperationalSettingsSnapshot,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.reputation.levels import rebuild_all_level_profiles


def default_operational_settings() -> OperationalSettingsSnapshot:
    return OperationalSettingsSnapshot(
        daily_reveal_quota=20,
        reauthentication_ttl_minutes=5,
        privacy_deletion_grace_hours=72,
        desktop_min_client_version="1.0.0",
        desktop_update_download_cache_seconds=3600,
    )


def _current_settings(
    db: Session,
) -> tuple[OperationalSettingsSnapshot, datetime | None, str | None]:
    defaults = default_operational_settings().model_dump(mode="json")
    records = db.scalars(
        select(SystemSetting).where(SystemSetting.key.in_(tuple(defaults)))
    ).all()
    for record in records:
        value = record.value_json.get("value")
        if value is not None:
            defaults[record.key] = value
    snapshot = OperationalSettingsSnapshot.model_validate(defaults)
    latest = max(records, key=lambda record: record.updated_at, default=None)
    return snapshot, latest.updated_at if latest else None, latest.updated_by if latest else None


def get_current_settings(db: Session) -> OperationalSettingsResponse:
    settings, updated_at, updated_by = _current_settings(db)
    return OperationalSettingsResponse(
        settings=settings,
        updated_at=updated_at,
        updated_by=updated_by,
    )


def _apply_snapshot(
    db: Session,
    *,
    snapshot: OperationalSettingsSnapshot,
    actor_id: str,
) -> None:
    now = utc_now()
    for key, value in snapshot.model_dump(mode="json").items():
        record = db.get(SystemSetting, key)
        if record is None:
            db.add(
                SystemSetting(
                    key=key,
                    value_json={"value": value},
                    version=1,
                    updated_by=actor_id,
                    updated_at=now,
                )
            )
        else:
            record.value_json = {"value": value}
            record.version += 1
            record.updated_by = actor_id
            record.updated_at = now


def save_current_settings(
    db: Session,
    *,
    snapshot: OperationalSettingsSnapshot,
    principal: Principal,
    context: ClientContext,
) -> OperationalSettingsResponse:
    _apply_snapshot(db, snapshot=snapshot, actor_id=principal.user.id)
    db.flush()
    rebuilt_level_profiles = rebuild_all_level_profiles(db)
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.settings.saved",
        target_type="system_settings",
        target_id="current",
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "setting_keys": sorted(snapshot.model_dump(mode="json")),
            "rebuilt_level_profiles": rebuilt_level_profiles,
        },
    )
    db.commit()
    return get_current_settings(db)
