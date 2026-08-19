from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.reward_catalog import (
    RewardCatalogItem,
    RewardCatalogKind,
    RewardCatalogStatus,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.rewards.schemas import (
    AdminRewardCatalogItemResponse,
    AdminRewardCatalogListResponse,
    RewardCatalogCreateRequest,
    RewardCatalogItemResponse,
    RewardCatalogResponse,
    RewardCatalogUpdateRequest,
)


def _stock_status(stock: int) -> str:
    if stock <= 0:
        return "out_of_stock"
    return "limited" if stock <= 10 else "available"


def _public_item(item: RewardCatalogItem) -> RewardCatalogItemResponse:
    return RewardCatalogItemResponse(
        id=item.id,
        slug=item.slug,
        name=item.name,
        description=item.description,
        kind=item.kind,
        cost_points=item.cost_points,
        per_user_limit=item.per_user_limit,
        stock_status=_stock_status(item.stock),
    )


def _admin_item(item: RewardCatalogItem) -> AdminRewardCatalogItemResponse:
    return AdminRewardCatalogItemResponse(
        id=item.id,
        slug=item.slug,
        name=item.name,
        description=item.description,
        kind=item.kind,
        cost_points=item.cost_points,
        stock=item.stock,
        per_user_limit=item.per_user_limit,
        stock_status=_stock_status(item.stock),
        status=item.status,
        version=item.version,
        created_by=item.created_by,
        updated_by=item.updated_by,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def list_public_catalog(db: Session, *, principal: Principal | None) -> RewardCatalogResponse:
    items = db.scalars(
        select(RewardCatalogItem)
        .where(
            RewardCatalogItem.kind == RewardCatalogKind.VIRTUAL,
            RewardCatalogItem.status == RewardCatalogStatus.ACTIVE,
        )
        .order_by(RewardCatalogItem.created_at.desc(), RewardCatalogItem.id.desc())
    ).all()
    available_points: int | None = None
    if principal is not None:
        available_points = int(
            db.scalar(
                select(
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    PointsLedger.status == PointsLedgerStatus.POSTED,
                                    PointsLedger.amount,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    )
                ).where(PointsLedger.user_id == principal.user.id)
            )
            or 0
        )
    return RewardCatalogResponse(
        items=[_public_item(item) for item in items],
        available_points=available_points,
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
        .order_by(RewardCatalogItem.updated_at.desc(), RewardCatalogItem.id.desc())
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
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
        kind=RewardCatalogKind.VIRTUAL,
        cost_points=payload.cost_points,
        stock=payload.stock,
        per_user_limit=payload.per_user_limit,
        status=payload.status,
        version=1,
        created_by=principal.user.id,
        updated_by=principal.user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.rewards.catalog.created",
        target_type="reward_catalog_item",
        target_id=item.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"reason_code": payload.reason_code, "slug": payload.slug, "kind": "virtual"},
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
        select(RewardCatalogItem)
        .where(RewardCatalogItem.id == item_id)
        .with_for_update()
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
    item.stock = payload.stock
    item.per_user_limit = payload.per_user_limit
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
