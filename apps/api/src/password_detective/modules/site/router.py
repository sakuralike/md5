from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, PlainTextResponse, Response
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.modules.site.assets import resolve_community_avatar, resolve_site_logo
from password_detective.modules.site.schemas import HomeDiscoveryResponse, PublicSiteConfigResponse
from password_detective.modules.site.seo import (
    build_robots_txt,
    build_sitemap_xml,
    seo_settings_for_files,
)
from password_detective.modules.site.service import get_home_discovery, get_public_site_config

router = APIRouter(prefix="/site", tags=["站点公开信息"])


@router.get(
    "/config",
    response_model=PublicSiteConfigResponse,
    dependencies=[Depends(rate_limit("site.config", limit=240, window_seconds=60))],
)
def public_site_config(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PublicSiteConfigResponse:
    return get_public_site_config(
        db,
        maintenance_force_disabled=settings.maintenance_force_disabled,
    )


@router.get(
    "/home-discovery",
    response_model=HomeDiscoveryResponse,
    dependencies=[Depends(rate_limit("site.home_discovery", limit=120, window_seconds=60))],
)
def home_discovery(db: Annotated[Session, Depends(get_db)]) -> HomeDiscoveryResponse:
    return get_home_discovery(db, limit=5)


@router.get(
    "/robots.txt",
    response_class=PlainTextResponse,
    dependencies=[Depends(rate_limit("site.robots", limit=60, window_seconds=60))],
)
def robots_txt(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PlainTextResponse:
    seo_settings = seo_settings_for_files(db)
    return PlainTextResponse(
        build_robots_txt(seo_settings, public_origin=settings.public_origin),
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get(
    "/sitemap.xml",
    dependencies=[Depends(rate_limit("site.sitemap", limit=60, window_seconds=60))],
)
def sitemap_xml(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    seo_settings = seo_settings_for_files(db)
    return Response(
        content=build_sitemap_xml(seo_settings, public_origin=settings.public_origin),
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


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
