from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from password_detective.db.dependencies import get_db
from password_detective.modules.auth.dependencies import Principal, get_current_principal
from password_detective.modules.third_party_apps.application_requests import (
    create_application_request,
    get_owned_application_request,
    list_owned_application_requests,
    submit_application_request,
    update_application_request,
)
from password_detective.modules.third_party_apps.schemas import (
    ThirdPartyApplicationCreateRequest,
    ThirdPartyApplicationDetail,
    ThirdPartyApplicationListResponse,
    ThirdPartyApplicationUpdateRequest,
)

router = APIRouter(prefix="/me/third-party-applications", tags=["开发者应用申请"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


@router.post("", response_model=ThirdPartyApplicationDetail, status_code=status.HTTP_201_CREATED)
def create_my_application(
    payload: ThirdPartyApplicationCreateRequest, db: DbSession, principal: CurrentPrincipal
) -> ThirdPartyApplicationDetail:
    return create_application_request(db, user_id=principal.user.id, payload=payload)


@router.get("", response_model=ThirdPartyApplicationListResponse)
def list_my_applications(
    db: DbSession,
    principal: CurrentPrincipal,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ThirdPartyApplicationListResponse:
    return list_owned_application_requests(
        db, user_id=principal.user.id, page=page, page_size=page_size
    )


@router.get("/{request_id}", response_model=ThirdPartyApplicationDetail)
def get_my_application(
    request_id: str, db: DbSession, principal: CurrentPrincipal
) -> ThirdPartyApplicationDetail:
    return get_owned_application_request(db, user_id=principal.user.id, request_id=request_id)


@router.patch("/{request_id}", response_model=ThirdPartyApplicationDetail)
def update_my_application(
    request_id: str,
    payload: ThirdPartyApplicationUpdateRequest,
    db: DbSession,
    principal: CurrentPrincipal,
) -> ThirdPartyApplicationDetail:
    return update_application_request(
        db, user_id=principal.user.id, request_id=request_id, payload=payload
    )


@router.post("/{request_id}/submit", response_model=ThirdPartyApplicationDetail)
def submit_my_application(
    request_id: str, db: DbSession, principal: CurrentPrincipal
) -> ThirdPartyApplicationDetail:
    return submit_application_request(db, user_id=principal.user.id, request_id=request_id)
