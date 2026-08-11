from __future__ import annotations

import hashlib
import hmac
import json
import logging
import smtplib
import ssl
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid
from typing import TYPE_CHECKING, Any, Literal, Protocol
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from password_detective.core.config import Settings

logger = logging.getLogger(__name__)

EMAIL_SUBJECT_PREFIX = "[密码侦探社]"
EMAIL_FOOTER_TEXT = "此信为系统邮件，请不要直接回复。"


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


@dataclass(frozen=True)
class DeliveredTrustCaseNotification:
    delivery_id: str
    recipient: str
    case_id: str
    case_kind: str
    case_status: str
    resolution_code: str


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

    def send_trust_case_result(
        self,
        *,
        delivery_id: str,
        recipient: str,
        case_id: str,
        case_kind: str,
        case_status: str,
        resolution_code: str,
    ) -> str | None: ...


class MemoryNotificationGateway:
    """Only for local development and tests; messages are never logged."""

    provider_name = "memory"

    def __init__(self) -> None:
        self.messages: list[DeliveredNotification] = []
        self.risk_alert_messages: list[DeliveredRiskAlertNotification] = []
        self.trust_case_messages: list[DeliveredTrustCaseNotification] = []

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

    def send_trust_case_result(
        self,
        *,
        delivery_id: str,
        recipient: str,
        case_id: str,
        case_kind: str,
        case_status: str,
        resolution_code: str,
    ) -> str | None:
        self.trust_case_messages.append(
            DeliveredTrustCaseNotification(
                delivery_id=delivery_id,
                recipient=recipient,
                case_id=case_id,
                case_kind=case_kind,
                case_status=case_status,
                resolution_code=resolution_code,
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

    def send_trust_case_result(
        self,
        *,
        delivery_id: str,
        recipient: str,
        case_id: str,
        case_kind: str,
        case_status: str,
        resolution_code: str,
    ) -> str | None:
        logger.info(
            "trust_case_notification_accepted_by_log_sink",
            extra={
                "event": "trust_case_notification_delivered",
                "case_id": case_id,
                "case_kind": case_kind,
                "case_status": case_status,
                "resolution_code": resolution_code,
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

    def send_trust_case_result(
        self,
        *,
        delivery_id: str,
        recipient: str,
        case_id: str,
        case_kind: str,
        case_status: str,
        resolution_code: str,
    ) -> str | None:
        return self._send(
            {
                "version": "notification-webhook-v1",
                "type": "trust_case_result",
                "delivery_id": delivery_id,
                "recipient": recipient,
                "case_id": case_id,
                "case_kind": case_kind,
                "case_status": case_status,
                "resolution_code": resolution_code,
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


class SMTPNotificationGateway:
    """SMTP adapter using plain-text messages and transport encryption when configured."""

    provider_name = "smtp"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        security: Literal["starttls", "ssl", "none"],
        username: str,
        password: str,
        sender_email: str,
        sender_name: str,
        timeout_seconds: float = 10.0,
        smtp_factory: Any | None = None,
        ssl_context_factory: Any = ssl.create_default_context,
    ) -> None:
        self._host = host
        self._port = port
        self._security = security
        self._username = username
        self._password = password
        self._sender_email = sender_email
        self._sender_name = sender_name
        self._timeout_seconds = timeout_seconds
        self._smtp_factory = smtp_factory
        self._ssl_context_factory = ssl_context_factory

    def send_account_token(self, *, kind: str, recipient: str, token: str) -> str | None:
        subject, content = _account_token_email(kind=kind, token=token)
        message = self._build_message(
            recipient=recipient,
            subject=subject,
            content=content,
            notification_type="account_token",
            message_key=kind,
        )
        return self._send_message(message=message, recipient=recipient)

    def send_test_email(self, *, recipient: str) -> str:
        message = self._build_message(
            recipient=recipient,
            subject=f"{EMAIL_SUBJECT_PREFIX} 邮件投递测试",
            content=(
                "这是一封由密码侦探社管理端发起的 SMTP 测试邮件。\n\n"
                "如果您收到此邮件，表示 SMTP 会话配置有效。\n"
                "服务器地址、端口、加密方式、认证凭据和发件人配置均已通过。\n\n"
                f"{EMAIL_FOOTER_TEXT}"
            ),
            notification_type="smtp_test",
            message_key=f"smtp-test-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        )
        return self._send_message(message=message, recipient=recipient)

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
        due_at_text = _isoformat_utc(due_at) or "未设置"
        message = self._build_message(
            recipient=recipient,
            subject=f"{EMAIL_SUBJECT_PREFIX} {severity.upper()} 风险告警",
            content=(
                "检测到需要管理员处理的风险告警。\n\n"
                f"告警编号：{alert_id}\n"
                f"通知类型：{kind}\n"
                f"严重级别：{severity}\n"
                f"处理时限：{due_at_text}\n\n"
                "请登录管理端核查并处置。为保护敏感信息，邮件不包含候选密码、"
                "证据原文或用户凭据。"
            ),
            notification_type="risk_alert",
            message_key=delivery_id,
            extra_headers={"X-Password-Detective-Delivery-ID": delivery_id},
        )
        return self._send_message(message=message, recipient=recipient)

    def send_trust_case_result(
        self,
        *,
        delivery_id: str,
        recipient: str,
        case_id: str,
        case_kind: str,
        case_status: str,
        resolution_code: str,
    ) -> str | None:
        message = self._build_message(
            recipient=recipient,
            subject=f"{EMAIL_SUBJECT_PREFIX} 举报与申诉处理结果",
            content=(
                "您的举报或申诉案件已有处理结果。\n\n"
                f"案件编号：{case_id}\n"
                f"案件类型：{case_kind}\n"
                f"案件状态：{case_status}\n"
                f"处理结果：{resolution_code}\n\n"
                "请登录密码侦探社查看案件时间线。为保护隐私，邮件不包含证据原文、"
                "处置备注、候选密码或用户凭据。"
            ),
            notification_type="trust_case_result",
            message_key=delivery_id,
            extra_headers={"X-Password-Detective-Delivery-ID": delivery_id},
        )
        return self._send_message(message=message, recipient=recipient)

    def _build_message(
        self,
        *,
        recipient: str,
        subject: str,
        content: str,
        notification_type: str,
        message_key: str,
        extra_headers: dict[str, str] | None = None,
    ) -> EmailMessage:
        sender_domain = self._sender_email.rsplit("@", maxsplit=1)[-1]
        message = EmailMessage()
        message["From"] = formataddr((self._sender_name, self._sender_email))
        message["To"] = recipient
        message["Subject"] = subject
        message["Date"] = format_datetime(datetime.now(UTC))
        message["Message-ID"] = make_msgid(idstring=message_key, domain=sender_domain)
        message["X-Password-Detective-Notification-Type"] = notification_type
        for name, value in (extra_headers or {}).items():
            message[name] = value
        message.set_content(content, charset="utf-8")
        return message

    def _send_message(self, *, message: EmailMessage, recipient: str) -> str:
        client = self._open_client()
        try:
            if self._username:
                client.login(self._username, self._password)
            refused = client.send_message(
                message,
                from_addr=self._sender_email,
                to_addrs=[recipient],
            )
            if refused:
                raise RuntimeError("notification_smtp_recipient_rejected")
        finally:
            _close_smtp_client(client)
        return str(message["Message-ID"])

    def _open_client(self) -> Any:
        if self._security == "ssl":
            factory = self._smtp_factory or smtplib.SMTP_SSL
            return factory(
                self._host,
                self._port,
                timeout=self._timeout_seconds,
                context=self._ssl_context_factory(),
            )

        factory = self._smtp_factory or smtplib.SMTP
        client = factory(self._host, self._port, timeout=self._timeout_seconds)
        if self._security != "starttls":
            return client
        try:
            client.ehlo()
            client.starttls(context=self._ssl_context_factory())
            client.ehlo()
        except Exception:
            _close_smtp_client(client)
            raise
        return client


def _close_smtp_client(client: Any) -> None:
    try:
        client.quit()
    except Exception:
        with suppress(Exception):
            client.close()


def _account_token_email(*, kind: str, token: str) -> tuple[str, str]:
    if kind == "email_verification":
        purpose = "验证邮箱"
        subject = f"{EMAIL_SUBJECT_PREFIX} 验证邮箱"
    elif kind == "password_reset":
        purpose = "重置账户密码"
        subject = f"{EMAIL_SUBJECT_PREFIX} 重置账户密码"
    else:
        purpose = "完成账户操作"
        subject = f"{EMAIL_SUBJECT_PREFIX} 账户安全通知"
    content = (
        f"请使用以下一次性令牌{purpose}：\n\n{token}\n\n"
        "令牌具有有效期且只能使用一次。若非本人操作，请忽略此邮件，不要将令牌转发给他人。"
    )
    return subject, content


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
    if settings.notification_backend == "webhook":
        return WebhookNotificationGateway(
            url=settings.notification_webhook_url,
            secret=settings.notification_webhook_secret,
            timeout_seconds=settings.notification_webhook_timeout_seconds,
        )
    return SMTPNotificationGateway(
        host=settings.notification_smtp_host,
        port=settings.notification_smtp_port,
        security=settings.notification_smtp_security,
        username=settings.notification_smtp_username,
        password=settings.notification_smtp_password.get_secret_value(),
        sender_email=settings.notification_smtp_sender_email,
        sender_name=settings.notification_smtp_sender_name,
        timeout_seconds=settings.notification_smtp_timeout_seconds,
    )
