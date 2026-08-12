from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityNotification,
    CommunityNotificationKind,
    CommunityNotificationPreference,
    CommunityNotificationSource,
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
) -> CommunityNotification | None:
    if recipient_id == actor_id or not notification_enabled(db, recipient_id, kind):
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


def notification_enabled(
    db: Session, recipient_id: str, kind: CommunityNotificationKind
) -> bool:
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
