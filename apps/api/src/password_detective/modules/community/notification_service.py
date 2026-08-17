from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from password_detective.core.config import get_settings
from password_detective.core.notifications import (
    CommunityNotificationDigestEmailItem,
    NotificationGateway,
)
from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityContentStatus,
    CommunityNotification,
    CommunityNotificationEmailDigest,
    CommunityNotificationEmailDigestItem,
    CommunityNotificationEmailDigestStatus,
    CommunityNotificationKind,
    CommunityNotificationOutbox,
    CommunityNotificationOutboxStatus,
    CommunityNotificationPreference,
    CommunityNotificationSource,
    CommunityPost,
    CommunityUserBlock,
)
from password_detective.db.models.user import User


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
    in_app_enabled, email_digest_enabled = notification_channels(db, recipient_id, kind)
    if not (in_app_enabled or email_digest_enabled) and not create_when_disabled:
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
            if queue_event and in_app_enabled:
                queue_notification_event(db, existing)
            if email_digest_enabled:
                queue_email_digest_item(db, existing)
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
    if queue_event and in_app_enabled:
        queue_notification_event(db, notification)
    if email_digest_enabled:
        queue_email_digest_item(db, notification)
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
        in_app_enabled, email_digest_enabled = notification_channels(
            db, recipient_id, CommunityNotificationKind.LIKE_SUMMARY
        )
        if refresh_unread and not (in_app_enabled or email_digest_enabled):
            return
        existing.actor_id = actor_id
        existing.preview = notification_preview(rendered_preview)
        if refresh_unread:
            existing.read_at = None
            existing.created_at = utc_now()
            existing.delivery_version += 1
            if in_app_enabled:
                queue_notification_event(db, existing)
            if email_digest_enabled:
                queue_email_digest_item(db, existing)
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


def notification_channels(
    db: Session, recipient_id: str, kind: CommunityNotificationKind
) -> tuple[bool, bool]:
    preference = db.scalar(
        select(CommunityNotificationPreference).where(
            CommunityNotificationPreference.user_id == recipient_id,
            CommunityNotificationPreference.kind == kind,
        )
    )
    if preference is None:
        return True, False
    return preference.in_app_enabled, preference.email_digest_enabled


def notification_enabled(db: Session, recipient_id: str, kind: CommunityNotificationKind) -> bool:
    return notification_channels(db, recipient_id, kind)[0]


def email_digest_enabled(db: Session, recipient_id: str, kind: CommunityNotificationKind) -> bool:
    return notification_channels(db, recipient_id, kind)[1]


def _digest_window(now: datetime) -> tuple[datetime, datetime]:
    minutes = get_settings().community_notification_digest_window_minutes
    normalized = now.astimezone(UTC).replace(second=0, microsecond=0)
    started = normalized - timedelta(minutes=normalized.minute % minutes)
    return started, started + timedelta(minutes=minutes)


def queue_email_digest_item(
    db: Session, notification: CommunityNotification
) -> CommunityNotificationEmailDigestItem:
    window_started_at, window_ends_at = _digest_window(utc_now())
    digest = db.scalar(
        select(CommunityNotificationEmailDigest).where(
            CommunityNotificationEmailDigest.recipient_id == notification.recipient_id,
            CommunityNotificationEmailDigest.window_started_at == window_started_at,
        )
    )
    if digest is None:
        digest = CommunityNotificationEmailDigest(
            recipient_id=notification.recipient_id,
            dedupe_key=f"community-email-digest:{notification.recipient_id}:{window_started_at.isoformat()}",
            window_started_at=window_started_at,
            window_ends_at=window_ends_at,
            available_at=window_ends_at,
        )
        db.add(digest)
        db.flush()
    item = db.scalar(
        select(CommunityNotificationEmailDigestItem).where(
            CommunityNotificationEmailDigestItem.digest_id == digest.id,
            CommunityNotificationEmailDigestItem.notification_id == notification.id,
            CommunityNotificationEmailDigestItem.delivery_version == notification.delivery_version,
        )
    )
    if item is None:
        item = CommunityNotificationEmailDigestItem(
            digest_id=digest.id,
            notification_id=notification.id,
            delivery_version=notification.delivery_version,
        )
        db.add(item)
    return item


