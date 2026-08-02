from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from password_detective.db.dependencies import get_db
from password_detective.modules.auth.dependencies import Principal, get_current_principal
from password_detective.modules.reputation.schemas import (
    PointsLedgerResponse,
    ReputationEventsResponse,
    TrustProfileResponse,
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
