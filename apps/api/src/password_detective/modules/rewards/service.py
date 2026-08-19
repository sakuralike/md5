from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.reward_catalog import (
    RewardCatalogItem,
    RewardCatalogKind,
    RewardCatalogStatus,
)
from password_detective.db.models.reward_order import (
    RewardActorType,
    RewardDeliveryKind,
    RewardEntitlementGrant,
    RewardEntitlementStatus,
    RewardFulfillment,
    RewardFulfillmentStatus,
    RewardInventoryEvent,
    RewardInventoryEventType,
    RewardOrder,
    RewardOrderEvent,
    RewardOrderItem,
    RewardOrderStatus,
)
from password_detective.db.models.user import User
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.rewards.schemas import (
    AdminRewardCatalogItemResponse,
    AdminRewardCatalogListResponse,
    RewardAdminFulfillmentResponse,
    RewardAdminOrderActionRequest,
    RewardAdminOrderListResponse,
    RewardAdminOrderResponse,
    RewardCatalogCreateRequest,
    RewardCatalogItemResponse,
    RewardCatalogResponse,
    RewardCatalogUpdateRequest,
    RewardEntitlementGrantResponse,
    RewardFulfillmentSummary,
    RewardInventoryAdjustmentRequest,
    RewardInventoryEventListResponse,
    RewardInventoryEventResponse,
    RewardOperationsStatsResponse,
    RewardOrderCreateRequest,
    RewardOrderCreateResponse,
    RewardOrderDetailResponse,
    RewardOrderListResponse,
    RewardOrderSummaryResponse,
    RewardOrderTimelineEvent,
)

_ENTITLEMENT_KEYS = {
    "community_supporter",
    "priority_case_review",
    "daily_reveal_boost",
}
_MAX_FULFILLMENT_RETRIES = 3
_FULFILLMENT_LEASE_SECONDS = 300


def _stock_status(stock: int) -> str:
    if stock <= 0:
        return "out_of_stock"
    return "limited" if stock < 10 else "available"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _redeem_status(item: RewardCatalogItem, *, now: datetime | None = None) -> str:
    current = now or utc_now()
    if item.stock <= 0:
        return "out_of_stock"
    if item.redeem_start_at and _aware(item.redeem_start_at) > current:
        return "scheduled"
    if item.redeem_end_at and _aware(item.redeem_end_at) <= current:
        return "ended"
    return "available"


def _available_points(db: Session, user_id: str) -> int:
    return int(
        db.scalar(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (PointsLedger.status == PointsLedgerStatus.POSTED, PointsLedger.amount),
                            else_=0,
                        )
                    ),
                    0,
                )
            ).where(PointsLedger.user_id == user_id)
        )
        or 0
    )


def _public_item(item: RewardCatalogItem) -> RewardCatalogItemResponse:
    return RewardCatalogItemResponse(
        id=item.id,
        slug=item.slug,
        name=item.name,
        description=item.description,
        kind=item.kind,
        cost_points=item.cost_points,
        per_user_limit=item.per_user_limit,
        category=item.category,
        tags=list(item.tags or []),
        entitlement_key=item.entitlement_key,
        entitlement_duration_days=item.entitlement_duration_days,
        redeem_start_at=item.redeem_start_at,
        redeem_end_at=item.redeem_end_at,
        stock_status=_stock_status(item.stock),
        redeem_status=_redeem_status(item),
    )


