from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from password_detective.db.models.desktop_announcement import DesktopAnnouncementContentType


class ThirdPartyAnnouncementItem(BaseModel):
    id: str
    title: str
    content: str
    content_type: DesktopAnnouncementContentType
    image_urls: list[str]
    action_label: str | None
    action_url: str | None
    sort_order: int
    starts_at: datetime | None
    ends_at: datetime | None


class ThirdPartyAnnouncementListResponse(BaseModel):
    items: list[ThirdPartyAnnouncementItem]
