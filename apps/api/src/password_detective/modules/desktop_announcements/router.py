from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.rate_limit import rate_limit
from password_detective.db.audit import write_audit_log
from password_detective.db.dependencies import get_db
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import Principal, require_admin_mfa
from password_detective.modules.desktop_announcements.schemas import (
    DesktopAnnouncementImageUploadResponse,
    DesktopAnnouncementListResponse,
    DesktopAnnouncementResponse,
    DesktopAnnouncementWriteRequest,
)
from password_detective.modules.desktop_announcements.service import (
    archive_announcement,
    create_announcement,
    list_admin_announcements,
    list_public_announcements,
    publish_announcement,
    update_announcement,
)
from password_detective.modules.site.assets import (
    resolve_desktop_announcement_image,
    store_desktop_announcement_image,
)

public_router = APIRouter(prefix="/desktop/announcements", tags=["桌面公告"])
admin_router = APIRouter(prefix="/admin/desktop-announcements", tags=["管理端·桌面公告"])


@public_router.get(
    "",
    response_model=DesktopAnnouncementListResponse,
    dependencies=[Depends(rate_limit("desktop.announcement.list", limit=60, window_seconds=60))],
)
def public_announcements(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> DesktopAnnouncementListResponse:
    response.headers["Cache-Control"] = "public, max-age=30"
    return list_public_announcements(db, limit=limit)


@public_router.get("/assets/{asset_name}", response_class=FileResponse)
def public_announcement_image(
    asset_name: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    path, content_type = resolve_desktop_announcement_image(settings, asset_name)
    return FileResponse(
        path,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Disposition": "inline",
        },
    )


@admin_router.post(
    "/images",
    response_model=DesktopAnnouncementImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            rate_limit("admin.desktop.announcement.image_upload", limit=30, window_seconds=3600)
        )
    ],
)
async def upload_desktop_announcement_image(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DesktopAnnouncementImageUploadResponse:
    stored = await store_desktop_announcement_image(request, settings)
    context = get_client_context(request)
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.desktop_announcement.image_uploaded",
        target_type="desktop_announcement_image",
        target_id=stored.sha256,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"content_type": stored.content_type, "size_bytes": stored.size_bytes},
    )
    db.commit()
    return DesktopAnnouncementImageUploadResponse(
        url=stored.url,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
    )


@admin_router.get("", response_model=DesktopAnnouncementListResponse)
def admin_announcements(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> DesktopAnnouncementListResponse:
    del principal
    return list_admin_announcements(db)


@admin_router.post(
    "",
    response_model=DesktopAnnouncementResponse,
    status_code=201,
    dependencies=[
        Depends(rate_limit("admin.desktop.announcement.create", limit=30, window_seconds=60))
    ],
)
def create_desktop_announcement(
    payload: DesktopAnnouncementWriteRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> DesktopAnnouncementResponse:
    return create_announcement(
        db, payload=payload, principal=principal, context=get_client_context(request)
    )


@admin_router.put(
    "/{announcement_id}",
    response_model=DesktopAnnouncementResponse,
    dependencies=[
        Depends(rate_limit("admin.desktop.announcement.update", limit=60, window_seconds=60))
    ],
)
def put_desktop_announcement(
    announcement_id: str,
    payload: DesktopAnnouncementWriteRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> DesktopAnnouncementResponse:
    return update_announcement(
        db,
        announcement_id=announcement_id,
        payload=payload,
        principal=principal,
        context=get_client_context(request),
    )


@admin_router.post("/{announcement_id}/publish", response_model=DesktopAnnouncementResponse)
def publish_desktop_announcement(
    announcement_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> DesktopAnnouncementResponse:
    return publish_announcement(
        db,
        announcement_id=announcement_id,
        principal=principal,
        context=get_client_context(request),
    )


@admin_router.post("/{announcement_id}/archive", response_model=DesktopAnnouncementResponse)
def archive_desktop_announcement(
    announcement_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> DesktopAnnouncementResponse:
    return archive_announcement(
        db,
        announcement_id=announcement_id,
        principal=principal,
        context=get_client_context(request),
    )
