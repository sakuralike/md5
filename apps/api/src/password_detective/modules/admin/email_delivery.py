from __future__ import annotations

from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.notifications import (
    EMAIL_FOOTER_TEXT,
    EMAIL_SUBJECT_PREFIX,
    NotificationGateway,
    SMTPNotificationGateway,
)
from password_detective.db.audit import write_audit_log
from password_detective.modules.admin.setting_schemas import (
    EmailDeliverySettingsResponse,
    EmailDeliveryTestResponse,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal


def describe_email_delivery(settings: Settings) -> EmailDeliverySettingsResponse:
    password_configured = bool(settings.notification_smtp_password.get_secret_value())
    auth_enabled = bool(settings.notification_smtp_username.strip()) and password_configured
    enabled = settings.notification_backend == "smtp"
    return EmailDeliverySettingsResponse(
        backend=settings.notification_backend,
        enabled=enabled,
        smtp_configured=enabled
        and bool(settings.notification_smtp_host.strip())
        and bool(settings.notification_smtp_sender_email.strip())
        and (settings.app_env in {"local", "test"} or auth_enabled),
        sender_name=settings.notification_smtp_sender_name,
        sender_email=settings.notification_smtp_sender_email,
        subject_prefix=EMAIL_SUBJECT_PREFIX,
        footer_text=EMAIL_FOOTER_TEXT,
        smtp_host=settings.notification_smtp_host,
        smtp_port=settings.notification_smtp_port,
        smtp_security=settings.notification_smtp_security,
        smtp_username=settings.notification_smtp_username,
        smtp_auth_enabled=auth_enabled,
        smtp_password_configured=password_configured,
        smtp_timeout_seconds=settings.notification_smtp_timeout_seconds,
    )


def send_email_delivery_test(
    db: Session,
    *,
    settings: Settings,
    gateway: NotificationGateway,
    recipient: str,
    principal: Principal,
    context: ClientContext,
) -> EmailDeliveryTestResponse:
    if settings.notification_backend != "smtp" or not isinstance(
        gateway, SMTPNotificationGateway
    ):
        raise AppError(
            "admin.email_delivery_not_enabled",
            "当前通知后端不是 SMTP，无法发送测试邮件",
            status_code=409,
        )

    try:
        message_id = gateway.send_test_email(recipient=recipient)
    except Exception as exc:
        write_audit_log(
            db,
            actor_id=principal.user.id,
            action="admin.email_delivery.test_failed",
            target_type="notification_provider",
            target_id="smtp",
            result="failure",
            ip_prefix=context.ip_prefix,
            request_id=context.request_id,
            details={"provider": "smtp", "failure_type": type(exc).__name__},
        )
        db.commit()
        raise AppError(
            "admin.email_delivery_test_failed",
            "SMTP 测试邮件发送失败，请检查服务器、端口、加密方式和凭据",
            status_code=502,
        ) from exc

    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.email_delivery.test_sent",
        target_type="notification_provider",
        target_id="smtp",
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "provider": "smtp",
            "security": settings.notification_smtp_security,
            "provider_message_id": message_id,
        },
    )
    db.commit()
    return EmailDeliveryTestResponse(
        message="SMTP 测试邮件已由服务器接受",
        provider_message_id=message_id,
    )
