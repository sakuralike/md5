from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.errors import AppError
from password_detective.core.security import ThirdPartyAccessClaims, decode_third_party_access_token
from password_detective.core.time import utc_now
from password_detective.db.dependencies import get_db
from password_detective.db.models.third_party_app import ThirdPartyApp, ThirdPartyAppStatus
from password_detective.db.models.third_party_oauth import (
    OAuthTokenSession,
    ThirdPartyAuthorization,
)
from password_detective.db.models.user import User, UserStatus

_bearer = HTTPBearer(auto_error=False)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


@dataclass(frozen=True)
class ThirdPartyPrincipal:
    user: User
    app: ThirdPartyApp
    authorization: ThirdPartyAuthorization
    session: OAuthTokenSession
    claims: ThirdPartyAccessClaims


def get_current_third_party_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ThirdPartyPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            "third_party_oauth.authentication_required", "需要第三方访问令牌", status_code=401
        )
    claims = decode_third_party_access_token(credentials.credentials, settings.app_secret_key)
    session = db.get(OAuthTokenSession, claims.token_session_id)
    app = db.scalar(select(ThirdPartyApp).where(ThirdPartyApp.id == claims.app_id))
    user = db.get(User, claims.user_id)
    authorization = db.get(ThirdPartyAuthorization, session.authorization_id) if session else None
    now = utc_now()
    if (
        session is None
        or app is None
        or app.status != ThirdPartyAppStatus.APPROVED
        or user is None
        or user.status != UserStatus.ACTIVE
        or authorization is None
        or authorization.revoked_at is not None
        or authorization.user_id != user.id
        or authorization.app_id != app.id
        or session.revoked_at is not None
        or session.user_id != user.id
        or session.app_id != app.id
        or app.client_id != claims.client_id
        or session.token_family_id != claims.token_family_id
        or _aware(session.access_expires_at) <= now
    ):
        raise AppError(
            "third_party_oauth.session_unavailable", "第三方授权会话已失效", status_code=401
        )
    request.state.third_party_app_id = app.id
    request.state.user_id = user.id
    return ThirdPartyPrincipal(
        user=user, app=app, authorization=authorization, session=session, claims=claims
    )


def require_third_party_scope(scope: str):
    def dependency(
        principal: Annotated[ThirdPartyPrincipal, Depends(get_current_third_party_principal)],
    ) -> ThirdPartyPrincipal:
        if scope not in principal.claims.scopes:
            raise AppError(
                "third_party_oauth.insufficient_scope", "第三方令牌缺少所需 Scope", status_code=403
            )
        return principal

    return dependency
