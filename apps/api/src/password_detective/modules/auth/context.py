from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request


@dataclass(frozen=True)
class ClientContext:
    request_id: str | None
    ip_prefix: str | None
    user_agent: str | None


def _mask_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    if ":" in ip:
        parts = ip.split(":")
        return ":".join(parts[:4]) + "::/64"
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3]) + ".0/24"
    return None


def get_client_context(request: Request) -> ClientContext:
    user_agent = request.headers.get("User-Agent")
    return ClientContext(
        request_id=getattr(request.state, "request_id", None),
        ip_prefix=_mask_ip(request.client.host if request.client else None),
        user_agent=user_agent[:255] if user_agent else None,
    )


def get_notification_gateway(request: Request):  # noqa: ANN201
    from password_detective.modules.admin.email_delivery import build_email_delivery_gateway

    with request.app.state.database.session_factory() as db:
        return build_email_delivery_gateway(
            db,
            settings=request.app.state.settings,
            fallback=request.app.state.notification_gateway,
        )
