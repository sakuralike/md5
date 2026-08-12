from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.errors import AppError
from password_detective.core.security import decode_access_token
from password_detective.core.time import utc_now
from password_detective.db.dependencies import get_db
from password_detective.db.models.user import User, UserRole, UserStatus
from password_detective.db.models.user_session import UserSession

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user: User
    session_family_id: str
    mfa_verified: bool


def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError("auth.authentication_required", "需要登录", status_code=401)
    return _resolve_principal(request, credentials.credentials, db, settings)


def get_optional_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal | None:
    if credentials is None:
        return None
    if credentials.scheme.lower() != "bearer":
        raise AppError("auth.authentication_required", "需要登录", status_code=401)
    return _resolve_principal(request, credentials.credentials, db, settings)


def _resolve_principal(
    request: Request,
    access_token: str,
    db: Session,
    settings: Settings,
) -> Principal:
    claims = decode_access_token(access_token, settings.app_secret_key)
    user = db.get(User, claims.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise AppError("auth.account_unavailable", "账号当前不可用", status_code=403)
    now = utc_now()
    active_session = db.scalar(
        select(UserSession.id).where(
            UserSession.user_id == user.id,
            UserSession.family_id == claims.session_family_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
    )
    if active_session is None:
        raise AppError("auth.session_revoked", "登录会话已失效", status_code=401)
    request.state.user_id = user.id
    return Principal(
        user=user,
        session_family_id=claims.session_family_id,
        mfa_verified=claims.mfa_verified,
    )


def require_roles(*roles: UserRole):
    allowed = set(roles)

    def dependency(principal: Annotated[Principal, Depends(get_current_principal)]) -> Principal:
        if principal.user.role not in allowed:
            raise AppError("auth.forbidden", "没有执行该操作的权限", status_code=403)
        return principal

    return dependency


def require_admin_mfa(
    principal: Annotated[
        Principal,
        Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN)),
    ],
) -> Principal:
    if not principal.user.totp_enabled:
        raise AppError("auth.totp_setup_required", "管理员必须先启用 TOTP", status_code=403)
    if not principal.mfa_verified:
        raise AppError("auth.totp_required", "该管理操作需要 TOTP 验证", status_code=403)
    return principal


def require_admin_only_mfa(
    principal: Annotated[Principal, Depends(require_roles(UserRole.ADMIN))],
) -> Principal:
    if not principal.user.totp_enabled:
        raise AppError("auth.totp_setup_required", "管理员必须先启用 TOTP", status_code=403)
    if not principal.mfa_verified:
        raise AppError("auth.totp_required", "该管理操作需要 TOTP 验证", status_code=403)
    return principal
