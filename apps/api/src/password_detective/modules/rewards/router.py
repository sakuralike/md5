from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from password_detective.core.idempotency import (
    abandon_idempotency,
    acquire_idempotency,
    complete_idempotency,
    payload_digest,
    require_idempotency_key,
)
from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.db.models.reward_catalog import RewardCatalogStatus
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import (
    Principal,
    get_optional_principal,
    require_admin_mfa,
)
from password_detective.modules.rewards.schemas import (
    AdminRewardCatalogItemResponse,
    AdminRewardCatalogListResponse,
    RewardCatalogCreateRequest,
    RewardCatalogResponse,
    RewardCatalogUpdateRequest,
)
from password_detective.modules.rewards.service import (
    create_catalog_item,
    list_admin_catalog,
    list_public_catalog,
    update_catalog_item,
)

public_router = APIRouter(prefix="/rewards", tags=["积分商城"])
admin_router = APIRouter(prefix="/admin/rewards", tags=["积分商城治理"])


@public_router.get("/catalog", response_model=RewardCatalogResponse)
def public_reward_catalog(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
) -> RewardCatalogResponse:
    return list_public_catalog(db, principal=principal)


@admin_router.get("/catalog", response_model=AdminRewardCatalogListResponse)
def admin_reward_catalog_list(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_mfa)],
    item_status: Annotated[RewardCatalogStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminRewardCatalogListResponse:
    return list_admin_catalog(db, status=item_status, page=page, page_size=page_size)


@admin_router.post(
    "/catalog",
    response_model=AdminRewardCatalogItemResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("admin.rewards.catalog.create", limit=20, window_seconds=60))],
)
def admin_reward_catalog_create(
    payload: RewardCatalogCreateRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AdminRewardCatalogItemResponse:
    lease = acquire_idempotency(
        db,
        scope="admin.rewards.catalog.create",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest(payload.model_dump(mode="json")),
    )
    if lease.cached_response is not None:
        response.status_code = lease.cached_status or status.HTTP_201_CREATED
        return AdminRewardCatalogItemResponse.model_validate(lease.cached_response)
    try:
        result = create_catalog_item(
            db, payload=payload, principal=principal, context=get_client_context(request)
        )
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_201_CREATED,
            response_body=result.model_dump(mode="json"),
        )
        return result
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@admin_router.patch(
    "/catalog/{item_id}",
    response_model=AdminRewardCatalogItemResponse,
    dependencies=[Depends(rate_limit("admin.rewards.catalog.update", limit=30, window_seconds=60))],
)
def admin_reward_catalog_update(
    item_id: str,
    payload: RewardCatalogUpdateRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AdminRewardCatalogItemResponse:
    request_payload = {"item_id": item_id, **payload.model_dump(mode="json")}
    lease = acquire_idempotency(
        db,
        scope="admin.rewards.catalog.update",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest(request_payload),
    )
    if lease.cached_response is not None:
        response.status_code = lease.cached_status or status.HTTP_200_OK
        return AdminRewardCatalogItemResponse.model_validate(lease.cached_response)
    try:
        result = update_catalog_item(
            db,
            item_id=item_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_200_OK,
            response_body=result.model_dump(mode="json"),
        )
        return result
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise
