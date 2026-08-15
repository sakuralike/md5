from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from password_detective.db.dependencies import get_db
from password_detective.modules.auth.dependencies import Principal, require_admin_mfa
from password_detective.modules.third_party_apps.schemas import (
    ThirdPartyAppCreateRequest,
    ThirdPartyAppListItem,
    ThirdPartyAppListResponse,
    ThirdPartyAppReviewRequest,
)
from password_detective.modules.third_party_apps.service import (
    approve_app,
    create_app,
    get_app,
    list_apps,
    restore_app,
    revoke_app,
    rotate_secret,
    suspend_app,
)

router = APIRouter(prefix="/admin/third-party-apps", tags=["第三方应用管理"])
AdminPrincipal = Annotated[Principal, Depends(require_admin_mfa)]
DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ThirdPartyAppListItem, status_code=status.HTTP_201_CREATED)
def admin_create_third_party_app(
    payload: ThirdPartyAppCreateRequest,
    db: DbSession,
    principal: AdminPrincipal,
) -> ThirdPartyAppListItem:
    return create_app(db, actor_id=principal.user.id, payload=payload)


@router.get("", response_model=ThirdPartyAppListResponse)
def admin_list_third_party_apps(
    db: DbSession,
    _: AdminPrincipal,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ThirdPartyAppListResponse:
    items, total = list_apps(db, page=page, page_size=page_size)
    return ThirdPartyAppListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/{app_id}", response_model=ThirdPartyAppListItem)
def admin_get_third_party_app(
    app_id: str,
    db: DbSession,
    _: AdminPrincipal,
) -> ThirdPartyAppListItem:
    return get_app(db, app_id)


@router.post("/{app_id}/approve", response_model=ThirdPartyAppListItem)
def admin_approve_third_party_app(
    app_id: str,
    db: DbSession,
    principal: AdminPrincipal,
    payload: ThirdPartyAppReviewRequest | None = None,
) -> ThirdPartyAppListItem:
    return approve_app(
        db,
        actor_id=principal.user.id,
        app_id=app_id,
        payload=payload or ThirdPartyAppReviewRequest(),
    )


@router.post("/{app_id}/suspend", response_model=ThirdPartyAppListItem)
def admin_suspend_third_party_app(
    app_id: str,
    db: DbSession,
    principal: AdminPrincipal,
) -> ThirdPartyAppListItem:
    return suspend_app(db, actor_id=principal.user.id, app_id=app_id)


@router.post("/{app_id}/restore", response_model=ThirdPartyAppListItem)
def admin_restore_third_party_app(
    app_id: str,
    db: DbSession,
    principal: AdminPrincipal,
) -> ThirdPartyAppListItem:
    return restore_app(db, actor_id=principal.user.id, app_id=app_id)


@router.post("/{app_id}/revoke", response_model=ThirdPartyAppListItem)
def admin_revoke_third_party_app(
    app_id: str,
    db: DbSession,
    principal: AdminPrincipal,
) -> ThirdPartyAppListItem:
    return revoke_app(db, actor_id=principal.user.id, app_id=app_id)


@router.post("/{app_id}/rotate-secret", response_model=ThirdPartyAppListItem)
def admin_rotate_third_party_app_secret(
    app_id: str,
    db: DbSession,
    principal: AdminPrincipal,
) -> ThirdPartyAppListItem:
    return rotate_secret(db, actor_id=principal.user.id, app_id=app_id)
