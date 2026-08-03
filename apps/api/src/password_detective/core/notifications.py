from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveredNotification:
    kind: str
    recipient: str
    token: str


@dataclass(frozen=True)
class DeliveredRiskAlertNotification:
    delivery_id: str
    kind: str
    recipient: str
    alert_id: str
    severity: str
    due_at: datetime | None


class NotificationGateway(Protocol):
    def send_account_token(self, *, kind: str, recipient: str, token: str) -> None: ...

    def send_risk_alert(
        self,
        *,
        delivery_id: str,
        kind: str,
        recipient: str,
        alert_id: str,
        severity: str,
        due_at: datetime | None,
    ) -> None: ...


class MemoryNotificationGateway:
    """Only for local development and tests; messages are never logged."""

    def __init__(self) -> None:
        self.messages: list[DeliveredNotification] = []
        self.risk_alert_messages: list[DeliveredRiskAlertNotification] = []

    def send_account_token(self, *, kind: str, recipient: str, token: str) -> None:
        self.messages.append(DeliveredNotification(kind=kind, recipient=recipient, token=token))

    def send_risk_alert(
        self,
        *,
        delivery_id: str,
        kind: str,
        recipient: str,
        alert_id: str,
        severity: str,
        due_at: datetime | None,
    ) -> None:
        self.risk_alert_messages.append(
            DeliveredRiskAlertNotification(
                delivery_id=delivery_id,
                kind=kind,
                recipient=recipient,
                alert_id=alert_id,
                severity=severity,
                due_at=due_at,
            )
        )

    def latest_token(self, *, kind: str, recipient: str) -> str:
        for message in reversed(self.messages):
            if message.kind == kind and message.recipient == recipient:
                return message.token
        raise LookupError(f"未找到 {kind} 通知")


class LoggingNotificationGateway:
    """Provider placeholder that never writes tokens or recipient addresses to logs."""

    def send_account_token(self, *, kind: str, recipient: str, token: str) -> None:
        logger.info(
            "account_notification_queued_without_provider",
            extra={"event": "account_notification_pending", "kind": kind},
        )

    def send_risk_alert(
        self,
        *,
        delivery_id: str,
        kind: str,
        recipient: str,
        alert_id: str,
        severity: str,
        due_at: datetime | None,
    ) -> None:
        logger.info(
            "risk_alert_notification_queued_without_provider",
            extra={
                "event": "risk_alert_notification_pending",
                "kind": kind,
                "alert_id": alert_id,
                "severity": severity,
                "has_deadline": due_at is not None,
            },
        )
