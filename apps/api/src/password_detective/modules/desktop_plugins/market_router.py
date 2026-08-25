from __future__ import annotations

import base64
import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.modules.desktop_plugins.schemas import (
    DownloadTicketRequest,
    DownloadTicketResponse,
    PluginArchitecture,
    PluginCategory,
    PluginRevocationListResponse,
    PublicPluginCatalogResponse,
    PublicPluginDetailResponse,
    PublicPluginVersionResponse,
)
from password_detective.modules.desktop_plugins.service import (
    create_download_ticket,
    get_public_plugin,
    get_public_version,
    list_public_catalog,
    list_revocations,
    prepare_download,
)

router = APIRouter(prefix="/desktop/plugins", tags=["桌面插件市场"])


@router.get(
    "/catalog",
    response_model=PublicPluginCatalogResponse,
    dependencies=[Depends(rate_limit("desktop.plugin.catalog", limit=120, window_seconds=60))],
)
def plugin_catalog(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    query: Annotated[str | None, Query(max_length=128)] = None,
    category: PluginCategory | None = None,
    architecture: PluginArchitecture = "windows-x64",
    host_version: Annotated[str, Query(min_length=5, max_length=32)] = "0.1.0",
    protocol_version: Annotated[int, Query(ge=1, le=1)] = 1,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PublicPluginCatalogResponse:
    response.headers["Cache-Control"] = "public, max-age=60"
    return list_public_catalog(
        db,
        query=query,
        category=category,
        architecture=architecture,
        host_version=host_version,
        protocol_version=protocol_version,
        page=page,
        page_size=page_size,
    )


@router.get("/revocations", response_model=PluginRevocationListResponse)
def plugin_revocations(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> JSONResponse | Response:
    payload = list_revocations(db)
    body = payload.model_dump(mode="json")
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    etag = f'"sha256-{hashlib.sha256(canonical.encode("utf-8")).hexdigest()}"'
    headers = {"Cache-Control": "public, max-age=300", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=body, headers=headers)


@router.get(
    "/downloads/{token}",
    name="download_desktop_plugin_artifact",
    dependencies=[Depends(rate_limit("desktop.plugin.download", limit=60, window_seconds=60))],
)
def download_plugin_artifact(
    token: str,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    artifact, path = prepare_download(db, settings, raw_token=token)
    digest = base64.b64encode(bytes.fromhex(artifact.sha256)).decode("ascii")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=artifact.artifact_filename,
        headers={
            "Cache-Control": "private, no-store",
            "ETag": f'"sha256-{artifact.sha256}"',
            "Digest": f"sha-256={digest}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{plugin_slug}", response_model=PublicPluginDetailResponse)
def plugin_detail(
    plugin_slug: str,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> PublicPluginDetailResponse:
    response.headers["Cache-Control"] = "public, max-age=60"
    return get_public_plugin(db, slug=plugin_slug)


@router.get("/{plugin_slug}/versions/{semver}", response_model=PublicPluginVersionResponse)
def plugin_version(
    plugin_slug: str,
    semver: str,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> PublicPluginVersionResponse:
    response.headers["Cache-Control"] = "public, max-age=60"
    return get_public_version(db, slug=plugin_slug, semver=semver)


@router.post(
    "/{plugin_slug}/download-ticket",
    response_model=DownloadTicketResponse,
    dependencies=[
        Depends(rate_limit("desktop.plugin.download_ticket", limit=60, window_seconds=60))
    ],
)
def issue_plugin_download_ticket(
    plugin_slug: str,
    payload: DownloadTicketRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DownloadTicketResponse:
    response.headers["Cache-Control"] = "no-store"
    return create_download_ticket(
        db,
        settings,
        slug=plugin_slug,
        semver=payload.semver,
        architecture=payload.architecture,
        download_url_builder=lambda token: str(
            request.url_for("download_desktop_plugin_artifact", token=token)
        ),
    )
