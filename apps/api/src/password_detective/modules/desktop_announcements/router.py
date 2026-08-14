from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import Principal, require_admin_mfa
from password_detective.modules.desktop_announcements.schemas import (
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
