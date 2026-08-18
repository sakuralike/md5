from __future__ import annotations

from datetime import datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.system_setting import SystemSetting
from password_detective.modules.admin.setting_schemas import SeoSettings, SeoSettingsResponse
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal

SEO_SETTINGS_KEY = "seo_settings"


def default_seo_settings() -> SeoSettings:
    return SeoSettings()


def _current_seo_settings(
    db: Session,
) -> tuple[SeoSettings, datetime | None, str | None]:
    record = db.get(SystemSetting, SEO_SETTINGS_KEY)
    if record is None:
        return default_seo_settings(), None, None

    raw_value = record.value_json.get("value")
    try:
        settings = SeoSettings.model_validate(raw_value)
    except (TypeError, ValidationError):
        settings = default_seo_settings()
    return settings, record.updated_at, record.updated_by


def get_seo_settings(db: Session) -> SeoSettingsResponse:
    settings, updated_at, updated_by = _current_seo_settings(db)
    return SeoSettingsResponse(
        settings=settings,
        updated_at=updated_at,
        updated_by=updated_by,
    )


def save_seo_settings(
    db: Session,
    *,
    settings: SeoSettings,
    principal: Principal,
    context: ClientContext,
) -> SeoSettingsResponse:
    now = utc_now()
    record = db.get(SystemSetting, SEO_SETTINGS_KEY)
    value_json = {"value": settings.model_dump(mode="json")}
    if record is None:
        db.add(
            SystemSetting(
                key=SEO_SETTINGS_KEY,
                value_json=value_json,
                version=1,
                updated_by=principal.user.id,
                updated_at=now,
            )
        )
    else:
        record.value_json = value_json
        record.version += 1
        record.updated_by = principal.user.id
        record.updated_at = now

    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.settings.seo.saved",
        target_type="seo_settings",
        target_id="current",
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "setting_key": SEO_SETTINGS_KEY,
            "operation": "direct_save",
        },
    )
    db.commit()
    return get_seo_settings(db)
