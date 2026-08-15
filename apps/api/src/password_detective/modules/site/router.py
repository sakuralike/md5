from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.modules.site.assets import resolve_community_avatar, resolve_site_logo
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


@router.get("/assets/logo/{asset_name}", response_class=FileResponse)
def public_site_logo(
    asset_name: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    path, content_type = resolve_site_logo(settings, asset_name)
    return FileResponse(
        path,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Disposition": "inline",
        },
    )


@router.get("/assets/avatars/{asset_name}", response_class=FileResponse)
def public_community_avatar(
    asset_name: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    path, content_type = resolve_community_avatar(settings, asset_name)
    return FileResponse(
        path,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Disposition": "inline",
        },
    )
