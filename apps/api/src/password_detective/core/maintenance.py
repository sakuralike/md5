from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from password_detective.core.client_ip import (
    address_in_networks,
    normalize_network_cidrs,
    parse_network_cidrs,
    resolve_client_ip,
)
from password_detective.db.models.system_setting import SystemSetting

DEFAULT_MAINTENANCE_MESSAGE = "系统正在维护，请稍后再试。"
MAINTENANCE_RETRY_AFTER_SECONDS = 300
_SETTING_KEYS = (
    "maintenance_enabled",
    "maintenance_message",
    "maintenance_allowed_ip_cidrs",
)
_EXEMPT_PATHS = {
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/api/v1/metrics",
    "/api/v1/site/config",
}
_EXEMPT_PREFIXES = ("/api/v1/site/assets/logo/",)


@dataclass(frozen=True)
class MaintenanceRuntimeConfig:
    enabled: bool
    message: str
    allowed_ip_cidrs: tuple[str, ...]


def _setting_value(records: dict[str, SystemSetting], key: str, default: object) -> object:
    record = records.get(key)
    if record is None:
        return default
    return record.value_json.get("value", default)


def load_maintenance_runtime_config(db: Session) -> MaintenanceRuntimeConfig:
    rows = db.scalars(select(SystemSetting).where(SystemSetting.key.in_(_SETTING_KEYS))).all()
    records = {row.key: row for row in rows}
    raw_enabled = _setting_value(records, "maintenance_enabled", False)
    enabled = raw_enabled if isinstance(raw_enabled, bool) else "maintenance_enabled" in records

    raw_message = _setting_value(records, "maintenance_message", DEFAULT_MAINTENANCE_MESSAGE)
    message = raw_message.strip() if isinstance(raw_message, str) else DEFAULT_MAINTENANCE_MESSAGE
    if (
        not message
        or "<" in message
        or ">" in message
        or any(
            (ord(character) < 32 and character not in {"\r", "\n", "\t"})
            or ord(character) == 127
            for character in message
        )
    ):
        message = DEFAULT_MAINTENANCE_MESSAGE

    raw_cidrs = _setting_value(records, "maintenance_allowed_ip_cidrs", [])
    try:
        cidrs = (
            normalize_network_cidrs(raw_cidrs)
            if isinstance(raw_cidrs, list) and all(isinstance(item, str) for item in raw_cidrs)
            else []
        )
    except ValueError:
        cidrs = []
    return MaintenanceRuntimeConfig(
        enabled=enabled,
        message=message,
        allowed_ip_cidrs=tuple(cidrs),
    )


def _is_exempt(request: Request) -> bool:
    if request.method == "OPTIONS":
        return True
    path = request.url.path.rstrip("/") or "/"
    return path in _EXEMPT_PATHS or any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES)


class MaintenanceModeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = request.app.state.settings
        if settings.maintenance_force_disabled or _is_exempt(request):
            return await call_next(request)

        def read_runtime_config() -> MaintenanceRuntimeConfig:
            with request.app.state.database.session_factory() as db:
                return load_maintenance_runtime_config(db)

        runtime = await run_in_threadpool(read_runtime_config)
        if not runtime.enabled:
            return await call_next(request)

        client_ip = resolve_client_ip(
            request,
            trusted_proxy_cidrs=settings.trusted_proxy_cidrs,
        )
        allowed_networks = parse_network_cidrs(runtime.allowed_ip_cidrs)
        if client_ip is not None and address_in_networks(client_ip, allowed_networks):
            return await call_next(request)

        return JSONResponse(
            status_code=503,
            content={
                "code": "maintenance.active",
                "message": runtime.message,
                "details": {"retry_after_seconds": MAINTENANCE_RETRY_AFTER_SECONDS},
                "request_id": getattr(request.state, "request_id", None),
            },
            headers={"Retry-After": str(MAINTENANCE_RETRY_AFTER_SECONDS)},
        )
