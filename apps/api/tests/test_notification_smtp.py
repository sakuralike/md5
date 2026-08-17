from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage

import pytest
from pydantic import ValidationError

from password_detective.core.config import Settings
from password_detective.core.notifications import (
    CommunityNotificationDigestEmailItem,
    SMTPNotificationGateway,
    build_notification_gateway,
)


class _FakeSMTPClient:
    def __init__(self, refused: dict[str, tuple[int, bytes]] | None = None) -> None:
        self.refused = refused or {}
        self.ehlo_calls = 0
        self.starttls_context = None
        self.login_credentials: tuple[str, str] | None = None
        self.sent_message: EmailMessage | None = None
        self.envelope_from: str | None = None
        self.envelope_to: list[str] | None = None
        self.quit_called = False
        self.close_called = False

    def ehlo(self) -> None:
        self.ehlo_calls += 1

    def starttls(self, *, context) -> None:  # noqa: ANN001
        self.starttls_context = context

    def login(self, username: str, password: str) -> None:
        self.login_credentials = (username, password)

    def send_message(
        self,
        message: EmailMessage,
        *,
        from_addr: str,
        to_addrs: list[str],
    ) -> dict[str, tuple[int, bytes]]:
        self.sent_message = message
        self.envelope_from = from_addr
        self.envelope_to = to_addrs
        return self.refused

    def quit(self) -> None:
        self.quit_called = True

    def close(self) -> None:
        self.close_called = True


