from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.third_party_announcements.schemas import (
    ThirdPartyAnnouncementListResponse,
)
from password_detective.modules.third_party_announcements.service import (
    list_third_party_announcements,
)
from password_detective.modules.third_party_oauth.dependencies import (
    ThirdPartyPrincipal,
    require_third_party_scope,
)

router = APIRouter(prefix="/third-party", tags=["第三方 API·桌面公告"])
DbSession = Annotated[Session, Depends(get_db)]
AnnouncementPrincipal = Annotated[
    ThirdPartyPrincipal,
    Depends(require_third_party_scope("announcements:read")),
]


@router.get(
    "/announcements",
    response_model=ThirdPartyAnnouncementListResponse,
    dependencies=[
        Depends(rate_limit("third_party.announcement.list", limit=60, window_seconds=60))
    ],
)
def third_party_announcements(
    request: Request,
    response: Response,
    db: DbSession,
    principal: AnnouncementPrincipal,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> ThirdPartyAnnouncementListResponse:
    response.headers["Cache-Control"] = "private, no-store"
    return list_third_party_announcements(
        db,
        limit=limit,
        principal=principal,
        context=get_client_context(request),
    )
