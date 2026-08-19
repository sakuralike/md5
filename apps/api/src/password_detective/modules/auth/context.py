from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from password_detective.core.client_ip import masked_ip_prefix, resolve_client_ip


@dataclass(frozen=True)
class ClientContext:
    request_id: str | None
    ip_prefix: str | None
    user_agent: str | None


def get_client_context(request: Request) -> ClientContext:
    user_agent = request.headers.get("User-Agent")
    client_ip = resolve_client_ip(
        request,
        trusted_proxy_cidrs=request.app.state.settings.trusted_proxy_cidrs,
    )
    return ClientContext(
        request_id=getattr(request.state, "request_id", None),
        ip_prefix=masked_ip_prefix(client_ip),
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
