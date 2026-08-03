from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from password_detective.core.notifications import NotificationGateway
from password_detective.core.time import utc_now
from password_detective.db.models.risk_alert import (
    RiskAlert,
    RiskAlertEvent,
    RiskAlertNotification,
    RiskAlertNotificationKind,
    RiskAlertNotificationStatus,
    RiskAlertStatus,
)
from password_detective.db.models.user import User, UserRole, UserStatus


@dataclass(frozen=True)
class RiskAlertSlaRule:
    version: str = "risk-alert-sla-v1"
    acknowledge_minutes: int = 15
    resolve_minutes: int = 240


ACTIVE_RISK_ALERT_SLA_RULE = RiskAlertSlaRule()
MAX_NOTIFICATION_ATTEMPTS = 3


def eligible_operator_query():
    return select(User).where(
        User.status == UserStatus.ACTIVE,
        User.role.in_([UserRole.MODERATOR, UserRole.ADMIN]),
        User.totp_enabled_at.is_not(None),
    )


def eligible_operator_ids(db: Session) -> list[str]:
    return list(db.scalars(eligible_operator_query().with_only_columns(User.id)))


def queue_risk_alert_notifications(
    db: Session,
    *,
    alert: RiskAlert,
    event: RiskAlertEvent | None,
    kind: RiskAlertNotificationKind,
    recipient_ids: list[str] | None = None,
) -> int:
    recipients = recipient_ids if recipient_ids is not None else eligible_operator_ids(db)
    queued = 0
    event_key = event.id if event is not None else "sla"
    for recipient_id in sorted(set(recipients)):
        dedupe_key = f"{alert.id}:{kind.value}:{event_key}:{recipient_id}"
        exists = db.scalar(
            select(RiskAlertNotification.id).where(RiskAlertNotification.dedupe_key == dedupe_key)
        )
        if exists is not None:
            continue
        db.add(
            RiskAlertNotification(
                alert_id=alert.id,
                event_id=event.id if event is not None else None,
                recipient_user_id=recipient_id,
                kind=kind,
                status=RiskAlertNotificationStatus.PENDING,
                dedupe_key=dedupe_key,
                attempts=0,
                available_at=utc_now(),
            )
        )
        queued += 1
    if queued:
        db.flush()
    return queued


def queue_due_sla_notifications(db: Session, *, now: datetime | None = None) -> int:
    observed_at = _as_utc(now or utc_now())
    alerts = list(
        db.scalars(
            select(RiskAlert).where(
                RiskAlert.status.in_([RiskAlertStatus.OPEN, RiskAlertStatus.ACKNOWLEDGED])
            )
        )
    )
    queued = 0
    for alert in alerts:
        if alert.status == RiskAlertStatus.OPEN and _as_utc(alert.acknowledge_due_at) < observed_at:
            recipients = [alert.assigned_to_id] if alert.assigned_to_id else None
            queued += queue_risk_alert_notifications(
                db,
                alert=alert,
                event=None,
                kind=RiskAlertNotificationKind.ACKNOWLEDGEMENT_OVERDUE,
                recipient_ids=recipients,
            )
        elif (
            alert.status == RiskAlertStatus.ACKNOWLEDGED
            and _as_utc(alert.resolve_due_at) < observed_at
        ):
            recipients = [alert.assigned_to_id] if alert.assigned_to_id else None
            queued += queue_risk_alert_notifications(
                db,
                alert=alert,
                event=None,
                kind=RiskAlertNotificationKind.RESOLUTION_OVERDUE,
                recipient_ids=recipients,
            )
    db.commit()
    return queued


def dispatch_pending_notifications(
    db: Session,
    gateway: NotificationGateway,
    *,
    now: datetime | None = None,
    batch_size: int = 50,
) -> dict[str, int]:
    observed_at = _as_utc(now or utc_now())
    notifications = list(
        db.scalars(
            select(RiskAlertNotification)
            .options(
                selectinload(RiskAlertNotification.alert),
                selectinload(RiskAlertNotification.recipient),
            )
            .where(
                RiskAlertNotification.status == RiskAlertNotificationStatus.PENDING,
                RiskAlertNotification.available_at <= observed_at,
            )
            .order_by(RiskAlertNotification.created_at, RiskAlertNotification.id)
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
            provider_message_id = gateway.send_risk_alert(
                delivery_id=notification.id,
                kind=notification.kind.value,
                recipient=notification.recipient.email,
                alert_id=notification.alert_id,
                severity=notification.alert.severity.value,
                due_at=_notification_due_at(notification),
            )
        except Exception as exc:  # provider failures are converted to bounded retries
            failed += 1
            notification.last_error_code = type(exc).__name__[:128]
            notification.provider_message_id = None
            notification.sent_at = None
            if notification.attempts >= MAX_NOTIFICATION_ATTEMPTS:
                notification.status = RiskAlertNotificationStatus.FAILED
                notification.failed_at = observed_at
            else:
                notification.failed_at = None
                notification.available_at = observed_at + timedelta(
                    minutes=2 ** (notification.attempts - 1)
                )
        else:
            sent += 1
            notification.status = RiskAlertNotificationStatus.SENT
            notification.provider_message_id = provider_message_id
            notification.sent_at = observed_at
            notification.failed_at = None
            notification.last_error_code = None
    db.commit()
    return {"selected": len(notifications), "sent": sent, "failed": failed}


def _notification_due_at(notification: RiskAlertNotification) -> datetime | None:
    if notification.kind in {
        RiskAlertNotificationKind.DETECTED,
        RiskAlertNotificationKind.ACKNOWLEDGEMENT_OVERDUE,
        RiskAlertNotificationKind.REOPENED,
    }:
        return notification.alert.acknowledge_due_at
    if notification.kind in {
        RiskAlertNotificationKind.ASSIGNED,
        RiskAlertNotificationKind.RESOLUTION_OVERDUE,
    }:
        return notification.alert.resolve_due_at
    return None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
