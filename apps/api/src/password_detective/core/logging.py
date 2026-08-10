from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

SENSITIVE_KEYS = {
    "password",
    "candidate_password",
    "archive_password",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "secret",
    "secret_ciphertext",
    "secret_nonce",
}


class SensitiveDataFilter(logging.Filter):
    """Redact structured sensitive fields before any formatter or sink sees them."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, dict):
            record.msg = redact_value(record.msg)
        if isinstance(record.args, dict):
            record.args = redact_value(record.args)
        for key in list(record.__dict__):
            if key.lower() in SENSITIVE_KEYS:
                record.__dict__[key] = "[REDACTED]"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        if isinstance(record.msg, dict):
            payload.pop("message", None)
            payload.update(redact_value(record.msg))
        for field in ("request_id", "method", "route", "status_code", "duration_ms"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(redact_value(payload), ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(SensitiveDataFilter())
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def redact_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return redact_value(value)


def redact_value(value: Any, *, parent_key: str | None = None) -> Any:
    if parent_key and parent_key.lower() in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {key: redact_value(item, parent_key=str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    return value
