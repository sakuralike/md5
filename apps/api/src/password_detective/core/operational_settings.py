from __future__ import annotations

from typing import cast

from sqlalchemy.orm import Session

from password_detective.db.models.system_setting import SystemSetting


def get_operational_setting[T: (int, str)](db: Session, key: str, default: T) -> T:
    record = db.get(SystemSetting, key)
    if record is None:
        return default
    value = record.value_json.get("value")
    if isinstance(default, int) and isinstance(value, int) and not isinstance(value, bool):
        return cast(T, value)
    if isinstance(default, str) and isinstance(value, str):
        return cast(T, value)
    return default