def _admin_item(item: RewardCatalogItem) -> AdminRewardCatalogItemResponse:
    return AdminRewardCatalogItemResponse(
        **_public_item(item).model_dump(),
        stock=item.stock,
        sort_weight=item.sort_weight,
        status=item.status,
        version=item.version,
        created_by=item.created_by,
        updated_by=item.updated_by,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def list_public_catalog(
    db: Session,
    *,
    principal: Principal | None,
    category: str | None = None,
    tag: str | None = None,
    sort: str = "featured",
) -> RewardCatalogResponse:
    conditions = [
        RewardCatalogItem.kind == RewardCatalogKind.VIRTUAL,
        RewardCatalogItem.status == RewardCatalogStatus.ACTIVE,
    ]
    if category:
        conditions.append(RewardCatalogItem.category == category.strip().lower())
    order_by = {
        "featured": (RewardCatalogItem.sort_weight.desc(), RewardCatalogItem.updated_at.desc()),
        "points_asc": (RewardCatalogItem.cost_points.asc(), RewardCatalogItem.id.asc()),
        "newest": (RewardCatalogItem.created_at.desc(), RewardCatalogItem.id.desc()),
    }[sort]
    items = list(db.scalars(select(RewardCatalogItem).where(*conditions).order_by(*order_by)).all())
    if tag:
        normalized_tag = tag.strip().lower()
        items = [item for item in items if normalized_tag in (item.tags or [])]
    return RewardCatalogResponse(
        items=[_public_item(item) for item in items],
        available_points=(
            _available_points(db, principal.user.id) if principal is not None else None
        ),
        categories=sorted({item.category for item in items}),
        tags=sorted({entry for item in items for entry in (item.tags or [])}),
    )


def list_admin_catalog(
    db: Session,
    *,
    status: RewardCatalogStatus | None,
    page: int,
    page_size: int,
) -> AdminRewardCatalogListResponse:
    conditions = []
    if status is not None:
        conditions.append(RewardCatalogItem.status == status)
    total = int(db.scalar(select(func.count(RewardCatalogItem.id)).where(*conditions)) or 0)
    items = db.scalars(
        select(RewardCatalogItem)
        .where(*conditions)
        .order_by(
            RewardCatalogItem.sort_weight.desc(),
            RewardCatalogItem.updated_at.desc(),
            RewardCatalogItem.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AdminRewardCatalogListResponse(
        items=[_admin_item(item) for item in items], page=page, page_size=page_size, total=total
    )


def create_catalog_item(
    db: Session,
    *,
    payload: RewardCatalogCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> AdminRewardCatalogItemResponse:
    if db.scalar(select(RewardCatalogItem.id).where(RewardCatalogItem.slug == payload.slug)):
        raise AppError("reward.catalog_slug_taken", "商品代码已存在", status_code=409)
    now = utc_now()
    item = RewardCatalogItem(
        id=new_id(),
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
        kind=RewardCatalogKind.VIRTUAL,
        cost_points=payload.cost_points,
        stock=payload.stock,
        per_user_limit=payload.per_user_limit,
        category=payload.category,
        tags=payload.tags,
        sort_weight=payload.sort_weight,
        entitlement_key=payload.entitlement_key,
        entitlement_duration_days=payload.entitlement_duration_days,
        redeem_start_at=payload.redeem_start_at,
        redeem_end_at=payload.redeem_end_at,
        status=payload.status,
        version=1,
        created_by=principal.user.id,
        updated_by=principal.user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    if item.stock:
        db.add(
            RewardInventoryEvent(
                catalog_item_id=item.id,
                event_type=RewardInventoryEventType.ADMIN_ADJUSTED,
                delta=item.stock,
                stock_before=0,
                stock_after=item.stock,
                actor_type=RewardActorType.ADMIN,
                actor_id=principal.user.id,
                reason_code="initial_stock",
                reference_key=f"catalog:{item.id}:initial",
            )
        )
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.rewards.catalog.created",
        target_type="reward_catalog_item",
        target_id=item.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "reason_code": payload.reason_code,
            "slug": payload.slug,
            "kind": "virtual",
            "category": payload.category,
            "entitlement_key": payload.entitlement_key,
        },
    )
    db.commit()
    db.refresh(item)
    return _admin_item(item)


def update_catalog_item(
    db: Session,
    *,
    item_id: str,
    payload: RewardCatalogUpdateRequest,
    principal: Principal,
    context: ClientContext,
) -> AdminRewardCatalogItemResponse:
    item = db.scalar(
        select(RewardCatalogItem).where(RewardCatalogItem.id == item_id).with_for_update()
    )
    if item is None:
        raise AppError("reward.catalog_not_found", "商品不存在", status_code=404)
    if item.version != payload.expected_version:
        raise AppError(
            "reward.catalog_version_conflict",
            "商品已被其他管理员更新，请刷新后重试",
            status_code=409,
            details={"current_version": item.version},
        )
    item.name = payload.name
    item.description = payload.description
    item.kind = RewardCatalogKind.VIRTUAL
    item.cost_points = payload.cost_points
    item.per_user_limit = payload.per_user_limit
    item.category = payload.category
    item.tags = payload.tags
    item.sort_weight = payload.sort_weight
    item.entitlement_key = payload.entitlement_key
    item.entitlement_duration_days = payload.entitlement_duration_days
    item.redeem_start_at = payload.redeem_start_at
    item.redeem_end_at = payload.redeem_end_at
    item.status = payload.status
    item.version += 1
    item.updated_by = principal.user.id
    item.updated_at = utc_now()
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.rewards.catalog.updated",
        target_type="reward_catalog_item",
        target_id=item.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"reason_code": payload.reason_code, "version": item.version},
    )
    db.commit()
    db.refresh(item)
    return _admin_item(item)


def _latest_fulfillment(db: Session, order_id: str) -> RewardFulfillment | None:
    return db.scalar(
        select(RewardFulfillment)
        .where(RewardFulfillment.order_id == order_id)
        .order_by(RewardFulfillment.attempt_no.desc())
        .limit(1)
    )


def _fulfillment_summary(
    fulfillment: RewardFulfillment | None,
) -> RewardFulfillmentSummary | None:
    if fulfillment is None:
        return None
    return RewardFulfillmentSummary(
        status=fulfillment.status,
        attempt_no=fulfillment.attempt_no,
        result_code=fulfillment.result_code,
        safe_message=fulfillment.safe_message,
        completed_at=fulfillment.completed_at,
    )


def _order_summary(db: Session, order: RewardOrder) -> RewardOrderSummaryResponse:
    return RewardOrderSummaryResponse(
        id=order.id,
        order_no=order.order_no,
        status=order.status,
        catalog_item_id=order.catalog_item_id,
        item_slug=order.item_slug_snapshot,
        item_name=order.item_name_snapshot,
        quantity=order.quantity,
        unit_cost_points=order.unit_cost_points,
        total_cost_points=order.total_cost_points,
        created_at=order.created_at,
        updated_at=order.updated_at,
        fulfilled_at=order.fulfilled_at,
        cancelled_at=order.cancelled_at,
        compensated_at=order.compensated_at,
        fulfillment=_fulfillment_summary(_latest_fulfillment(db, order.id)),
    )


def _timeline(db: Session, order_id: str) -> list[RewardOrderTimelineEvent]:
    events = db.scalars(
        select(RewardOrderEvent)
        .where(RewardOrderEvent.order_id == order_id)
        .order_by(RewardOrderEvent.created_at, RewardOrderEvent.id)
    ).all()
    return [
        RewardOrderTimelineEvent(
            id=event.id,
            from_status=event.from_status,
            to_status=event.to_status,
            event_type=event.event_type,
            reason_code=event.reason_code,
            created_at=event.created_at,
        )
        for event in events
    ]


def _entitlement(db: Session, order_id: str) -> RewardEntitlementGrantResponse | None:
    grant = db.scalar(
        select(RewardEntitlementGrant).where(RewardEntitlementGrant.order_id == order_id)
    )
    if grant is None:
        return None
    return RewardEntitlementGrantResponse(
        entitlement_key=grant.entitlement_key,
        status=grant.status.value,
        starts_at=grant.starts_at,
        expires_at=grant.expires_at,
    )


def _order_detail(db: Session, order: RewardOrder) -> RewardOrderDetailResponse:
    return RewardOrderDetailResponse(
        **_order_summary(db, order).model_dump(),
        available_points=_available_points(db, order.user_id),
        timeline=_timeline(db, order.id),
        entitlement=_entitlement(db, order.id),
    )


def create_reward_order(
    db: Session,
    *,
    payload: RewardOrderCreateRequest,
    principal: Principal,
) -> RewardOrderCreateResponse:
    user = db.scalar(select(User).where(User.id == principal.user.id).with_for_update())
    if user is None:
        raise AppError("auth.account_unavailable", "账号当前不可用", status_code=403)
    item = db.scalar(
        select(RewardCatalogItem)
        .where(RewardCatalogItem.id == payload.catalog_item_id)
        .with_for_update()
    )
    if item is None:
        raise AppError("reward.catalog_not_found", "商品不存在", status_code=404)
    if item.status != RewardCatalogStatus.ACTIVE or item.kind != RewardCatalogKind.VIRTUAL:
        raise AppError("reward.catalog_unavailable", "商品当前不可兑换", status_code=409)
    redeem_status = _redeem_status(item)
    if redeem_status == "scheduled":
        raise AppError("reward.redeem_not_started", "商品兑换尚未开始", status_code=409)
    if redeem_status == "ended":
        raise AppError("reward.redeem_ended", "商品兑换已经结束", status_code=409)
    if item.stock < payload.quantity:
        raise AppError("reward.insufficient_stock", "商品库存不足", status_code=409)

    counted_statuses = (
        RewardOrderStatus.PENDING_FULFILLMENT,
        RewardOrderStatus.PROCESSING,
        RewardOrderStatus.FULFILLED,
    )
    redeemed_quantity = int(
        db.scalar(
            select(func.coalesce(func.sum(RewardOrder.quantity), 0)).where(
                RewardOrder.user_id == user.id,
                RewardOrder.catalog_item_id == item.id,
                or_(
                    RewardOrder.status.in_(counted_statuses),
                    (
                        (RewardOrder.status == RewardOrderStatus.FAILED)
                        & RewardOrder.compensated_at.is_(None)
                    ),
                ),
            )
        )
        or 0
    )
    if redeemed_quantity + payload.quantity > item.per_user_limit:
        raise AppError(
            "reward.per_user_limit_exceeded",
            "本商品已超过每位用户的兑换上限",
            status_code=409,
            details={"per_user_limit": item.per_user_limit},
        )
    total_cost = item.cost_points * payload.quantity
    balance = _available_points(db, user.id)
    if balance < total_cost:
        raise AppError(
            "reward.insufficient_points",
            "可用积分不足",
            status_code=409,
            details={"available_points": balance, "required_points": total_cost},
        )

    now = utc_now()
    order_id = new_id()
    ledger_id = new_id()
    order = RewardOrder(
        id=order_id,
        order_no=f"R{now:%Y%m%d}{order_id.replace('-', '')[:12].upper()}",
        user_id=user.id,
        status=RewardOrderStatus.PENDING_FULFILLMENT,
        quantity=payload.quantity,
        unit_cost_points=item.cost_points,
        total_cost_points=total_cost,
        catalog_item_id=item.id,
        catalog_version=item.version,
        item_slug_snapshot=item.slug,
        item_name_snapshot=item.name,
        entitlement_key_snapshot=item.entitlement_key,
        entitlement_duration_days_snapshot=item.entitlement_duration_days,
        points_ledger_entry_id=ledger_id,
        version=1,
        created_at=now,
        updated_at=now,
    )
    stock_before = item.stock
    item.stock -= payload.quantity
    db.add_all(
        [
            PointsLedger(
                id=ledger_id,
                user_id=user.id,
                amount=-total_cost,
                event_type="reward.redeemed",
                reference_id=order_id,
                status=PointsLedgerStatus.POSTED,
                created_at=now,
                settled_at=now,
            ),
            order,
            RewardOrderItem(
                order_id=order_id,
                catalog_item_id=item.id,
                item_slug_snapshot=item.slug,
                item_name_snapshot=item.name,
                kind_snapshot=item.kind,
                quantity=payload.quantity,
                unit_cost_points=item.cost_points,
                total_cost_points=total_cost,
                catalog_version=item.version,
            ),
            RewardInventoryEvent(
                catalog_item_id=item.id,
                order_id=order_id,
                event_type=RewardInventoryEventType.REDEEMED,
                delta=-payload.quantity,
                stock_before=stock_before,
                stock_after=item.stock,
                actor_type=RewardActorType.USER,
                actor_id=user.id,
                reason_code="order_redeemed",
                reference_key=order_id,
                created_at=now,
            ),
            RewardOrderEvent(
                order_id=order_id,
                from_status=None,
                to_status=RewardOrderStatus.PENDING_FULFILLMENT,
                event_type="order.created",
                actor_type=RewardActorType.USER,
                actor_id=user.id,
                reason_code="reward_redeemed",
                created_at=now,
            ),
            RewardFulfillment(
                order_id=order_id,
                attempt_no=1,
                delivery_kind=RewardDeliveryKind.INTERNAL_ENTITLEMENT,
                status=RewardFulfillmentStatus.PENDING,
                retry_count=0,
                next_retry_at=now,
                created_at=now,
            ),
        ]
    )
    db.commit()
    db.refresh(order)
    return RewardOrderCreateResponse(**_order_detail(db, order).model_dump())


def list_user_orders(
    db: Session,
    *,
    principal: Principal,
    status: RewardOrderStatus | None,
    page: int,
    page_size: int,
) -> RewardOrderListResponse:
    conditions = [RewardOrder.user_id == principal.user.id]
    if status is not None:
        conditions.append(RewardOrder.status == status)
    total = int(db.scalar(select(func.count(RewardOrder.id)).where(*conditions)) or 0)
    orders = db.scalars(
        select(RewardOrder)
        .where(*conditions)
        .order_by(RewardOrder.created_at.desc(), RewardOrder.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return RewardOrderListResponse(
        items=[_order_summary(db, order) for order in orders],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_user_order(
    db: Session, *, order_id: str, principal: Principal
) -> RewardOrderDetailResponse:
    order = db.scalar(
        select(RewardOrder).where(
            RewardOrder.id == order_id, RewardOrder.user_id == principal.user.id
        )
    )
    if order is None:
        raise AppError("reward.order_not_found", "兑换订单不存在", status_code=404)
    return _order_detail(db, order)


def _append_order_event(
    db: Session,
    *,
    order: RewardOrder,
    from_status: RewardOrderStatus,
    event_type: str,
    actor_type: RewardActorType,
    actor_id: str | None,
    reason_code: str,
    now: datetime,
) -> None:
    db.add(
        RewardOrderEvent(
            order_id=order.id,
            from_status=from_status,
            to_status=order.status,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            reason_code=reason_code,
            created_at=now,
        )
    )


def _compensate_order(
    db: Session,
    *,
    order: RewardOrder,
    item: RewardCatalogItem,
    actor_type: RewardActorType,
    actor_id: str | None,
    event_type: str,
    reason_code: str,
    now: datetime,
) -> None:
    if order.compensation_ledger_entry_id is not None:
        raise AppError("reward.order_already_compensated", "订单已经完成积分补偿", status_code=409)
    ledger_id = new_id()
    db.add(
        PointsLedger(
            id=ledger_id,
            user_id=order.user_id,
            amount=order.total_cost_points,
            event_type=event_type,
            reference_id=order.id,
            status=PointsLedgerStatus.POSTED,
            created_at=now,
            settled_at=now,
        )
    )
    stock_before = item.stock
    item.stock += order.quantity
    db.add(
        RewardInventoryEvent(
            catalog_item_id=item.id,
            order_id=order.id,
            event_type=RewardInventoryEventType.RELEASED,
            delta=order.quantity,
            stock_before=stock_before,
            stock_after=item.stock,
            actor_type=actor_type,
            actor_id=actor_id,
            reason_code=reason_code,
            reference_key=order.id,
            created_at=now,
        )
    )
    order.compensation_ledger_entry_id = ledger_id
    order.compensated_at = now


def cancel_user_order(
    db: Session, *, order_id: str, principal: Principal
) -> RewardOrderDetailResponse:
    db.scalar(select(User).where(User.id == principal.user.id).with_for_update())
    order = db.scalar(
        select(RewardOrder)
        .where(RewardOrder.id == order_id, RewardOrder.user_id == principal.user.id)
        .with_for_update()
    )
    if order is None:
        raise AppError("reward.order_not_found", "兑换订单不存在", status_code=404)
    if order.status != RewardOrderStatus.PENDING_FULFILLMENT:
        raise AppError("reward.order_not_cancellable", "当前订单状态不能取消", status_code=409)
    fulfillment = _latest_fulfillment(db, order.id)
    if fulfillment is None or fulfillment.status not in {
        RewardFulfillmentStatus.PENDING,
        RewardFulfillmentStatus.RETRYABLE,
    }:
        raise AppError("reward.order_not_cancellable", "订单履约已开始，不能取消", status_code=409)
    item = db.scalar(
        select(RewardCatalogItem)
        .where(RewardCatalogItem.id == order.catalog_item_id)
        .with_for_update()
    )
    if item is None:
        raise AppError("reward.catalog_not_found", "商品不存在", status_code=409)
    now = utc_now()
    previous = order.status
    order.status = RewardOrderStatus.CANCELLED
    order.cancelled_at = now
    order.updated_at = now
    order.version += 1
    fulfillment.status = RewardFulfillmentStatus.CANCELLED
    fulfillment.result_code = "order_cancelled"
    fulfillment.safe_message = "订单已取消，积分和库存已返还。"
    fulfillment.completed_at = now
    _compensate_order(
        db,
        order=order,
        item=item,
        actor_type=RewardActorType.USER,
        actor_id=principal.user.id,
        event_type="reward.cancelled_compensation",
        reason_code="user_cancelled",
        now=now,
    )
    _append_order_event(
        db,
        order=order,
        from_status=previous,
        event_type="order.cancelled",
        actor_type=RewardActorType.USER,
        actor_id=principal.user.id,
        reason_code="user_cancelled",
        now=now,
    )
    db.commit()
    db.refresh(order)
    return _order_detail(db, order)


def _grant_entitlement(db: Session, order: RewardOrder, *, now: datetime) -> None:
    if order.entitlement_key_snapshot not in _ENTITLEMENT_KEYS:
        raise ValueError("unsupported_entitlement")
    existing = db.scalar(
        select(RewardEntitlementGrant).where(
            RewardEntitlementGrant.order_id == order.id,
            RewardEntitlementGrant.entitlement_key == order.entitlement_key_snapshot,
        )
    )
    if existing is not None:
        return
    duration = order.entitlement_duration_days_snapshot
    expires_at = now + timedelta(days=duration * order.quantity) if duration else None
    db.add(
        RewardEntitlementGrant(
            user_id=order.user_id,
            order_id=order.id,
            entitlement_key=order.entitlement_key_snapshot,
            status=RewardEntitlementStatus.ACTIVE,
            starts_at=now,
            expires_at=expires_at,
            created_at=now,
        )
    )


def process_pending_fulfillments(
    db: Session, *, limit: int = 50, worker_id: str = "reward-worker"
) -> dict[str, int]:
    now = utc_now()
    recovered = list(db.scalars(
        select(RewardFulfillment)
        .where(
            RewardFulfillment.status == RewardFulfillmentStatus.RUNNING,
            RewardFulfillment.lease_expires_at.is_not(None),
            RewardFulfillment.lease_expires_at <= now,
        )
        .with_for_update(skip_locked=True)
    ).all())
    for stale in recovered:
        stale.status = RewardFulfillmentStatus.RETRYABLE
        stale.next_retry_at = now
        stale.lease_owner = None
        stale.lease_expires_at = None
        stale.result_code = "fulfillment_lease_expired"
        stale.safe_message = "履约任务已恢复，将自动重试。"
        order = db.scalar(
            select(RewardOrder).where(RewardOrder.id == stale.order_id).with_for_update()
        )
        if order is not None and order.status == RewardOrderStatus.PROCESSING:
            order.status = RewardOrderStatus.PENDING_FULFILLMENT
            order.updated_at = now
            _append_order_event(
                db,
                order=order,
                from_status=RewardOrderStatus.PROCESSING,
                event_type="fulfillment.lease_recovered",
                actor_type=RewardActorType.SYSTEM,
                actor_id=None,
                reason_code="worker_lease_expired",
                now=now,
            )
    recovered_ids = {item.id for item in recovered}
    fulfillments = list(recovered)
    remaining = max(limit - len(fulfillments), 0)
    if remaining:
        pending = db.scalars(
            select(RewardFulfillment)
            .where(
                RewardFulfillment.id.not_in(recovered_ids) if recovered_ids else True,
                RewardFulfillment.status.in_(
                    (RewardFulfillmentStatus.PENDING, RewardFulfillmentStatus.RETRYABLE)
                ),
                or_(
                    RewardFulfillment.next_retry_at.is_(None),
                    RewardFulfillment.next_retry_at <= now,
                ),
            )
            .order_by(RewardFulfillment.created_at, RewardFulfillment.id)
            .limit(remaining)
            .with_for_update(skip_locked=True)
        ).all()
        fulfillments.extend(pending)
    succeeded = 0
    retried = 0
    failed = 0
    for fulfillment in fulfillments:
        fulfillment.lease_owner = worker_id
        fulfillment.lease_expires_at = now + timedelta(seconds=_FULFILLMENT_LEASE_SECONDS)
        order = db.scalar(
            select(RewardOrder).where(RewardOrder.id == fulfillment.order_id).with_for_update()
        )
        if order is None:
            fulfillment.status = RewardFulfillmentStatus.FAILED
            fulfillment.result_code = "order_missing"
            fulfillment.safe_message = "订单数据异常，请联系管理员。"
            fulfillment.completed_at = now
            fulfillment.lease_owner = None
            fulfillment.lease_expires_at = None
            failed += 1
            continue
        if order.status == RewardOrderStatus.CANCELLED:
            fulfillment.status = RewardFulfillmentStatus.CANCELLED
            fulfillment.completed_at = now
            fulfillment.lease_owner = None
            fulfillment.lease_expires_at = None
            continue
        if order.status == RewardOrderStatus.FULFILLED:
            fulfillment.status = RewardFulfillmentStatus.SUCCEEDED
            fulfillment.completed_at = order.fulfilled_at or now
            fulfillment.lease_owner = None
            fulfillment.lease_expires_at = None
            continue
        previous = order.status
        order.status = RewardOrderStatus.PROCESSING
        order.updated_at = now
        order.version += 1
        fulfillment.status = RewardFulfillmentStatus.RUNNING
        fulfillment.started_at = now
        _append_order_event(
            db,
            order=order,
            from_status=previous,
            event_type="fulfillment.started",
            actor_type=RewardActorType.SYSTEM,
            actor_id=None,
            reason_code="worker_claimed",
            now=now,
        )
        try:
            _grant_entitlement(db, order, now=now)
        except Exception as exc:  # noqa: BLE001 - failures become persisted, retryable facts.
            fulfillment.retry_count += 1
            fulfillment.lease_owner = None
            fulfillment.lease_expires_at = None
            fulfillment.result_code = type(exc).__name__[:128]
            fulfillment.safe_message = "权益发放暂未完成，请稍后查看。"
            if fulfillment.retry_count < _MAX_FULFILLMENT_RETRIES:
                fulfillment.status = RewardFulfillmentStatus.RETRYABLE
                fulfillment.next_retry_at = now + timedelta(
                    seconds=30 * (2 ** (fulfillment.retry_count - 1))
                )
                order.status = RewardOrderStatus.PENDING_FULFILLMENT
                retried += 1
                event_type = "fulfillment.retry_scheduled"
                reason_code = "retryable_failure"
            else:
                fulfillment.status = RewardFulfillmentStatus.FAILED
                fulfillment.completed_at = now
                order.status = RewardOrderStatus.FAILED
                order.failure_code = "entitlement_delivery_failed"
                order.failed_at = now
                failed += 1
                event_type = "fulfillment.failed"
                reason_code = "retry_limit_reached"
            order.updated_at = now
            _append_order_event(
                db,
                order=order,
                from_status=RewardOrderStatus.PROCESSING,
                event_type=event_type,
                actor_type=RewardActorType.SYSTEM,
                actor_id=None,
                reason_code=reason_code,
                now=now,
            )
            continue
        fulfillment.status = RewardFulfillmentStatus.SUCCEEDED
        fulfillment.result_code = "entitlement_granted"
        fulfillment.safe_message = "虚拟权益已发放。"
        fulfillment.next_retry_at = None
        fulfillment.completed_at = now
        fulfillment.lease_owner = None
        fulfillment.lease_expires_at = None
        order.status = RewardOrderStatus.FULFILLED
        order.fulfilled_at = now
        order.updated_at = now
        _append_order_event(
            db,
            order=order,
            from_status=RewardOrderStatus.PROCESSING,
            event_type="fulfillment.succeeded",
            actor_type=RewardActorType.SYSTEM,
            actor_id=None,
            reason_code="entitlement_granted",
            now=now,
        )
        succeeded += 1
    db.commit()
    return {
        "processed": len(fulfillments),
        "succeeded": succeeded,
        "retried": retried,
        "failed": failed,
    }


def _inventory_event_response(event: RewardInventoryEvent) -> RewardInventoryEventResponse:
    return RewardInventoryEventResponse(
        id=event.id,
        catalog_item_id=event.catalog_item_id,
        order_id=event.order_id,
        event_type=event.event_type,
        delta=event.delta,
        stock_before=event.stock_before,
        stock_after=event.stock_after,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        reason_code=event.reason_code,
        note=event.note,
        created_at=event.created_at,
    )


def adjust_catalog_inventory(
    db: Session,
    *,
    item_id: str,
    payload: RewardInventoryAdjustmentRequest,
    principal: Principal,
    context: ClientContext,
) -> AdminRewardCatalogItemResponse:
    item = db.scalar(
        select(RewardCatalogItem).where(RewardCatalogItem.id == item_id).with_for_update()
    )
    if item is None:
        raise AppError("reward.catalog_not_found", "商品不存在", status_code=404)
    if item.version != payload.expected_version:
        raise AppError(
            "reward.catalog_version_conflict",
            "商品已被其他管理员更新，请刷新后重试",
            status_code=409,
            details={"current_version": item.version},
        )
    stock_before = item.stock
    stock_after = stock_before + payload.delta
    if stock_after < 0:
        raise AppError("reward.inventory_below_zero", "库存调整后不能小于 0", status_code=409)
    now = utc_now()
    event_id = new_id()
    item.stock = stock_after
    item.version += 1
    item.updated_by = principal.user.id
    item.updated_at = now
    db.add(
        RewardInventoryEvent(
            id=event_id,
            catalog_item_id=item.id,
            event_type=RewardInventoryEventType.ADMIN_ADJUSTED,
            delta=payload.delta,
            stock_before=stock_before,
            stock_after=stock_after,
            actor_type=RewardActorType.ADMIN,
            actor_id=principal.user.id,
            reason_code=payload.reason_code,
            reference_key=event_id,
            note=payload.note,
            created_at=now,
        )
    )
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.rewards.inventory.adjusted",
        target_type="reward_catalog_item",
        target_id=item.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "reason_code": payload.reason_code,
            "delta": payload.delta,
            "stock_after": stock_after,
            "version": item.version,
        },
    )
    db.commit()
    db.refresh(item)
    return _admin_item(item)


def list_inventory_events(
    db: Session, *, item_id: str, page: int, page_size: int
) -> RewardInventoryEventListResponse:
    if db.get(RewardCatalogItem, item_id) is None:
        raise AppError("reward.catalog_not_found", "商品不存在", status_code=404)
    total = int(
        db.scalar(
            select(func.count(RewardInventoryEvent.id)).where(
                RewardInventoryEvent.catalog_item_id == item_id
            )
        )
        or 0
    )
    events = db.scalars(
        select(RewardInventoryEvent)
        .where(RewardInventoryEvent.catalog_item_id == item_id)
        .order_by(RewardInventoryEvent.created_at.desc(), RewardInventoryEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return RewardInventoryEventListResponse(
        items=[_inventory_event_response(event) for event in events],
        page=page,
        page_size=page_size,
        total=total,
    )


def _admin_fulfillment(item: RewardFulfillment) -> RewardAdminFulfillmentResponse:
    return RewardAdminFulfillmentResponse(
        id=item.id,
        attempt_no=item.attempt_no,
        delivery_kind=item.delivery_kind,
        status=item.status,
        retry_count=item.retry_count,
        result_code=item.result_code,
        safe_message=item.safe_message,
        next_retry_at=item.next_retry_at,
        started_at=item.started_at,
        completed_at=item.completed_at,
        created_at=item.created_at,
    )


def _admin_order(db: Session, order: RewardOrder) -> RewardAdminOrderResponse:
    fulfillments = db.scalars(
        select(RewardFulfillment)
        .where(RewardFulfillment.order_id == order.id)
        .order_by(RewardFulfillment.attempt_no)
    ).all()
    inventory = db.scalars(
        select(RewardInventoryEvent)
        .where(RewardInventoryEvent.order_id == order.id)
        .order_by(RewardInventoryEvent.created_at, RewardInventoryEvent.id)
    ).all()
    return RewardAdminOrderResponse(
        **_order_summary(db, order).model_dump(),
        user_id=order.user_id,
        version=order.version,
        failure_code=order.failure_code,
        points_ledger_entry_id=order.points_ledger_entry_id,
        compensation_ledger_entry_id=order.compensation_ledger_entry_id,
        fulfillments=[_admin_fulfillment(item) for item in fulfillments],
        inventory_events=[_inventory_event_response(event) for event in inventory],
        timeline=_timeline(db, order.id),
    )


def list_admin_orders(
    db: Session,
    *,
    status: RewardOrderStatus | None,
    catalog_item_id: str | None,
    order_no: str | None,
    user_id: str | None,
    page: int,
    page_size: int,
) -> RewardAdminOrderListResponse:
    conditions = []
    if status is not None:
        conditions.append(RewardOrder.status == status)
    if catalog_item_id:
        conditions.append(RewardOrder.catalog_item_id == catalog_item_id)
    if order_no:
        conditions.append(RewardOrder.order_no == order_no.strip().upper())
    if user_id:
        conditions.append(RewardOrder.user_id == user_id.strip())
    total = int(db.scalar(select(func.count(RewardOrder.id)).where(*conditions)) or 0)
    orders = db.scalars(
        select(RewardOrder)
        .where(*conditions)
        .order_by(RewardOrder.created_at.desc(), RewardOrder.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return RewardAdminOrderListResponse(
        items=[_admin_order(db, order) for order in orders],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_admin_order(db: Session, *, order_id: str) -> RewardAdminOrderResponse:
    order = db.get(RewardOrder, order_id)
    if order is None:
        raise AppError("reward.order_not_found", "兑换订单不存在", status_code=404)
    return _admin_order(db, order)


def retry_admin_order(
    db: Session,
    *,
    order_id: str,
    payload: RewardAdminOrderActionRequest,
    principal: Principal,
    context: ClientContext,
) -> RewardAdminOrderResponse:
    order = db.scalar(select(RewardOrder).where(RewardOrder.id == order_id).with_for_update())
    if order is None:
        raise AppError("reward.order_not_found", "兑换订单不存在", status_code=404)
    if order.version != payload.expected_version:
        raise AppError(
            "reward.order_version_conflict",
            "订单已被其他操作更新，请刷新后重试",
            status_code=409,
            details={"current_version": order.version},
        )
    if order.status != RewardOrderStatus.FAILED or order.compensated_at is not None:
        raise AppError("reward.order_not_retryable", "当前订单不能重试履约", status_code=409)
    attempt_no = (
        int(
            db.scalar(
                select(func.coalesce(func.max(RewardFulfillment.attempt_no), 0)).where(
                    RewardFulfillment.order_id == order.id
                )
            )
            or 0
        )
        + 1
    )
    now = utc_now()
    previous = order.status
    order.status = RewardOrderStatus.PENDING_FULFILLMENT
    order.failure_code = None
    order.failed_at = None
    order.updated_at = now
    order.version += 1
    db.add(
        RewardFulfillment(
            order_id=order.id,
            attempt_no=attempt_no,
            delivery_kind=RewardDeliveryKind.INTERNAL_ENTITLEMENT,
            status=RewardFulfillmentStatus.PENDING,
            retry_count=0,
            next_retry_at=now,
            created_at=now,
        )
    )
    _append_order_event(
        db,
        order=order,
        from_status=previous,
        event_type="fulfillment.admin_retried",
        actor_type=RewardActorType.ADMIN,
        actor_id=principal.user.id,
        reason_code=payload.reason_code,
        now=now,
    )
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.rewards.order.retry",
        target_type="reward_order",
        target_id=order.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"reason_code": payload.reason_code, "attempt_no": attempt_no},
    )
    db.commit()
    db.refresh(order)
    return _admin_order(db, order)


def compensate_admin_order(
    db: Session,
    *,
    order_id: str,
    payload: RewardAdminOrderActionRequest,
    principal: Principal,
    context: ClientContext,
) -> RewardAdminOrderResponse:
    order = db.scalar(select(RewardOrder).where(RewardOrder.id == order_id).with_for_update())
    if order is None:
        raise AppError("reward.order_not_found", "兑换订单不存在", status_code=404)
    if order.version != payload.expected_version:
        raise AppError(
            "reward.order_version_conflict",
            "订单已被其他操作更新，请刷新后重试",
            status_code=409,
            details={"current_version": order.version},
        )
    if order.status != RewardOrderStatus.FAILED:
        raise AppError(
            "reward.order_not_compensatable", "只有履约失败订单可以补偿", status_code=409
        )
    db.scalar(select(User).where(User.id == order.user_id).with_for_update())
    item = db.scalar(
        select(RewardCatalogItem)
        .where(RewardCatalogItem.id == order.catalog_item_id)
        .with_for_update()
    )
    if item is None:
        raise AppError("reward.catalog_not_found", "商品不存在", status_code=409)
    now = utc_now()
    _compensate_order(
        db,
        order=order,
        item=item,
        actor_type=RewardActorType.ADMIN,
        actor_id=principal.user.id,
        event_type="reward.fulfillment_compensation",
        reason_code=payload.reason_code,
        now=now,
    )
    order.updated_at = now
    order.version += 1
    _append_order_event(
        db,
        order=order,
        from_status=RewardOrderStatus.FAILED,
        event_type="order.compensated",
        actor_type=RewardActorType.ADMIN,
        actor_id=principal.user.id,
        reason_code=payload.reason_code,
        now=now,
    )
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.rewards.order.compensate",
        target_type="reward_order",
        target_id=order.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"reason_code": payload.reason_code, "points": order.total_cost_points},
    )
    db.commit()
    db.refresh(order)
    return _admin_order(db, order)


def get_operations_stats(db: Session) -> RewardOperationsStatsResponse:
    counts = dict(
        db.execute(
            select(RewardOrder.status, func.count(RewardOrder.id)).group_by(RewardOrder.status)
        ).all()
    )
    total = sum(int(value) for value in counts.values())
    fulfilled = int(counts.get(RewardOrderStatus.FULFILLED, 0))
    failed = int(counts.get(RewardOrderStatus.FAILED, 0))
    completed = fulfilled + failed
    redeemed_points = int(
        db.scalar(select(func.coalesce(func.sum(RewardOrder.total_cost_points), 0))) or 0
    )
    compensated_points = int(
        db.scalar(
            select(func.coalesce(func.sum(RewardOrder.total_cost_points), 0)).where(
                RewardOrder.compensated_at.is_not(None)
            )
        )
        or 0
    )
    low_stock = int(
        db.scalar(
            select(func.count(RewardCatalogItem.id)).where(
                RewardCatalogItem.status == RewardCatalogStatus.ACTIVE,
                RewardCatalogItem.stock < 10,
            )
        )
        or 0
    )
    return RewardOperationsStatsResponse(
        total_orders=total,
        pending_orders=int(counts.get(RewardOrderStatus.PENDING_FULFILLMENT, 0))
        + int(counts.get(RewardOrderStatus.PROCESSING, 0)),
        fulfilled_orders=fulfilled,
        failed_orders=failed,
        cancelled_orders=int(counts.get(RewardOrderStatus.CANCELLED, 0)),
        redeemed_points=redeemed_points,
        compensated_points=compensated_points,
        fulfillment_success_rate=round(fulfilled / completed * 100, 2) if completed else 0.0,
        low_stock_items=low_stock,
    )
