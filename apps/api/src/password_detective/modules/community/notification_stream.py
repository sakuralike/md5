from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from password_detective.db.models.community import (
    CommunityContentStatus,
    CommunityNotification,
    CommunityNotificationOutbox,
    CommunityNotificationOutboxStatus,
    CommunityPost,
)
from password_detective.db.models.user import User
from password_detective.modules.community.group_service import post_visibility_condition
from password_detective.modules.community.notification_service import (
    in_app_notification_visibility_condition,
)
from password_detective.modules.community.schemas import (
    CommunityAuthor,
    CommunityNotificationResponse,
    CommunityNotificationStreamEvent,
)


@dataclass(frozen=True)
class NotificationEventBatch:
    items: list[CommunityNotificationStreamEvent]
    last_event_id: str | None


def latest_delivered_event_id(db: Session, recipient_id: str) -> str | None:
    return db.scalar(
        select(CommunityNotificationOutbox.id)
        .join(
            CommunityNotification,
            CommunityNotification.id == CommunityNotificationOutbox.notification_id,
        )
        .where(
            CommunityNotificationOutbox.recipient_id == recipient_id,
            CommunityNotificationOutbox.status == CommunityNotificationOutboxStatus.DELIVERED,
            CommunityNotification.recipient_id == recipient_id,
            _notification_visibility_condition(recipient_id),
            in_app_notification_visibility_condition(recipient_id),
        )
        .order_by(
            CommunityNotificationOutbox.created_at.desc(),
            CommunityNotificationOutbox.id.desc(),
        )
        .limit(1)
    )


def list_delivered_events(
    db: Session,
    *,
    recipient_id: str,
    after_event_id: str | None,
    limit: int = 20,
) -> NotificationEventBatch:
    conditions = [
        CommunityNotificationOutbox.recipient_id == recipient_id,
        CommunityNotificationOutbox.status == CommunityNotificationOutboxStatus.DELIVERED,
        CommunityNotification.recipient_id == recipient_id,
        _notification_visibility_condition(recipient_id),
        in_app_notification_visibility_condition(recipient_id),
    ]
    if after_event_id:
        cursor = db.get(CommunityNotificationOutbox, after_event_id)
        if cursor is None or cursor.recipient_id != recipient_id:
            return NotificationEventBatch(
                items=[],
                last_event_id=latest_delivered_event_id(db, recipient_id),
            )
        conditions.append(
            or_(
                CommunityNotificationOutbox.created_at > cursor.created_at,
                (CommunityNotificationOutbox.created_at == cursor.created_at)
                & (CommunityNotificationOutbox.id > cursor.id),
            )
        )
    rows = db.execute(
        select(CommunityNotificationOutbox, CommunityNotification)
        .join(
            CommunityNotification,
            CommunityNotification.id == CommunityNotificationOutbox.notification_id,
        )
        .where(*conditions)
        .order_by(
            CommunityNotificationOutbox.created_at,
            CommunityNotificationOutbox.id,
        )
        .limit(limit)
    ).all()
    actors = _load_authors(db, [notification.actor_id for _, notification in rows])
    unread_count = unread_notification_count(db, recipient_id)
    items = [
        CommunityNotificationStreamEvent(
            event_id=event.id,
            notification=_notification_response(notification, actors[notification.actor_id]),
            unread_count=unread_count,
        )
        for event, notification in rows
        if notification.actor_id in actors
    ]
    last_event_id = items[-1].event_id if items else after_event_id
    return NotificationEventBatch(items=items, last_event_id=last_event_id)


def _load_authors(db: Session, user_ids: list[str]) -> dict[str, CommunityAuthor]:
    if not user_ids:
        return {}
    users = db.scalars(select(User).where(User.id.in_(set(user_ids)))).all()
    return {
        user.id: CommunityAuthor(user_id=user.id, username=user.username, role=user.role)
        for user in users
    }


def _notification_response(
    notification: CommunityNotification,
    actor: CommunityAuthor,
) -> CommunityNotificationResponse:
    return CommunityNotificationResponse(
        id=notification.id,
        kind=notification.kind,
        source_type=notification.source_type,
        source_id=notification.source_id,
        post_id=notification.post_id,
        comment_id=notification.comment_id,
        preview=notification.preview,
        actor=actor,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


def _notification_visibility_condition(user_id: str):
    visible_post_ids = select(CommunityPost.id).where(
        CommunityPost.status == CommunityContentStatus.PUBLISHED,
        post_visibility_condition(user_id),
    )
    return or_(
        CommunityNotification.post_id.is_(None),
        CommunityNotification.post_id.in_(visible_post_ids),
    )


def unread_notification_count(db: Session, user_id: str) -> int:
    return (
        db.scalar(
            select(func.count(CommunityNotification.id)).where(
                CommunityNotification.recipient_id == user_id,
                CommunityNotification.read_at.is_(None),
                _notification_visibility_condition(user_id),
                in_app_notification_visibility_condition(user_id),
            )
        )
        or 0
    )