def _gateway(
    client: _FakeSMTPClient,
    *,
    security: str = "starttls",
    factory_calls: list[tuple[tuple, dict]] | None = None,
) -> SMTPNotificationGateway:
    def factory(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        if factory_calls is not None:
            factory_calls.append((args, kwargs))
        return client

    return SMTPNotificationGateway(
        host="smtp.synthetic.example.com",
        port=465 if security == "ssl" else 587,
        security=security,  # type: ignore[arg-type]
        username="synthetic-user",
        password="synthetic-app-password",
        sender_email="no-reply@synthetic.example.com",
        sender_name="密码侦探社",
        timeout_seconds=8.5,
        smtp_factory=factory,
        ssl_context_factory=lambda: "synthetic-tls-context",
    )


def test_smtp_gateway_uses_starttls_auth_and_sends_account_token_as_plain_text():
    client = _FakeSMTPClient()
    factory_calls: list[tuple[tuple, dict]] = []
    gateway = _gateway(client, factory_calls=factory_calls)

    message_id = gateway.send_account_token(
        kind="email_verification",
        recipient="operator@synthetic.example.com",
        token="synthetic-one-time-token",
    )

    assert factory_calls == [
        (("smtp.synthetic.example.com", 587), {"timeout": 8.5})
    ]
    assert client.ehlo_calls == 2
    assert client.starttls_context == "synthetic-tls-context"
    assert client.login_credentials == ("synthetic-user", "synthetic-app-password")
    assert client.quit_called is True
    assert client.envelope_from == "no-reply@synthetic.example.com"
    assert client.envelope_to == ["operator@synthetic.example.com"]
    assert client.sent_message is not None
    assert str(client.sent_message["Subject"]) == "[密码侦探社] 验证邮箱"
    assert client.sent_message["To"] == "operator@synthetic.example.com"
    assert client.sent_message["X-Password-Detective-Notification-Type"] == "account_token"
    assert "synthetic-one-time-token" in client.sent_message.get_content()
    assert "synthetic-app-password" not in client.sent_message.as_string()
    assert message_id == str(client.sent_message["Message-ID"])
    assert message_id.endswith("@synthetic.example.com>")


def test_smtp_gateway_uses_implicit_ssl_and_sends_minimum_risk_alert_content():
    client = _FakeSMTPClient()
    factory_calls: list[tuple[tuple, dict]] = []
    gateway = _gateway(client, security="ssl", factory_calls=factory_calls)

    message_id = gateway.send_risk_alert(
        delivery_id="delivery-synthetic-1",
        kind="acknowledgement_overdue",
        recipient="moderator@synthetic.example.com",
        alert_id="alert-synthetic-1",
        severity="high",
        due_at=datetime(2026, 8, 3, 13, 30, tzinfo=UTC),
    )

    assert factory_calls == [
        (
            ("smtp.synthetic.example.com", 465),
            {"timeout": 8.5, "context": "synthetic-tls-context"},
        )
    ]
    assert client.ehlo_calls == 0
    assert client.starttls_context is None
    assert client.sent_message is not None
    content = client.sent_message.get_content()
    assert "alert-synthetic-1" in content
    assert "2026-08-03T13:30:00+00:00" in content
    assert "synthetic-candidate-secret" not in content
    assert client.sent_message["X-Password-Detective-Delivery-ID"] == "delivery-synthetic-1"
    assert message_id == str(client.sent_message["Message-ID"])


def test_smtp_gateway_closes_connection_when_starttls_handshake_fails():
    class FailingStartTLSClient(_FakeSMTPClient):
        def starttls(self, *, context) -> None:  # noqa: ANN001
            self.starttls_context = context
            raise RuntimeError("synthetic STARTTLS failure")

    client = FailingStartTLSClient()
    gateway = _gateway(client)

    with pytest.raises(RuntimeError, match="synthetic STARTTLS failure"):
        gateway.send_account_token(
            kind="email_verification",
            recipient="operator@synthetic.example.com",
            token="synthetic-one-time-token",
        )

    assert client.quit_called is True
    assert client.sent_message is None


def test_smtp_gateway_converts_recipient_refusal_to_provider_failure():
    client = _FakeSMTPClient(
        refused={"operator@synthetic.example.com": (550, b"synthetic rejection")}
    )
    gateway = _gateway(client)

    with pytest.raises(RuntimeError, match="notification_smtp_recipient_rejected"):
        gateway.send_account_token(
            kind="password_reset",
            recipient="operator@synthetic.example.com",
            token="synthetic-one-time-token",
        )

    assert client.quit_called is True


def test_smtp_settings_enforce_sender_credentials_and_encryption():
    base = {
        "notification_backend": "smtp",
        "notification_smtp_host": "smtp.synthetic.example.com",
        "notification_smtp_sender_email": "no-reply@synthetic.example.com",
    }
    with pytest.raises(ValidationError, match="服务器地址"):
        Settings(
            notification_backend="smtp",
            notification_smtp_sender_email=base["notification_smtp_sender_email"],
        )
    with pytest.raises(ValidationError, match="有效的发件邮箱"):
        Settings(**{**base, "notification_smtp_sender_email": "Synthetic <invalid@example.com>"})
    with pytest.raises(ValidationError, match="同时配置"):
        Settings(**base, notification_smtp_username="synthetic-user")
    with pytest.raises(ValidationError, match="认证凭据"):
        Settings(**base, app_env="integration")
    with pytest.raises(ValidationError, match="STARTTLS 或 SSL"):
        Settings(
            **base,
            app_env="production",
            notification_smtp_security="none",
            notification_smtp_username="synthetic-user",
            notification_smtp_password="synthetic-app-password",
            app_secret_key="synthetic-production-secret-key-at-least-32-characters",
            browser_cookie_secure=True,
        )

    settings = Settings(
        **base,
        app_env="production",
        notification_smtp_username="synthetic-user",
        notification_smtp_password="synthetic-app-password",
        app_secret_key="synthetic-production-secret-key-at-least-32-characters",
        browser_cookie_secure=True,
    )
    gateway = build_notification_gateway(settings)
    assert isinstance(gateway, SMTPNotificationGateway)
    assert str(settings.notification_smtp_password) == "**********"


def test_smtp_gateway_sends_admin_test_email_without_secrets():
    client = _FakeSMTPClient()
    gateway = _gateway(client)

    message_id = gateway.send_test_email(recipient="operator@synthetic.example.com")

    assert client.sent_message is not None
    assert str(client.sent_message["Subject"]) == "[密码侦探社] 邮件投递测试"
    assert client.sent_message["X-Password-Detective-Notification-Type"] == "smtp_test"
    assert "synthetic-app-password" not in client.sent_message.as_string()
    assert message_id == str(client.sent_message["Message-ID"])


def test_smtp_gateway_sends_stable_minimum_disclosure_community_digest() -> None:
    client = _FakeSMTPClient()
    gateway = _gateway(client)
    window_started_at = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)

    message_id = gateway.send_community_notification_digest(
        digest_id="digest-synthetic-001",
        recipient="digest-user@synthetic.example.com",
        window_started_at=window_started_at,
        window_ends_at=datetime(2026, 8, 17, 10, 0, tzinfo=UTC),
        items=[
            CommunityNotificationDigestEmailItem(
                kind="reply",
                preview="合成回复通知",
            )
        ],
    )

    assert client.sent_message is not None
    assert str(client.sent_message["Subject"]) == "[密码侦探社] 社区通知摘要"
    assert client.sent_message["X-Password-Detective-Notification-Type"] == (
        "community_notification_digest"
    )
    assert client.sent_message["X-Password-Detective-Digest-ID"] == "digest-synthetic-001"
    assert client.sent_message.get_content().count("合成回复通知") == 1
    assert "synthetic-app-password" not in client.sent_message.as_string()
    assert message_id == str(client.sent_message["Message-ID"])

    repeated_client = _FakeSMTPClient()
    repeated_gateway = _gateway(repeated_client)
    repeated_message_id = repeated_gateway.send_community_notification_digest(
        digest_id="digest-synthetic-001",
        recipient="digest-user@synthetic.example.com",
        window_started_at=window_started_at,
        window_ends_at=datetime(2026, 8, 17, 10, 0, tzinfo=UTC),
        items=[
            CommunityNotificationDigestEmailItem(
                kind="reply",
                preview="合成回复通知",
            )
        ],
    )
    assert repeated_message_id == message_id
