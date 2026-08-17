from __future__ import annotations

from email.message import EmailMessage

from password_detective.core.notifications import SMTPNotificationGateway


class _FakeSMTPClient:
    def __init__(self) -> None:
        self.message: EmailMessage | None = None

    def ehlo(self) -> None:
        pass

    def starttls(self, *, context: object) -> None:
        del context

    def login(self, username: str, password: str) -> None:
        del username, password

    def send_message(
        self,
        message: EmailMessage,
        *,
        from_addr: str,
        to_addrs: list[str],
    ) -> dict[str, tuple[int, bytes]]:
        del from_addr, to_addrs
        self.message = message
        return {}

    def quit(self) -> None:
        pass


def test_smtp_gateway_uses_saved_branding_and_safe_html_footer() -> None:
    client = _FakeSMTPClient()
    gateway = SMTPNotificationGateway(
        host="smtp.synthetic.example.com",
        port=587,
        security="starttls",
        username="synthetic-user",
        password="synthetic-password",
        sender_email="no-reply@synthetic.example.com",
        sender_name="合成通知",
        subject_prefix="[合成侦探社]",
        footer_text="这是合成系统邮件，请勿回复。",
        footer_html=(
            '<a href="https://synthetic.example.com">访问合成网站</a>'
            '<script>alert("unsafe")</script>'
        ),
        smtp_factory=lambda *args, **kwargs: client,
        ssl_context_factory=object,
    )

    gateway.send_test_email(recipient="operator@synthetic.example.com")

    assert client.message is not None
    assert client.message.is_multipart() is True
    assert str(client.message["Subject"]) == "[合成侦探社] 邮件投递测试"
    plain = client.message.get_body(preferencelist=("plain",))
    html = client.message.get_body(preferencelist=("html",))
    assert plain is not None and "这是合成系统邮件，请勿回复。" in plain.get_content()
    assert html is not None
    html_content = html.get_content()
    assert 'href="https://synthetic.example.com"' in html_content
    assert "alert" not in html_content
    assert "<script" not in html_content
    assert "synthetic-password" not in client.message.as_string()
