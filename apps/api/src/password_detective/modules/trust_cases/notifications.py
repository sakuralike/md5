from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from password_detective.core.errors import AppError
from password_detective.core.notifications import NotificationGateway
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.trust_case import (
    TrustCase,
    TrustCaseEvent,
    TrustCaseNotification,
    TrustCaseNotificationKind,
    TrustCaseNotificationStatus,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.trust_cases.schemas import (
    TrustCaseNotificationListResponse,
    TrustCaseNotificationReplayRequest,
    TrustCaseNotificationResponse,
)

MAX_TRUST_CASE_NOTIFICATION_ATTEMPTS = 3


def queue_resolution_notification(
    db: Session, *, case: TrustCase, event: TrustCaseEvent
) -> TrustCaseNotification:
    dedupe_key = f"{case.id}:resolution:{event.id}:{case.reporter_id}"
    existing = db.scalar(
        select(TrustCaseNotification).where(TrustCaseNotification.dedupe_key == dedupe_key)
    )
    if existing is not None:
        return existing
    notification = TrustCaseNotification(
        case_id=case.id,
        event_id=event.id,
        recipient_user_id=case.reporter_id,
        kind=TrustCaseNotificationKind.RESOLUTION,
        status=TrustCaseNotificationStatus.PENDING,
        dedupe_key=dedupe_key,
        attempts=0,
        available_at=utc_now(),
        replay_count=0,
    )
    db.add(notification)
    db.flush()
    return notification


def dispatch_pending_case_notifications(
    db: Session,
    gateway: NotificationGateway,
    *,
    now: datetime | None = None,
    batch_size: int = 50,
) -> dict[str, int]:
    observed_at = _as_utc(now or utc_now())
    notifications = list(
        db.scalars(
            select(TrustCaseNotification)
            .options(
                selectinload(TrustCaseNotification.case),
                selectinload(TrustCaseNotification.recipient),
            )
            .where(
                TrustCaseNotification.status == TrustCaseNotificationStatus.PENDING,
                TrustCaseNotification.available_at <= observed_at,
            )
            .order_by(TrustCaseNotification.created_at, TrustCaseNotification.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
    )
    sent = 0
    failed = 0
    for notification in notifications:
        notification.attempts += 1
        notification.provider = gateway.provider_name
        notification.updated_at = observed_at
        try:
            case = notification.case
            recipient = notification.recipient
            provider_message_id = gateway.send_trust_case_result(
                delivery_id=notification.id,
                recipient=recipient.email,
                case_id=case.id,
                case_kind=case.kind.value,
                case_status=case.status.value,
                resolution_code=case.resolution_code or "unknown",
            )
        except Exception as exc:
            notification.last_error_code = type(exc).__name__[:128]
            if notification.attempts >= MAX_TRUST_CASE_NOTIFICATION_ATTEMPTS:
                notification.status = TrustCaseNotificationStatus.FAILED
                notification.failed_at = observed_at
                failed += 1
            else:
                notification.available_at = observed_at + timedelta(
                    minutes=2 ** notification.attempts
                )
        else:
            notification.status = TrustCaseNotificationStatus.SENT
            notification.provider_message_id = provider_message_id
            notification.sent_at = observed_at
            notification.failed_at = None
            notification.last_error_code = None
            sent += 1
    db.commit()
    return {"processed": len(notifications), "sent": sent, "failed": failed}


def list_case_notifications(
    db: Session,
    *,
    status: TrustCaseNotificationStatus | None,
    page: int,
    page_size: int,
) -> TrustCaseNotificationListResponse:
    filters = []
    if status is not None:
        filters.append(TrustCaseNotification.status == status)
    total = db.scalar(select(func.count(TrustCaseNotification.id)).where(*filters)) or 0
    rows = list(
        db.scalars(
            select(TrustCaseNotification)
            .where(*filters)
            .order_by(TrustCaseNotification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return TrustCaseNotificationListResponse(
        items=[notification_response(item) for item in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def replay_case_notification(
    db: Session,
    *,
    notification_id: str,
    payload: TrustCaseNotificationReplayRequest,
    principal: Principal,
    context: ClientContext,
) -> TrustCaseNotificationResponse:
    notification = db.scalar(
        select(TrustCaseNotification)
        .where(TrustCaseNotification.id == notification_id)
        .with_for_update()
    )
    if notification is None:
        raise AppError(
            "trust.notification_not_found", "未找到案件结果通知", status_code=404
        )
    now = utc_now()
    notification.status = TrustCaseNotificationStatus.PENDING
    notification.attempts = 0
    notification.available_at = now
    notification.sent_at = None
    notification.failed_at = None
    notification.last_error_code = None
    notification.provider_message_id = None
    notification.replay_count += 1
    notification.last_replayed_at = now
    notification.last_replayed_by_id = principal.user.id
    notification.updated_at = now
    write_audit_log(
        db,
        action="trust_case.notification.replay",
        target_type="trust_case_notification",
        target_id=notification.id,
        result="success",
        actor_id=principal.user.id,
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "case_id": notification.case_id,
            "recipient_user_id": notification.recipient_user_id,
            "replay_count": notification.replay_count,
            "reason_code": payload.reason_code,
            "has_note": payload.note is not None,
        },
    )
    db.commit()
    db.refresh(notification)
    return notification_response(notification)


def notification_response(
    notification: TrustCaseNotification,
) -> TrustCaseNotificationResponse:
    return TrustCaseNotificationResponse(
        id=notification.id,
        case_id=notification.case_id,
        recipient_user_id=notification.recipient_user_id,
        kind=notification.kind,
        status=notification.status,
        attempts=notification.attempts,
        provider=notification.provider,
        provider_message_id=notification.provider_message_id,
        available_at=notification.available_at,
        sent_at=notification.sent_at,
        failed_at=notification.failed_at,
        last_error_code=notification.last_error_code,
        replay_count=notification.replay_count,
        last_replayed_at=notification.last_replayed_at,
        last_replayed_by_id=notification.last_replayed_by_id,
        created_at=notification.created_at,
        updated_at=notification.updated_at,
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
