from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.errors import AppError
from password_detective.db.dependencies import get_db
from password_detective.modules.auth.dependencies import Principal, get_current_principal
from password_detective.modules.third_party_oauth.dependencies import (
    ThirdPartyPrincipal,
    require_third_party_scope,
)
from password_detective.modules.third_party_oauth.schemas import (
    AuthorizedApplicationListResponse,
    OAuthRevokeRequest,
    OAuthTokenRequest,
    OAuthTokenResponse,
    ThirdPartyAuthorizationDecisionRequest,
    ThirdPartyAuthorizationDecisionResponse,
    ThirdPartyAuthorizationDetails,
    ThirdPartyAuthorizationRequest,
    ThirdPartyPrincipalResponse,
)
from password_detective.modules.third_party_oauth.service import (
    authorize,
    decide_authorization,
    exchange_authorization_code,
    get_authorization_details,
    list_authorized_applications,
    revoke_authorization,
    revoke_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/third-party/oauth", tags=["第三方 OAuth"])


@router.get("/authorize")
def oauth_authorize(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    response_type: Annotated[str, Query(min_length=1, max_length=32)],
    client_id: Annotated[str, Query(min_length=8, max_length=128)],
    redirect_uri: Annotated[str, Query(min_length=1, max_length=2_000)],
    code_challenge: Annotated[str, Query(min_length=43, max_length=128)],
    state: Annotated[str, Query(min_length=16, max_length=256)],
    code_challenge_method: Annotated[str, Query(min_length=1, max_length=8)] = "S256",
    scope: Annotated[str | None, Query(max_length=1_000)] = None,
) -> RedirectResponse:
    location = authorize(
        db,
        client_id=client_id,
        redirect_uri=redirect_uri,
        response_type=response_type,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        scope=scope,
        state=state,
        user=principal.user,
    )
    return RedirectResponse(location, status_code=302)


@router.get("/consent", response_model=ThirdPartyAuthorizationDetails)
def oauth_consent_details(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    request: Annotated[ThirdPartyAuthorizationRequest, Depends()],
) -> ThirdPartyAuthorizationDetails:
    return get_authorization_details(db, user=principal.user, request=request)


@router.post("/consent", response_model=ThirdPartyAuthorizationDecisionResponse)
def oauth_consent_decision(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    payload: ThirdPartyAuthorizationDecisionRequest,
) -> ThirdPartyAuthorizationDecisionResponse:
    location = decide_authorization(
        db,
        user=principal.user,
        request=payload,
        decision=payload.decision,
    )
    return ThirdPartyAuthorizationDecisionResponse(redirect_url=location)


@router.get("/authorized-applications", response_model=AuthorizedApplicationListResponse)
def oauth_authorized_applications(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthorizedApplicationListResponse:
    return AuthorizedApplicationListResponse(
        items=list_authorized_applications(db, user=principal.user)
    )


@router.delete("/authorized-applications/{app_id}", status_code=204)
def oauth_revoke_authorized_application(
    app_id: str,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    revoke_authorization(db, user=principal.user, app_id=app_id)


@router.post("/token", response_model=OAuthTokenResponse)
def oauth_token(
    payload: OAuthTokenRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OAuthTokenResponse:
    if payload.grant_type == "authorization_code":
        if not payload.code or not payload.redirect_uri or not payload.code_verifier:
            raise AppError(
                "third_party_oauth.invalid_request", "授权码交换缺少参数", status_code=400
            )
        access, refresh, expires_in, scopes = exchange_authorization_code(
            db,
            settings,
            client_id=payload.client_id,
            raw_code=payload.code,
            redirect_uri=payload.redirect_uri,
            code_verifier=payload.code_verifier,
        )
    elif payload.grant_type == "refresh_token":
        if not payload.refresh_token:
            raise AppError(
                "third_party_oauth.invalid_request", "刷新令牌交换缺少参数", status_code=400
            )
        access, refresh, expires_in, scopes = rotate_refresh_token(
            db,
            settings,
            client_id=payload.client_id,
            raw_refresh_token=payload.refresh_token,
        )
    else:
        raise AppError(
            "third_party_oauth.unsupported_grant_type", "不支持的授权类型", status_code=400
        )
    return OAuthTokenResponse(
        access_token=access,
        expires_in=expires_in,
        refresh_token=refresh,
        scope=" ".join(scopes),
    )


@router.post("/revoke", status_code=204)
def oauth_revoke(payload: OAuthRevokeRequest, db: Annotated[Session, Depends(get_db)]) -> None:
    revoke_token(db, client_id=payload.client_id, token=payload.token)


@router.get("/me", response_model=ThirdPartyPrincipalResponse)
def oauth_me(
    principal: Annotated[ThirdPartyPrincipal, Depends(require_third_party_scope("profile:read"))],
) -> ThirdPartyPrincipalResponse:
    return ThirdPartyPrincipalResponse(
        user_id=principal.user.id,
        client_id=principal.app.client_id,
        app_id=principal.app.id,
        scopes=list(principal.claims.scopes),
    )
