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
from password_detective.db.models.reward_order import RewardOrderStatus
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    get_optional_principal,
    require_admin_mfa,
)
from password_detective.modules.rewards.schemas import (
    AdminRewardCatalogItemResponse,
    AdminRewardCatalogListResponse,
    RewardAdminOrderActionRequest,
    RewardAdminOrderListResponse,
    RewardAdminOrderResponse,
    RewardCatalogCreateRequest,
    RewardCatalogResponse,
    RewardCatalogUpdateRequest,
    RewardInventoryAdjustmentRequest,
    RewardInventoryEventListResponse,
    RewardOperationsStatsResponse,
    RewardOrderCreateRequest,
    RewardOrderCreateResponse,
    RewardOrderDetailResponse,
    RewardOrderListResponse,
)
from password_detective.modules.rewards.service import (
    adjust_catalog_inventory,
    cancel_user_order,
    compensate_admin_order,
    create_catalog_item,
    create_reward_order,
    get_admin_order,
    get_operations_stats,
    get_user_order,
    list_admin_catalog,
    list_admin_orders,
    list_inventory_events,
    list_public_catalog,
    list_user_orders,
    retry_admin_order,
    update_catalog_item,
)

public_router = APIRouter(prefix="/rewards", tags=["积分商城"])
admin_router = APIRouter(prefix="/admin/rewards", tags=["积分商城治理"])


@public_router.get("/catalog", response_model=RewardCatalogResponse)
def public_reward_catalog(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    category: Annotated[str | None, Query(max_length=64)] = None,
    tag: Annotated[str | None, Query(max_length=24)] = None,
    sort: Annotated[str, Query(pattern="^(featured|points_asc|newest)$")] = "featured",
) -> RewardCatalogResponse:
    return list_public_catalog(db, principal=principal, category=category, tag=tag, sort=sort)


