from __future__ import annotations

import base64
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.db.models.desktop_update import (
    DesktopArchitecture,
    DesktopReleaseChannel,
)
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import Principal, require_admin_mfa
from password_detective.modules.desktop_updates.schemas import (
    DesktopReleaseCreateRequest,
    DesktopReleaseListResponse,
    DesktopReleaseResponse,
    DesktopUpdateCheckResponse,
)
from password_detective.modules.desktop_updates.service import (
    check_for_update,
    create_release,
    list_releases,
    prepare_download,
    publish_release,
    upload_artifact,
    withdraw_release,
)

public_router = APIRouter(prefix="/desktop/updates", tags=["桌面更新"])
admin_router = APIRouter(prefix="/admin/desktop-releases", tags=["管理端·桌面发布"])


@public_router.get(
    "/check",
    response_model=DesktopUpdateCheckResponse,
    dependencies=[Depends(rate_limit("desktop.update.check", limit=60, window_seconds=60))],
)
def update_check(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    current_version: Annotated[str, Query(min_length=5, max_length=32)],
    channel: DesktopReleaseChannel = DesktopReleaseChannel.STABLE,
    platform: Literal["windows"] = "windows",
    architecture: DesktopArchitecture = DesktopArchitecture.X64,
) -> DesktopUpdateCheckResponse:
    response.headers["Cache-Control"] = "public, max-age=60"
    return check_for_update(
        db,
        current_version=current_version,
        channel=channel,
        platform=platform,
        architecture=architecture,
        download_url_builder=lambda release_id: request.url_for(
            "download_desktop_update", release_id=release_id
        ),
    )


@public_router.get(
    "/{release_id}/download",
    name="download_desktop_update",
    dependencies=[Depends(rate_limit("desktop.update.download", limit=30, window_seconds=60))],
)
def download_update(
    release_id: str,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    release, path = prepare_download(db, settings, release_id=release_id)
    digest = base64.b64encode(bytes.fromhex(release.artifact_sha256)).decode("ascii")
    return FileResponse(
        path,
        media_type=release.content_type,
        filename=release.artifact_filename,
        headers={
            "Cache-Control": (
                f"public, max-age={settings.desktop_update_download_cache_seconds}, immutable"
            ),
            "ETag": f'"sha256-{release.artifact_sha256}"',
            "Digest": f"sha-256={digest}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@admin_router.post(
    "",
    response_model=DesktopReleaseResponse,
    status_code=201,
    dependencies=[Depends(rate_limit("admin.desktop.release.create", limit=30, window_seconds=60))],
)
def create_desktop_release(
    payload: DesktopReleaseCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> DesktopReleaseResponse:
    return create_release(
        db,
        settings,
        payload=payload,
        principal=principal,
        context=get_client_context(request),
    )


@admin_router.get("", response_model=DesktopReleaseListResponse)
def desktop_releases(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> DesktopReleaseListResponse:
    del principal
    return list_releases(db)


@admin_router.put(
    "/{release_id}/artifact",
    response_model=DesktopReleaseResponse,
    dependencies=[Depends(rate_limit("admin.desktop.release.upload", limit=10, window_seconds=60))],
)
async def put_desktop_release_artifact(
    release_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> DesktopReleaseResponse:
    raw_content_length = request.headers.get("content-length")
    content_length = (
        int(raw_content_length) if raw_content_length and raw_content_length.isdigit() else None
    )
    return await upload_artifact(
        db,
        settings,
        release_id=release_id,
        chunks=request.stream(),
        content_length=content_length,
        principal=principal,
        context=get_client_context(request),
    )


@admin_router.post(
    "/{release_id}/publish",
    response_model=DesktopReleaseResponse,
    dependencies=[
        Depends(rate_limit("admin.desktop.release.publish", limit=20, window_seconds=60))
    ],
)
def publish_desktop_release(
    release_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> DesktopReleaseResponse:
    return publish_release(
        db,
        settings,
        release_id=release_id,
        principal=principal,
        context=get_client_context(request),
    )


@admin_router.post(
    "/{release_id}/withdraw",
    response_model=DesktopReleaseResponse,
    dependencies=[
        Depends(rate_limit("admin.desktop.release.withdraw", limit=20, window_seconds=60))
    ],
)
def withdraw_desktop_release(
    release_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> DesktopReleaseResponse:
    return withdraw_release(
        db,
        release_id=release_id,
        principal=principal,
        context=get_client_context(request),
    )
