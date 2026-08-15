from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from password_detective.db.dependencies import get_db
from password_detective.db.models.third_party_app import ThirdPartyApplicationRequestStatus
from password_detective.modules.auth.dependencies import Principal, require_admin_mfa
from password_detective.modules.third_party_apps.application_requests import (
    approve_application_request,
    get_application_request_for_admin,
    list_application_requests_for_admin,
    reject_application_request,
)
from password_detective.modules.third_party_apps.schemas import (
    ThirdPartyApplicationApprovalResponse,
    ThirdPartyApplicationDetail,
    ThirdPartyApplicationListResponse,
    ThirdPartyApplicationRejectRequest,
    ThirdPartyApplicationReviewRequest,
)

router = APIRouter(prefix="/admin/third-party-applications", tags=["开发者应用审核"])
DbSession = Annotated[Session, Depends(get_db)]
AdminPrincipal = Annotated[Principal, Depends(require_admin_mfa)]


@router.get("/requests", response_model=ThirdPartyApplicationListResponse)
def list_application_requests(
    db: DbSession,
    _: AdminPrincipal,
    review_status: Annotated[
        ThirdPartyApplicationRequestStatus | None, Query(alias="status")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ThirdPartyApplicationListResponse:
    return list_application_requests_for_admin(
        db, page=page, page_size=page_size, status=review_status
    )


@router.get("/requests/{request_id}", response_model=ThirdPartyApplicationDetail)
def get_application_request(
    request_id: str, db: DbSession, _: AdminPrincipal
) -> ThirdPartyApplicationDetail:
    return get_application_request_for_admin(db, request_id=request_id)


@router.post("/requests/{request_id}/reject", response_model=ThirdPartyApplicationDetail)
def reject_application_request_route(
    request_id: str,
    payload: ThirdPartyApplicationRejectRequest,
    db: DbSession,
    principal: AdminPrincipal,
) -> ThirdPartyApplicationDetail:
    return reject_application_request(
        db, actor_id=principal.user.id, request_id=request_id, payload=payload
    )


@router.post("/requests/{request_id}/approve", response_model=ThirdPartyApplicationApprovalResponse)
def approve_application_request_route(
    request_id: str,
    payload: ThirdPartyApplicationReviewRequest,
    db: DbSession,
    principal: AdminPrincipal,
) -> ThirdPartyApplicationApprovalResponse:
    return approve_application_request(
        db, actor_id=principal.user.id, request_id=request_id, payload=payload
    )
