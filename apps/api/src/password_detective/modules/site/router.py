from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.modules.site.schemas import HomeDiscoveryResponse, PublicSiteConfigResponse
from password_detective.modules.site.service import get_home_discovery, get_public_site_config

router = APIRouter(prefix="/site", tags=["站点公开信息"])


@router.get(
    "/config",
    response_model=PublicSiteConfigResponse,
    dependencies=[Depends(rate_limit("site.config", limit=240, window_seconds=60))],
)
def public_site_config(db: Annotated[Session, Depends(get_db)]) -> PublicSiteConfigResponse:
    return get_public_site_config(db)


@router.get(
    "/home-discovery",
    response_model=HomeDiscoveryResponse,
    dependencies=[Depends(rate_limit("site.home_discovery", limit=120, window_seconds=60))],
)
def home_discovery(db: Annotated[Session, Depends(get_db)]) -> HomeDiscoveryResponse:
    return get_home_discovery(db, limit=5)
