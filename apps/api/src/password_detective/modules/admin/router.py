from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.browser_session import (
    clear_refresh_cookie,
    enforce_browser_origin,
    require_refresh_cookie,
    set_refresh_cookie,
)
from password_detective.core.config import Settings, get_settings
from password_detective.core.errors import AppError
from password_detective.core.rate_limit import rate_limit
from password_detective.core.security import hash_refresh_token
from password_detective.db.dependencies import get_db
from password_detective.db.models.user import UserRole
from password_detective.db.models.user_session import UserSession
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import (
    Principal,
    require_admin_mfa,
    require_roles,
)
from password_detective.modules.auth.schemas import (
    BrowserTokenResponse,
    LoginRequest,
    MessageResponse,
    TotpCodeRequest,
    TotpSetupResponse,
)
from password_detective.modules.auth.service import (
    login_user,
    revoke_by_refresh_token,
    revoke_session_family,
    rotate_refresh_token,
)
from password_detective.modules.auth.totp import begin_totp_setup, confirm_totp_setup, disable_totp

router = APIRouter(prefix="/admin", tags=["管理端"])


@router.post(
    "/auth/login",
    response_model=BrowserTokenResponse,
    dependencies=[Depends(rate_limit("admin.auth.login", limit=10, window_seconds=60))],
)
def admin_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BrowserTokenResponse:
    enforce_browser_origin(request, settings)
    context = get_client_context(request)
    tokens = login_user(db, settings, payload, context)
    if tokens.user.role not in {UserRole.MODERATOR, UserRole.ADMIN}:
        session = db.scalar(
            select(UserSession).where(
                UserSession.refresh_token_hash == hash_refresh_token(tokens.refresh_token)
            )
        )
        if session is not None:
            revoke_session_family(
                db,
                user_id=tokens.user.id,
                family_id=session.family_id,
                reason="admin_role_rejected",
                context=context,
            )
        raise AppError("auth.forbidden", "该账号没有管理端访问权限", status_code=403)
    set_refresh_cookie(response, settings, client="admin", refresh_token=tokens.refresh_token)
    return BrowserTokenResponse.from_token_response(tokens)


@router.post(
    "/auth/refresh",
    response_model=BrowserTokenResponse,
    dependencies=[Depends(rate_limit("admin.auth.refresh", limit=30, window_seconds=60))],
)
def admin_refresh(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BrowserTokenResponse:
    enforce_browser_origin(request, settings)
    refresh_token = require_refresh_cookie(request, client="admin")
    tokens = rotate_refresh_token(db, settings, refresh_token, get_client_context(request))
    set_refresh_cookie(response, settings, client="admin", refresh_token=tokens.refresh_token)
    return BrowserTokenResponse.from_token_response(tokens)


@router.post("/auth/logout", response_model=MessageResponse)
def admin_logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    enforce_browser_origin(request, settings)
    refresh_token = request.cookies.get("pd_admin_refresh")
    if refresh_token:
        revoke_by_refresh_token(
            db,
            refresh_token=refresh_token,
            reason="admin_logout",
            context=get_client_context(request),
        )
    clear_refresh_cookie(response, settings, client="admin")
    return MessageResponse(message="已退出管理端")


@router.get("/access-check")
def access_check(
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> dict[str, str]:
    return {"status": "authorized", "role": principal.user.role.value, "mfa": "verified"}


@router.post("/totp/setup", response_model=TotpSetupResponse)
def setup_totp(
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN)),
    ],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TotpSetupResponse:
    return begin_totp_setup(
        db,
        settings,
        user=principal.user,
        context=get_client_context(request),
    )


@router.post("/totp/confirm", response_model=MessageResponse)
def confirm_totp(
    payload: TotpCodeRequest,
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN)),
    ],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    confirm_totp_setup(
        db,
        settings,
        user=principal.user,
        session_family_id=principal.session_family_id,
        code=payload.code,
        context=get_client_context(request),
    )
    return MessageResponse(message="TOTP 已启用，请重新登录以进入管理端")


@router.post("/totp/disable", response_model=MessageResponse)
def remove_totp(
    payload: TotpCodeRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    disable_totp(
        db,
        settings,
        user=principal.user,
        code=payload.code,
        context=get_client_context(request),
    )
    return MessageResponse(message="TOTP 已停用")
