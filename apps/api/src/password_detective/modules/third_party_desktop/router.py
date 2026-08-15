from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.third_party_desktop.schemas import (
    ThirdPartyChallengeRequest,
    ThirdPartyChallengeResponse,
    ThirdPartyInstallationListResponse,
    ThirdPartyInstallationRegistrationRequest,
    ThirdPartyInstallationResponse,
    ThirdPartyReceiptRequest,
    ThirdPartyReceiptResponse,
)
from password_detective.modules.third_party_desktop.service import (
    create_challenge,
    list_installations,
    register_installation,
    revoke_installation,
    submit_receipt,
)
from password_detective.modules.third_party_oauth.dependencies import (
    ThirdPartyPrincipal,
    require_third_party_scope,
)

router = APIRouter(prefix="/third-party", tags=["第三方桌面验证"])
DbSession = Annotated[Session, Depends(get_db)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
InstallationPrincipal = Annotated[
    ThirdPartyPrincipal, Depends(require_third_party_scope("desktop:installations"))
]
VerificationPrincipal = Annotated[
    ThirdPartyPrincipal, Depends(require_third_party_scope("desktop:verification"))
]


@router.post(
    "/installations",
    response_model=ThirdPartyInstallationResponse,
    dependencies=[
        Depends(rate_limit("third_party.installation.register", limit=10, window_seconds=3600))
    ],
)
def register(
    payload: ThirdPartyInstallationRegistrationRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: SettingsDependency,
    principal: InstallationPrincipal,
) -> ThirdPartyInstallationResponse:
    response.headers["Cache-Control"] = "no-store"
    return register_installation(
        db,
        settings,
        payload=payload,
        principal=principal,
        context=get_client_context(request),
    )


@router.get("/installations", response_model=ThirdPartyInstallationListResponse)
def installations(
    db: DbSession, principal: InstallationPrincipal
) -> ThirdPartyInstallationListResponse:
    return list_installations(db, principal=principal)


@router.post(
    "/installations/{installation_id}/revoke",
    response_model=ThirdPartyInstallationResponse,
    dependencies=[
        Depends(rate_limit("third_party.installation.revoke", limit=20, window_seconds=3600))
    ],
)
def revoke(
    installation_id: str,
    request: Request,
    db: DbSession,
    principal: InstallationPrincipal,
) -> ThirdPartyInstallationResponse:
    return revoke_installation(
        db,
        installation_id=installation_id,
        principal=principal,
        context=get_client_context(request),
    )


@router.post(
    "/challenges",
    response_model=ThirdPartyChallengeResponse,
    dependencies=[Depends(rate_limit("third_party.challenge.create", limit=30, window_seconds=60))],
)
def challenge(
    payload: ThirdPartyChallengeRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: SettingsDependency,
    principal: VerificationPrincipal,
) -> ThirdPartyChallengeResponse:
    response.headers["Cache-Control"] = "no-store"
    return create_challenge(
        db,
        settings,
        payload=payload,
        principal=principal,
        context=get_client_context(request),
    )


@router.post(
    "/verification-receipts",
    response_model=ThirdPartyReceiptResponse,
    dependencies=[Depends(rate_limit("third_party.receipt.submit", limit=30, window_seconds=60))],
)
def receipt(
    payload: ThirdPartyReceiptRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: SettingsDependency,
    principal: VerificationPrincipal,
) -> ThirdPartyReceiptResponse:
    response.headers["Cache-Control"] = "no-store"
    return submit_receipt(
        db,
        settings,
        payload=payload,
        principal=principal,
        context=get_client_context(request),
    )
