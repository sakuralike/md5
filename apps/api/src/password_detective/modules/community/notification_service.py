from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityContentStatus,
    CommunityNotification,
    CommunityNotificationKind,
    CommunityNotificationOutbox,
    CommunityNotificationOutboxStatus,
    CommunityNotificationPreference,
    CommunityNotificationSource,
    CommunityPost,
    CommunityUserBlock,
)


def create_notification(
    db: Session,
    *,
    recipient_id: str,
    actor_id: str,
    kind: CommunityNotificationKind,
    source_type: CommunityNotificationSource,
    source_id: str,
    post_id: str | None,
    comment_id: str | None,
    preview: str,
    refresh_existing: bool = False,
    queue_event: bool = True,
    create_when_disabled: bool = False,
) -> CommunityNotification | None:
    if recipient_id == actor_id:
        return None
    enabled = notification_enabled(db, recipient_id, kind)
    if not enabled and not create_when_disabled:
        return None
    if kind not in {
        CommunityNotificationKind.GROUP_DECISION,
        CommunityNotificationKind.GROUP_ROLE_CHANGE,
    } and users_block_each_other(db, actor_id=actor_id, target_id=recipient_id):
        return None
    existing = db.scalar(
        select(CommunityNotification).where(
            CommunityNotification.recipient_id == recipient_id,
            CommunityNotification.kind == kind,
            CommunityNotification.source_type == source_type,
            CommunityNotification.source_id == source_id,
        )
    )
    if existing is not None:
        if refresh_existing:
            existing.actor_id = actor_id
            existing.post_id = post_id
            existing.comment_id = comment_id
            existing.preview = notification_preview(preview)
            existing.read_at = None
            existing.created_at = utc_now()
            existing.delivery_version += 1
            if queue_event and enabled:
                queue_notification_event(db, existing)
        return existing
    notification = CommunityNotification(
        recipient_id=recipient_id,
        actor_id=actor_id,
        kind=kind,
        source_type=source_type,
        source_id=source_id,
        post_id=post_id,
        comment_id=comment_id,
        preview=notification_preview(preview),
    )
    db.add(notification)
    db.flush()
    if queue_event and enabled:
        queue_notification_event(db, notification)
    return notification

def sync_like_summary(
    db: Session,
    *,
    recipient_id: str,
    actor_id: str,
    source_type: CommunityNotificationSource,
    source_id: str,
    post_id: str,
    comment_id: str | None,
    like_count: int,
    preview: str,
    refresh_unread: bool,
    create_if_missing: bool,
) -> None:
    existing = db.scalar(
        select(CommunityNotification).where(
            CommunityNotification.recipient_id == recipient_id,
            CommunityNotification.kind == CommunityNotificationKind.LIKE_SUMMARY,
            CommunityNotification.source_type == source_type,
            CommunityNotification.source_id == source_id,
        )
    )
    if like_count <= 0:
        if existing is not None:
            db.delete(existing)
        return
    rendered_preview = f"{preview}（共 {like_count} 个赞）"
    if existing is not None:
        if refresh_unread and not notification_enabled(
            db, recipient_id, CommunityNotificationKind.LIKE_SUMMARY
        ):
            return
        existing.actor_id = actor_id
        existing.preview = notification_preview(rendered_preview)
        if refresh_unread:
            existing.read_at = None
            existing.created_at = utc_now()
            existing.delivery_version += 1
            queue_notification_event(db, existing)
        return
    if not create_if_missing:
        return
    create_notification(
        db,
        recipient_id=recipient_id,
        actor_id=actor_id,
        kind=CommunityNotificationKind.LIKE_SUMMARY,
        source_type=source_type,
        source_id=source_id,
        post_id=post_id,
        comment_id=comment_id,
        preview=rendered_preview,
    )


def notification_enabled(db: Session, recipient_id: str, kind: CommunityNotificationKind) -> bool:
    preference = db.scalar(
        select(CommunityNotificationPreference).where(
            CommunityNotificationPreference.user_id == recipient_id,
            CommunityNotificationPreference.kind == kind,
        )
    )
    return preference is None or preference.in_app_enabled