def in_app_notification_visibility_condition(user_id: str):
    return (
        ~select(CommunityNotificationPreference.id)
        .where(
            CommunityNotificationPreference.user_id == user_id,
            CommunityNotificationPreference.kind == CommunityNotification.kind,
            CommunityNotificationPreference.in_app_enabled.is_(False),
        )
        .exists()
    )


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


def dispatch_pending_email_digests(
    db: Session, gateway: NotificationGateway, *, limit: int = 100
) -> dict[str, int]:
    now = utc_now()
    digests = db.scalars(
        select(CommunityNotificationEmailDigest)
        .where(
            CommunityNotificationEmailDigest.status
            == CommunityNotificationEmailDigestStatus.PENDING,
            CommunityNotificationEmailDigest.window_ends_at <= now,
            CommunityNotificationEmailDigest.available_at <= now,
        )
        .order_by(
            CommunityNotificationEmailDigest.available_at,
            CommunityNotificationEmailDigest.created_at,
            CommunityNotificationEmailDigest.id,
        )
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    sent = failed = retried = suppressed = 0
    for digest in digests:
        digest.attempts += 1
        try:
            recipient = db.get(User, digest.recipient_id)
            items = db.scalars(
                select(CommunityNotificationEmailDigestItem).where(
                    CommunityNotificationEmailDigestItem.digest_id == digest.id
                )
            ).all()
            deliverable: list[CommunityNotificationDigestEmailItem] = []
            for item in items:
                notification = db.get(CommunityNotification, item.notification_id)
                if notification is None or notification.delivery_version != item.delivery_version:
                    continue
                if not email_digest_enabled(db, digest.recipient_id, notification.kind):
                    continue
                if not _notification_still_deliverable(db, notification):
                    continue
                deliverable.append(
                    CommunityNotificationDigestEmailItem(
                        kind=notification.kind.value,
                        preview=notification.preview,
                    )
                )
            if recipient is None or not recipient.email or not deliverable:
                digest.status = CommunityNotificationEmailDigestStatus.SUPPRESSED
                digest.suppressed_at = now
                digest.last_error_code = "community.email_digest_no_deliverable_items"
                suppressed += 1
                continue
            digest.provider_message_id = gateway.send_community_notification_digest(
                digest_id=digest.dedupe_key,
                recipient=recipient.email,
                window_started_at=digest.window_started_at,
                window_ends_at=digest.window_ends_at,
                items=deliverable,
            )
            digest.provider_name = gateway.provider_name
            digest.status = CommunityNotificationEmailDigestStatus.SENT
            digest.sent_at = now
            digest.failed_at = None
            digest.last_error_code = None
            sent += 1
        except Exception:
            if digest.attempts >= 5:
                digest.status = CommunityNotificationEmailDigestStatus.FAILED
                digest.failed_at = now
                digest.last_error_code = "community.email_digest_dispatch_failed"
                failed += 1
            else:
                digest.available_at = now + timedelta(minutes=2**digest.attempts)
                digest.last_error_code = "community.email_digest_dispatch_retry"
                retried += 1
    db.commit()
    return {
        "processed": len(digests),
        "sent": sent,
        "retried": retried,
        "failed": failed,
        "suppressed": suppressed,
    }


def _notification_still_deliverable(db: Session, notification: CommunityNotification) -> bool:
    if notification.kind not in {
        CommunityNotificationKind.GROUP_DECISION,
        CommunityNotificationKind.GROUP_ROLE_CHANGE,
    } and users_block_each_other(
        db, actor_id=notification.actor_id, target_id=notification.recipient_id
    ):
        return False
    if notification.post_id is None:
        return True
    from password_detective.modules.community.group_service import can_user_view_post

    post = db.get(CommunityPost, notification.post_id)
    return (
        post is not None
        and post.status == CommunityContentStatus.PUBLISHED
        and can_user_view_post(db, post, notification.recipient_id)
    )


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
