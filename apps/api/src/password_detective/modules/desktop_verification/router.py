from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import Principal, get_current_principal
from password_detective.modules.desktop_verification.schemas import (
    ChallengeRequest,
    ChallengeResponse,
    InstallationListResponse,
    InstallationRegistrationRequest,
    InstallationResponse,
    ReceiptRequest,
    ReceiptResponse,
)
from password_detective.modules.desktop_verification.service import (
    create_challenge,
    list_installations,
    register_installation,
    revoke_installation,
    submit_receipt,
)

router = APIRouter(prefix="/desktop", tags=["桌面可信验证"])


@router.post(
    "/installations",
    response_model=InstallationResponse,
    dependencies=[
        Depends(rate_limit("desktop.installation.register", limit=10, window_seconds=3600))
    ],
)
def register(
    payload: InstallationRegistrationRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> InstallationResponse:
    response.headers["Cache-Control"] = "no-store"
    return register_installation(
        db,
        settings,
        payload=payload,
        principal=principal,
        context=get_client_context(request),
    )


@router.get("/installations", response_model=InstallationListResponse)
def installations(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> InstallationListResponse:
    return list_installations(db, principal=principal)


@router.post(
    "/installations/{installation_id}/revoke",
    response_model=InstallationResponse,
    dependencies=[
        Depends(rate_limit("desktop.installation.revoke", limit=20, window_seconds=3600))
    ],
)
def revoke(
    installation_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> InstallationResponse:
    return revoke_installation(
        db,
        installation_id=installation_id,
        principal=principal,
        context=get_client_context(request),
    )


@router.post(
    "/challenges",
    response_model=ChallengeResponse,
    dependencies=[Depends(rate_limit("desktop.challenge.create", limit=30, window_seconds=60))],
)
def challenge(
    payload: ChallengeRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> ChallengeResponse:
    response.headers["Cache-Control"] = "no-store"
    return create_challenge(
        db,
        settings,
        payload=payload,
        principal=principal,
        context=get_client_context(request),
    )


@router.post(
    "/receipts",
    response_model=ReceiptResponse,
    dependencies=[Depends(rate_limit("desktop.receipt.submit", limit=30, window_seconds=60))],
)
def receipt(
    payload: ReceiptRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> ReceiptResponse:
    response.headers["Cache-Control"] = "no-store"
    return submit_receipt(
        db,
        settings,
        payload=payload,
        principal=principal,
        context=get_client_context(request),
    )
