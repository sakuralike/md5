from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.db.models.user_session import UserSession
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import Principal, get_current_principal
from password_detective.modules.auth.schemas import (
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    SessionResponse,
    TokenResponse,
    UserResponse,
)
from password_detective.modules.auth.service import (
    login_user,
    register_user,
    revoke_all_sessions,
    revoke_session_family,
    rotate_refresh_token,
)

router = APIRouter(tags=["认证与账号"])


@router.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("auth.register", limit=10, window_seconds=3600))],
)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    return register_user(db, payload, get_client_context(request))


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("auth.login", limit=10, window_seconds=60))],
)
def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    return login_user(db, settings, payload, get_client_context(request))


@router.post(
    "/auth/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("auth.refresh", limit=30, window_seconds=60))],
)
def refresh(
    payload: RefreshRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    return rotate_refresh_token(db, settings, payload.refresh_token, get_client_context(request))


@router.post("/auth/logout", response_model=MessageResponse)
def logout(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    revoke_session_family(
        db,
        user_id=principal.user.id,
        family_id=principal.session_family_id,
        reason="logout",
        context=get_client_context(request),
    )
    return MessageResponse(message="已退出当前会话")


@router.post("/auth/logout-all", response_model=MessageResponse)
def logout_all(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    revoke_all_sessions(db, user_id=principal.user.id, context=get_client_context(request))
    return MessageResponse(message="已退出全部会话")


@router.get("/me/profile", response_model=UserResponse)
def profile(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> UserResponse:
    return principal.user


@router.get("/me/security/sessions", response_model=list[SessionResponse])
def sessions(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SessionResponse]:
    rows = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == principal.user.id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.last_used_at.desc())
    ).all()
    return [
        SessionResponse(
            id=row.family_id,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            expires_at=row.expires_at,
            user_agent=row.user_agent,
            ip_prefix=row.ip_prefix,
            current=row.family_id == principal.session_family_id,
        )
        for row in rows
    ]


@router.delete("/me/security/sessions/{family_id}", response_model=MessageResponse)
def revoke_session(
    family_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    revoke_session_family(
        db,
        user_id=principal.user.id,
        family_id=family_id,
        reason="user_revoked",
        context=get_client_context(request),
    )
    return MessageResponse(message="会话已撤销")
