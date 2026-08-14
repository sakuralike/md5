from __future__ import annotations

import json

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.web_announcement import (
    WebAnnouncement,
    WebAnnouncementStatus,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.web_announcements.schemas import (
    WebAnnouncementListResponse,
    WebAnnouncementResponse,
    WebAnnouncementWriteRequest,
)


def _decode_images(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _to_response(item: WebAnnouncement) -> WebAnnouncementResponse:
    return WebAnnouncementResponse(
        id=item.id,
        title=item.title,
        content=item.content,
        content_type=item.content_type,
        image_urls=_decode_images(item.image_urls_json),
        action_label=item.action_label,
        action_url=item.action_url,
        sort_order=item.sort_order,
        auto_close_seconds=item.auto_close_seconds,
        starts_at=item.starts_at,
        ends_at=item.ends_at,
        status=item.status,
        revision=item.revision,
        created_at=item.created_at,
        updated_at=item.updated_at,
        published_at=item.published_at,
        archived_at=item.archived_at,
    )


def list_public_announcements(db: Session, *, limit: int) -> WebAnnouncementListResponse:
    now = utc_now()
    items = db.scalars(
        select(WebAnnouncement)
        .where(
            WebAnnouncement.status == WebAnnouncementStatus.PUBLISHED,
            or_(WebAnnouncement.starts_at.is_(None), WebAnnouncement.starts_at <= now),
            or_(WebAnnouncement.ends_at.is_(None), WebAnnouncement.ends_at > now),
        )
        .order_by(
            WebAnnouncement.sort_order.desc(),
            WebAnnouncement.published_at.desc(),
            WebAnnouncement.created_at.desc(),
        )
        .limit(limit)
    ).all()
    return WebAnnouncementListResponse(items=[_to_response(item) for item in items])


def list_admin_announcements(db: Session) -> WebAnnouncementListResponse:
    items = db.scalars(
        select(WebAnnouncement).order_by(
            WebAnnouncement.created_at.desc(), WebAnnouncement.id.desc()
        )
    ).all()
    return WebAnnouncementListResponse(items=[_to_response(item) for item in items])


def create_announcement(
    db: Session,
    *,
    payload: WebAnnouncementWriteRequest,
    principal: Principal,
    context: ClientContext,
) -> WebAnnouncementResponse:
    item = WebAnnouncement(
        title=payload.title,
        content=payload.content,
        content_type=payload.content_type,
        image_urls_json=json.dumps(payload.image_urls, ensure_ascii=False),
        action_label=payload.action_label,
        action_url=payload.action_url,
        sort_order=payload.sort_order,
        auto_close_seconds=payload.auto_close_seconds,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        created_by=principal.user.id,
    )
    db.add(item)
    db.flush()
    _audit(db, principal, context, item, "web.announcement.create")
    db.commit()
    db.refresh(item)
    return _to_response(item)


def update_announcement(
    db: Session,
    *,
    announcement_id: str,
    payload: WebAnnouncementWriteRequest,
    principal: Principal,
    context: ClientContext,
) -> WebAnnouncementResponse:
    item = _get_editable(db, announcement_id)
    item.title = payload.title
    item.content = payload.content
    item.content_type = payload.content_type
    item.image_urls_json = json.dumps(payload.image_urls, ensure_ascii=False)
    item.action_label = payload.action_label
    item.action_url = payload.action_url
    item.sort_order = payload.sort_order
    item.auto_close_seconds = payload.auto_close_seconds
    item.starts_at = payload.starts_at
    item.ends_at = payload.ends_at
    item.revision += 1
    _audit(db, principal, context, item, "web.announcement.update")
    db.commit()
    db.refresh(item)
    return _to_response(item)


def publish_announcement(
    db: Session,
    *,
    announcement_id: str,
    principal: Principal,
    context: ClientContext,
) -> WebAnnouncementResponse:
    item = _get_editable(db, announcement_id)
    item.status = WebAnnouncementStatus.PUBLISHED
    item.published_at = utc_now()
    item.archived_at = None
    item.revision += 1
    _audit(db, principal, context, item, "web.announcement.publish")
    db.commit()
    db.refresh(item)
    return _to_response(item)


def archive_announcement(
    db: Session,
    *,
    announcement_id: str,
    principal: Principal,
    context: ClientContext,
) -> WebAnnouncementResponse:
    item = db.get(WebAnnouncement, announcement_id)
    if item is None:
        raise AppError("web.announcement.not_found", "Web 公告不存在", status_code=404)
    if item.status == WebAnnouncementStatus.ARCHIVED:
        return _to_response(item)
    item.status = WebAnnouncementStatus.ARCHIVED
    item.archived_at = utc_now()
    item.revision += 1
    _audit(db, principal, context, item, "web.announcement.archive")
    db.commit()
    db.refresh(item)
    return _to_response(item)


def _get_editable(db: Session, announcement_id: str) -> WebAnnouncement:
    item = db.get(WebAnnouncement, announcement_id)
    if item is None:
        raise AppError("web.announcement.not_found", "Web 公告不存在", status_code=404)
    if item.status == WebAnnouncementStatus.ARCHIVED:
        raise AppError(
            "web.announcement.archived",
            "已归档公告不可编辑或重新发布，请新建公告",
            status_code=409,
        )
    return item


def _audit(
    db: Session,
    principal: Principal,
    context: ClientContext,
    item: WebAnnouncement,
    action: str,
) -> None:
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action=action,
        target_type="web_announcement",
        target_id=item.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"title": item.title, "revision": item.revision, "status": item.status.value},
    )
