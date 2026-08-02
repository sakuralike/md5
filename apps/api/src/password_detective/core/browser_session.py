from __future__ import annotations

from typing import Literal

from fastapi import Request, Response

from password_detective.core.config import Settings
from password_detective.core.errors import AppError

BrowserClient = Literal["web", "admin"]


def cookie_name(client: BrowserClient) -> str:
    return f"pd_{client}_refresh"


def cookie_path(client: BrowserClient) -> str:
    return f"/api/v1/{client}/auth"


def set_refresh_cookie(
    response: Response,
    settings: Settings,
    *,
    client: BrowserClient,
    refresh_token: str,
) -> None:
    response.set_cookie(
        key=cookie_name(client),
        value=refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.browser_cookie_secure,
        samesite="lax",
        path=cookie_path(client),
    )


def clear_refresh_cookie(response: Response, settings: Settings, *, client: BrowserClient) -> None:
    response.delete_cookie(
        key=cookie_name(client),
        httponly=True,
        secure=settings.browser_cookie_secure,
        samesite="lax",
        path=cookie_path(client),
    )


def require_refresh_cookie(request: Request, *, client: BrowserClient) -> str:
    token = request.cookies.get(cookie_name(client))
    if not token:
        raise AppError("auth.authentication_required", "需要登录", status_code=401)
    return token


def enforce_browser_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("Origin")
    if origin and origin not in settings.cors_origin_list:
        raise AppError("request.invalid_origin", "请求来源不受信任", status_code=403)
