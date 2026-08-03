from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from password_detective.core.config import Settings

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
    provider_name: str

    def send_account_token(self, *, kind: str, recipient: str, token: str) -> str | None: ...

    def send_risk_alert(
        self,
        *,
        delivery_id: str,
        kind: str,
        recipient: str,
        alert_id: str,
        severity: str,
        due_at: datetime | None,
    ) -> str | None: ...


class MemoryNotificationGateway:
    """Only for local development and tests; messages are never logged."""

    provider_name = "memory"

    def __init__(self) -> None:
        self.messages: list[DeliveredNotification] = []
        self.risk_alert_messages: list[DeliveredRiskAlertNotification] = []

    def send_account_token(self, *, kind: str, recipient: str, token: str) -> str | None:
        self.messages.append(DeliveredNotification(kind=kind, recipient=recipient, token=token))
        return None

    def send_risk_alert(
        self,
        *,
        delivery_id: str,
        kind: str,
        recipient: str,
        alert_id: str,
        severity: str,
        due_at: datetime | None,
    ) -> str | None:
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
        return None

    def latest_token(self, *, kind: str, recipient: str) -> str:
        for message in reversed(self.messages):
            if message.kind == kind and message.recipient == recipient:
                return message.token
        raise LookupError(f"未找到 {kind} 通知")


class LoggingNotificationGateway:
    """Non-production sink that confirms delivery without logging recipient addresses or secrets."""

    provider_name = "log"

    def send_account_token(self, *, kind: str, recipient: str, token: str) -> str | None:
        logger.info(
            "account_notification_accepted_by_log_sink",
            extra={"event": "account_notification_delivered", "kind": kind},
        )
        return None

    def send_risk_alert(
        self,
        *,
        delivery_id: str,
        kind: str,
        recipient: str,
        alert_id: str,
        severity: str,
        due_at: datetime | None,
    ) -> str | None:
        logger.info(
            "risk_alert_notification_accepted_by_log_sink",
            extra={
                "event": "risk_alert_notification_delivered",
                "kind": kind,
                "alert_id": alert_id,
                "severity": severity,
                "has_deadline": due_at is not None,
            },
        )
        return None


class WebhookNotificationGateway:
    """Signed HTTPS provider adapter. Recipient addresses are used only in the outbound request."""

    provider_name = "webhook"

    def __init__(
        self,
        *,
        url: str,
        secret: str,
        timeout_seconds: float = 10.0,
        opener: Any = urlopen,
    ) -> None:
        self._url = url
        self._secret = secret.encode("utf-8")
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def send_account_token(self, *, kind: str, recipient: str, token: str) -> str | None:
        return self._send(
            {
                "version": "notification-webhook-v1",
                "type": "account_token",
                "kind": kind,
                "recipient": recipient,
                "token": token,
            }
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
    ) -> str | None:
        return self._send(
            {
                "version": "notification-webhook-v1",
                "type": "risk_alert",
                "delivery_id": delivery_id,
                "kind": kind,
                "recipient": recipient,
                "alert_id": alert_id,
                "severity": severity,
                "due_at": _isoformat_utc(due_at),
            }
        )

    def _send(self, payload: dict[str, Any]) -> str | None:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        body = serialized.encode("utf-8")
        timestamp = str(int(datetime.now(UTC).timestamp()))
        signature = hmac.new(
            self._secret,
            timestamp.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        request = Request(
            self._url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "password-detective-notification-worker/1",
                "X-Password-Detective-Timestamp": timestamp,
                "X-Password-Detective-Signature": f"sha256={signature}",
            },
        )
        with self._opener(request, timeout=self._timeout_seconds) as response:
            status = getattr(response, "status", 200)
            if status < 200 or status >= 300:
                raise RuntimeError("notification_webhook_rejected")
            return response.headers.get("X-Provider-Message-Id")


def _isoformat_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized.isoformat()


def build_notification_gateway(settings: Settings) -> NotificationGateway:
    if settings.notification_backend == "memory":
        return MemoryNotificationGateway()
    if settings.notification_backend == "log":
        return LoggingNotificationGateway()
    return WebhookNotificationGateway(
        url=settings.notification_webhook_url,
        secret=settings.notification_webhook_secret,
        timeout_seconds=settings.notification_webhook_timeout_seconds,
    )
