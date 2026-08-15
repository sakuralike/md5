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
from password_detective.modules.site.assets import (
    resolve_web_announcement_image,
    store_web_announcement_image,
)
from password_detective.modules.web_announcements.schemas import (
    WebAnnouncementImageUploadResponse,
    WebAnnouncementListResponse,
    WebAnnouncementResponse,
    WebAnnouncementWriteRequest,
)
from password_detective.modules.web_announcements.service import (
    archive_announcement,
    create_announcement,
    list_admin_announcements,
    list_public_announcements,
    publish_announcement,
    update_announcement,
)

public_router = APIRouter(prefix="/web/announcements", tags=["Web 公告"])
admin_router = APIRouter(prefix="/admin/web-announcements", tags=["管理端·Web 公告"])


@public_router.get(
    "",
    response_model=WebAnnouncementListResponse,
    dependencies=[Depends(rate_limit("web.announcement.list", limit=60, window_seconds=60))],
)
def public_announcements(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> WebAnnouncementListResponse:
    response.headers["Cache-Control"] = "public, max-age=30"
    return list_public_announcements(db, limit=limit)


@public_router.get("/assets/{asset_name}", response_class=FileResponse)
def public_announcement_image(
    asset_name: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    path, content_type = resolve_web_announcement_image(settings, asset_name)
    etag = f'"{asset_name.rsplit(".", 1)[0]}"'
    cache_headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "Content-Disposition": "inline",
        "ETag": etag,
    }
    if_none_match = request.headers.get("if-none-match", "")
    if any(
        candidate.strip() in {etag, f"W/{etag}", "*"}
        for candidate in if_none_match.split(",")
    ):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=cache_headers)
    return FileResponse(path, media_type=content_type, headers=cache_headers)


@admin_router.post(
    "/images",
    response_model=WebAnnouncementImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit("admin.web.announcement.image_upload", limit=30, window_seconds=3600))
    ],
)
async def upload_web_announcement_image(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WebAnnouncementImageUploadResponse:
    stored = await store_web_announcement_image(request, settings)
    context = get_client_context(request)
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.web_announcement.image_uploaded",
        target_type="web_announcement_image",
        target_id=stored.sha256,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"content_type": stored.content_type, "size_bytes": stored.size_bytes},
    )
    db.commit()
    return WebAnnouncementImageUploadResponse(
        url=stored.url,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
    )


@admin_router.get("", response_model=WebAnnouncementListResponse)
def admin_announcements(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> WebAnnouncementListResponse:
    del principal
    return list_admin_announcements(db)


@admin_router.post(
    "",
    response_model=WebAnnouncementResponse,
    status_code=201,
    dependencies=[
        Depends(rate_limit("admin.web.announcement.create", limit=30, window_seconds=60))
    ],
)
def create_web_announcement(
    payload: WebAnnouncementWriteRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> WebAnnouncementResponse:
    return create_announcement(
        db, payload=payload, principal=principal, context=get_client_context(request)
    )


@admin_router.put(
    "/{announcement_id}",
    response_model=WebAnnouncementResponse,
    dependencies=[
        Depends(rate_limit("admin.web.announcement.update", limit=60, window_seconds=60))
    ],
)
def put_web_announcement(
    announcement_id: str,
    payload: WebAnnouncementWriteRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> WebAnnouncementResponse:
    return update_announcement(
        db,
        announcement_id=announcement_id,
        payload=payload,
        principal=principal,
        context=get_client_context(request),
    )


@admin_router.post("/{announcement_id}/publish", response_model=WebAnnouncementResponse)
def publish_web_announcement(
    announcement_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> WebAnnouncementResponse:
    return publish_announcement(
        db,
        announcement_id=announcement_id,
        principal=principal,
        context=get_client_context(request),
    )


@admin_router.post("/{announcement_id}/archive", response_model=WebAnnouncementResponse)
def archive_web_announcement(
    announcement_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> WebAnnouncementResponse:
    return archive_announcement(
        db,
        announcement_id=announcement_id,
        principal=principal,
        context=get_client_context(request),
    )