def users_block_each_other(db: Session, *, actor_id: str, target_id: str) -> bool:
    return (
        db.scalar(
            select(CommunityUserBlock.id).where(
                or_(
                    (CommunityUserBlock.blocker_id == actor_id)
                    & (CommunityUserBlock.blocked_id == target_id),
                    (CommunityUserBlock.blocker_id == target_id)
                    & (CommunityUserBlock.blocked_id == actor_id),
                )
            )
        )
        is not None
    )


def notification_preview(text: str) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= 180 else f"{compact[:177]}..."


def queue_notification_event(
    db: Session, notification: CommunityNotification
) -> CommunityNotificationOutbox:
    event = CommunityNotificationOutbox(
        notification_id=notification.id,
        recipient_id=notification.recipient_id,
        dedupe_key=(f"community-notification:{notification.id}:v{notification.delivery_version}"),
    )
    db.add(event)
    return event


def dispatch_pending_notification_events(db: Session, *, limit: int = 100) -> dict[str, int]:
    now = utc_now()
    events = db.scalars(
        select(CommunityNotificationOutbox)
        .where(
            CommunityNotificationOutbox.status == CommunityNotificationOutboxStatus.PENDING,
            CommunityNotificationOutbox.available_at <= now,
        )
        .order_by(
            CommunityNotificationOutbox.available_at,
            CommunityNotificationOutbox.created_at,
            CommunityNotificationOutbox.id,
        )
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    delivered = 0
    failed = 0
    retried = 0
    for event in events:
        event.attempts += 1
        try:
            notification = db.get(CommunityNotification, event.notification_id)
            if notification is None or notification.recipient_id != event.recipient_id:
                event.status = CommunityNotificationOutboxStatus.FAILED
                event.failed_at = now
                event.last_error_code = "community.notification_missing"
                failed += 1
                continue
            if not notification_enabled(db, event.recipient_id, notification.kind):
                event.status = CommunityNotificationOutboxStatus.FAILED
                event.failed_at = now
                event.last_error_code = "community.notification_preference_disabled"
                failed += 1
                continue
            if notification.kind not in {
                CommunityNotificationKind.GROUP_DECISION,
                CommunityNotificationKind.GROUP_ROLE_CHANGE,
            } and users_block_each_other(
                db, actor_id=notification.actor_id, target_id=event.recipient_id
            ):
                event.status = CommunityNotificationOutboxStatus.FAILED
                event.failed_at = now
                event.last_error_code = "community.notification_visibility_revoked"
                failed += 1
                continue
            if notification.post_id is not None:
                from password_detective.modules.community.group_service import (
                    can_user_view_post,
                )

                post = db.get(CommunityPost, notification.post_id)
                if (
                    post is None
                    or post.status != CommunityContentStatus.PUBLISHED
                    or not can_user_view_post(db, post, event.recipient_id)
                ):
                    event.status = CommunityNotificationOutboxStatus.FAILED
                    event.failed_at = now
                    event.last_error_code = "community.notification_visibility_revoked"
                    failed += 1
                    continue
            event.status = CommunityNotificationOutboxStatus.DELIVERED
            event.delivered_at = now
            event.failed_at = None
            event.last_error_code = None
            delivered += 1
        except Exception:
            if event.attempts >= 5:
                event.status = CommunityNotificationOutboxStatus.FAILED
                event.failed_at = now
                event.last_error_code = "community.notification_dispatch_failed"
                failed += 1
            else:
                delay_seconds = min(60, 2**event.attempts)
                event.available_at = now + timedelta(seconds=delay_seconds)
                event.last_error_code = "community.notification_dispatch_retry"
                retried += 1
    db.commit()
    return {
        "processed": len(events),
        "delivered": delivered,
        "retried": retried,
        "failed": failed,
    }