@public_router.post(
    "/orders",
    response_model=RewardOrderCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("rewards.orders.create", limit=10, window_seconds=60))],
)
def create_order(
    payload: RewardOrderCreateRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> RewardOrderCreateResponse:
    lease = acquire_idempotency(
        db,
        scope="rewards.orders.create",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest(payload.model_dump(mode="json")),
    )
    if lease.cached_response is not None:
        response.status_code = lease.cached_status or status.HTTP_201_CREATED
        return RewardOrderCreateResponse.model_validate(lease.cached_response)
    try:
        result = create_reward_order(db, payload=payload, principal=principal)
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


@public_router.get("/orders", response_model=RewardOrderListResponse)
def user_order_list(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    item_status: Annotated[RewardOrderStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> RewardOrderListResponse:
    return list_user_orders(
        db, principal=principal, status=item_status, page=page, page_size=page_size
    )


@public_router.get("/orders/{order_id}", response_model=RewardOrderDetailResponse)
def user_order_detail(
    order_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> RewardOrderDetailResponse:
    return get_user_order(db, order_id=order_id, principal=principal)


@public_router.post(
    "/orders/{order_id}/cancel",
    response_model=RewardOrderDetailResponse,
    dependencies=[Depends(rate_limit("rewards.orders.cancel", limit=10, window_seconds=60))],
)
def user_order_cancel(
    order_id: str,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> RewardOrderDetailResponse:
    lease = acquire_idempotency(
        db,
        scope="rewards.orders.cancel",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest({"order_id": order_id}),
    )
    if lease.cached_response is not None:
        return RewardOrderDetailResponse.model_validate(lease.cached_response)
    try:
        result = cancel_user_order(db, order_id=order_id, principal=principal)
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
    lease = acquire_idempotency(
        db,
        scope="admin.rewards.catalog.update",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest({"item_id": item_id, **payload.model_dump(mode="json")}),
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


@admin_router.post(
    "/catalog/{item_id}/inventory-adjustments",
    response_model=AdminRewardCatalogItemResponse,
    dependencies=[
        Depends(rate_limit("admin.rewards.inventory.adjust", limit=30, window_seconds=60))
    ],
)
def admin_inventory_adjustment(
    item_id: str,
    payload: RewardInventoryAdjustmentRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AdminRewardCatalogItemResponse:
    lease = acquire_idempotency(
        db,
        scope="admin.rewards.inventory.adjust",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest({"item_id": item_id, **payload.model_dump(mode="json")}),
    )
    if lease.cached_response is not None:
        return AdminRewardCatalogItemResponse.model_validate(lease.cached_response)
    try:
        result = adjust_catalog_inventory(
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


@admin_router.get(
    "/catalog/{item_id}/inventory-events", response_model=RewardInventoryEventListResponse
)
def admin_inventory_events(
    item_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_mfa)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> RewardInventoryEventListResponse:
    return list_inventory_events(db, item_id=item_id, page=page, page_size=page_size)


@admin_router.get("/orders", response_model=RewardAdminOrderListResponse)
def admin_order_list(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_mfa)],
    item_status: Annotated[RewardOrderStatus | None, Query(alias="status")] = None,
    catalog_item_id: Annotated[str | None, Query(max_length=36)] = None,
    order_no: Annotated[str | None, Query(max_length=32)] = None,
    user_id: Annotated[str | None, Query(max_length=36)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RewardAdminOrderListResponse:
    return list_admin_orders(
        db,
        status=item_status,
        catalog_item_id=catalog_item_id,
        order_no=order_no,
        user_id=user_id,
        page=page,
        page_size=page_size,
    )


@admin_router.get("/orders/{order_id}", response_model=RewardAdminOrderResponse)
def admin_order_detail(
    order_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_mfa)],
) -> RewardAdminOrderResponse:
    return get_admin_order(db, order_id=order_id)


def _admin_order_action(
    *,
    action: str,
    order_id: str,
    payload: RewardAdminOrderActionRequest,
    request: Request,
    response: Response,
    db: Session,
    principal: Principal,
    idempotency_key: str,
) -> RewardAdminOrderResponse:
    lease = acquire_idempotency(
        db,
        scope=f"admin.rewards.order.{action}",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest({"order_id": order_id, **payload.model_dump(mode="json")}),
    )
    if lease.cached_response is not None:
        response.status_code = lease.cached_status or status.HTTP_200_OK
        return RewardAdminOrderResponse.model_validate(lease.cached_response)
    try:
        context = get_client_context(request)
        result = (
            retry_admin_order(
                db,
                order_id=order_id,
                payload=payload,
                principal=principal,
                context=context,
            )
            if action == "retry"
            else compensate_admin_order(
                db,
                order_id=order_id,
                payload=payload,
                principal=principal,
                context=context,
            )
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


@admin_router.post(
    "/orders/{order_id}/retry",
    response_model=RewardAdminOrderResponse,
    dependencies=[Depends(rate_limit("admin.rewards.order.retry", limit=30, window_seconds=60))],
)
def admin_order_retry(
    order_id: str,
    payload: RewardAdminOrderActionRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> RewardAdminOrderResponse:
    return _admin_order_action(
        action="retry",
        order_id=order_id,
        payload=payload,
        request=request,
        response=response,
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
    )


@admin_router.post(
    "/orders/{order_id}/compensate",
    response_model=RewardAdminOrderResponse,
    dependencies=[
        Depends(rate_limit("admin.rewards.order.compensate", limit=30, window_seconds=60))
    ],
)
def admin_order_compensate(
    order_id: str,
    payload: RewardAdminOrderActionRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> RewardAdminOrderResponse:
    return _admin_order_action(
        action="compensate",
        order_id=order_id,
        payload=payload,
        request=request,
        response=response,
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
    )


@admin_router.get("/operations/stats", response_model=RewardOperationsStatsResponse)
def admin_operations_stats(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_mfa)],
) -> RewardOperationsStatsResponse:
    return get_operations_stats(db)
