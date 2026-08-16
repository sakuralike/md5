from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.db.models.desktop_update import DesktopArchitecture, DesktopReleaseChannel
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.desktop_updates.schemas import DesktopPlatform
from password_detective.modules.third_party_oauth.dependencies import (
    ThirdPartyPrincipal,
    require_third_party_scope,
)
from password_detective.modules.third_party_updates.schemas import (
    ThirdPartyUpdateCheckResponse,
)
from password_detective.modules.third_party_updates.service import check_third_party_update

router = APIRouter(prefix="/third-party/updates", tags=["第三方 API·桌面更新"])
DbSession = Annotated[Session, Depends(get_db)]
UpdatePrincipal = Annotated[
    ThirdPartyPrincipal,
    Depends(require_third_party_scope("updates:read")),
]


@router.get(
    "/check",
    response_model=ThirdPartyUpdateCheckResponse,
    dependencies=[Depends(rate_limit("third_party.update.check", limit=60, window_seconds=60))],
)
def third_party_update_check(
    request: Request,
    response: Response,
    db: DbSession,
    principal: UpdatePrincipal,
    current_version: Annotated[str, Query(min_length=5, max_length=32)],
    channel: DesktopReleaseChannel = DesktopReleaseChannel.STABLE,
    platform: DesktopPlatform = "windows",
    architecture: DesktopArchitecture = DesktopArchitecture.X64,
) -> ThirdPartyUpdateCheckResponse:
    response.headers["Cache-Control"] = "private, no-store"
    return check_third_party_update(
        db,
        current_version=current_version,
        channel=channel,
        platform=platform,
        architecture=architecture,
        download_url_builder=lambda release_id: request.url_for(
            "download_desktop_update", release_id=release_id
        ),
        principal=principal,
        context=get_client_context(request),
    )
