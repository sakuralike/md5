from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from password_detective.db.dependencies import get_db
from password_detective.modules.auth.dependencies import Principal, get_current_principal
from password_detective.modules.reputation.levels import (
    get_level_catalog,
    get_user_level_profile,
    list_growth_events,
)
from password_detective.modules.reputation.schemas import (
    GrowthEventsResponse,
    PointsLedgerResponse,
    ReputationEventsResponse,
    TrustProfileResponse,
    UserLevelCatalogResponse,
    UserLevelProfileResponse,
)
from password_detective.modules.reputation.service import (
    get_trust_profile,
    list_my_points,
    list_my_reputation_events,
)

router = APIRouter(prefix="/me", tags=["用户中心·积分与信誉"])


@router.get("/trust-profile", response_model=TrustProfileResponse)
def trust_profile(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> TrustProfileResponse:
    return get_trust_profile(db, principal=principal)


@router.get("/points", response_model=PointsLedgerResponse)
def my_points(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PointsLedgerResponse:
    return list_my_points(db, principal=principal, page=page, page_size=page_size)


@router.get("/reputation", response_model=ReputationEventsResponse)
def my_reputation_events(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ReputationEventsResponse:
    return list_my_reputation_events(db, principal=principal, page=page, page_size=page_size)


@router.get("/level", response_model=UserLevelProfileResponse)
def my_level(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> UserLevelProfileResponse:
    return get_user_level_profile(db, user_id=principal.user.id)


@router.get("/level-catalog", response_model=UserLevelCatalogResponse)
def level_catalog(
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[Principal, Depends(get_current_principal)],
) -> UserLevelCatalogResponse:
    return get_level_catalog(db)


@router.get("/growth-events", response_model=GrowthEventsResponse)
def my_growth_events(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> GrowthEventsResponse:
    return list_growth_events(
        db, user_id=principal.user.id, page=page, page_size=page_size
    )
