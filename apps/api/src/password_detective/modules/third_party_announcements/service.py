from __future__ import annotations

from sqlalchemy.orm import Session

from password_detective.db.audit import write_audit_log
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.desktop_announcements.schemas import DesktopAnnouncementListResponse
from password_detective.modules.desktop_announcements.service import list_public_announcements
from password_detective.modules.third_party_announcements.schemas import (
    ThirdPartyAnnouncementItem,
    ThirdPartyAnnouncementListResponse,
)
from password_detective.modules.third_party_oauth.dependencies import ThirdPartyPrincipal


def list_third_party_announcements(
    db: Session,
    *,
    limit: int,
    principal: ThirdPartyPrincipal,
    context: ClientContext,
) -> ThirdPartyAnnouncementListResponse:
    public_response: DesktopAnnouncementListResponse = list_public_announcements(db, limit=limit)
    response = ThirdPartyAnnouncementListResponse(
        items=[
            ThirdPartyAnnouncementItem(
                id=item.id,
                title=item.title,
                content=item.content,
                content_type=item.content_type,
                image_urls=item.image_urls,
                action_label=item.action_label,
                action_url=item.action_url,
                sort_order=item.sort_order,
                starts_at=item.starts_at,
                ends_at=item.ends_at,
            )
            for item in public_response.items
        ]
    )
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="third_party_announcement.list_read",
        target_type="third_party_app",
        target_id=principal.app.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "client_id": principal.app.client_id,
            "item_count": len(response.items),
        },
    )
    db.commit()
    return response
