from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.notifications import (
    EMAIL_FOOTER_TEXT,
    EMAIL_SUBJECT_PREFIX,
    NotificationGateway,
    SMTPNotificationGateway,
)
from password_detective.core.settings_secrets import (
    SettingsSecretVault,
    build_settings_secret_vault,
)
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.system_setting import SystemSetting
from password_detective.modules.admin.setting_schemas import (
    EmailDeliverySettingsResponse,
    EmailDeliverySettingsUpdate,
    EmailDeliveryTestResponse,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal

SMTP_EMAIL_DELIVERY_SETTING_KEY = "smtp_email_delivery"


@dataclass(frozen=True)
class EmailDeliveryRuntimeConfig:
    enabled: bool
    sender_name: str
    sender_email: str
    subject_prefix: str
    footer_text: str
    footer_html: str
    smtp_host: str
    smtp_port: int
    smtp_security: Literal["starttls", "ssl", "none"]
    smtp_username: str
    smtp_password: str
    smtp_auth_enabled: bool
    smtp_timeout_seconds: float
    configuration_source: Literal["database", "deployment_environment"]


def _deployment_runtime(settings: Settings) -> EmailDeliveryRuntimeConfig:
    password = settings.notification_smtp_password.get_secret_value()
    return EmailDeliveryRuntimeConfig(
        enabled=settings.notification_backend == "smtp",
        sender_name=settings.notification_smtp_sender_name,
        sender_email=settings.notification_smtp_sender_email,
        subject_prefix=EMAIL_SUBJECT_PREFIX,
        footer_text=EMAIL_FOOTER_TEXT,
        footer_html="",
        smtp_host=settings.notification_smtp_host,
        smtp_port=settings.notification_smtp_port,
        smtp_security=settings.notification_smtp_security,
        smtp_username=settings.notification_smtp_username,
        smtp_password=password,
        smtp_auth_enabled=bool(settings.notification_smtp_username.strip()) and bool(password),
        smtp_timeout_seconds=settings.notification_smtp_timeout_seconds,
        configuration_source="deployment_environment",
    )


def build_settings_secret_vault_for_settings(settings: Settings) -> SettingsSecretVault:
    return build_settings_secret_vault(settings)


def _stored_runtime(
    db: Session,
    settings: Settings,
) -> EmailDeliveryRuntimeConfig | None:
    record = db.get(SystemSetting, SMTP_EMAIL_DELIVERY_SETTING_KEY)
    if record is None:
        return None
    value = record.value_json
    vault = build_settings_secret_vault_for_settings(settings)
    password = ""
    ciphertext = value.get("smtp_password_ciphertext")
    nonce = value.get("smtp_password_nonce")
    key_version = value.get("smtp_password_key_version")
    if ciphertext and nonce and key_version:
        from password_detective.core.settings_secrets import EncryptedSettingsSecret

        password = vault.decrypt(
            EncryptedSettingsSecret(
                ciphertext=str(ciphertext), nonce=str(nonce), key_version=str(key_version)
            )
        )
    return EmailDeliveryRuntimeConfig(
        enabled=bool(value.get("enabled", False)),
        sender_name=str(value.get("sender_name", "")),
        sender_email=str(value.get("sender_email", "")),
        subject_prefix=str(value.get("subject_prefix", EMAIL_SUBJECT_PREFIX)),
        footer_text=str(value.get("footer_text", EMAIL_FOOTER_TEXT)),
        footer_html=str(value.get("footer_html", "")),
        smtp_host=str(value.get("smtp_host", "")),
        smtp_port=int(value.get("smtp_port", 587)),
        smtp_security=str(value.get("smtp_security", "starttls")),
        smtp_username=str(value.get("smtp_username", "")),
        smtp_password=password,
        smtp_auth_enabled=bool(value.get("smtp_auth_enabled", False)),
        smtp_timeout_seconds=float(value.get("smtp_timeout_seconds", 10)),
        configuration_source="database",
    )


def resolve_email_delivery_runtime(
    db: Session | None,
    settings: Settings,
) -> EmailDeliveryRuntimeConfig:
    if db is not None:
        stored = _stored_runtime(db, settings)
        if stored is not None:
            return stored
    return _deployment_runtime(settings)


def build_email_delivery_gateway(
    db: Session,
    *,
    settings: Settings,
    fallback: NotificationGateway,
) -> NotificationGateway:
    if db.get(SystemSetting, SMTP_EMAIL_DELIVERY_SETTING_KEY) is None:
        return fallback
    runtime = resolve_email_delivery_runtime(db, settings)
    if not runtime.enabled:
        from password_detective.core.notifications import MemoryNotificationGateway

        return MemoryNotificationGateway()
    return SMTPNotificationGateway(
        host=runtime.smtp_host,
        port=runtime.smtp_port,
        security=runtime.smtp_security,
        username=runtime.smtp_username if runtime.smtp_auth_enabled else "",
        password=runtime.smtp_password if runtime.smtp_auth_enabled else "",
        sender_email=runtime.sender_email,
        sender_name=runtime.sender_name,
        subject_prefix=runtime.subject_prefix,
        footer_text=runtime.footer_text,
        footer_html=runtime.footer_html,
        timeout_seconds=runtime.smtp_timeout_seconds,
    )


def _response(
    runtime: EmailDeliveryRuntimeConfig, *, backend: str
) -> EmailDeliverySettingsResponse:
    has_transport = bool(runtime.smtp_host.strip()) and bool(runtime.sender_email.strip())
    auth_valid = not runtime.smtp_auth_enabled or (
        bool(runtime.smtp_username.strip()) and bool(runtime.smtp_password)
    )
    return EmailDeliverySettingsResponse(
        backend=backend if backend in {"memory", "log", "webhook", "smtp"} else "smtp",
        enabled=runtime.enabled,
        smtp_configured=runtime.enabled and has_transport and auth_valid,
        sender_name=runtime.sender_name,
        sender_email=runtime.sender_email,
        subject_prefix=runtime.subject_prefix,
        footer_text=runtime.footer_text,
        footer_html=runtime.footer_html,
        smtp_host=runtime.smtp_host,
        smtp_port=runtime.smtp_port,
        smtp_security=runtime.smtp_security,
        smtp_username=runtime.smtp_username,
        smtp_auth_enabled=runtime.smtp_auth_enabled,
        smtp_password_configured=bool(runtime.smtp_password),
        smtp_timeout_seconds=runtime.smtp_timeout_seconds,
        configuration_source=runtime.configuration_source,
    )


def describe_email_delivery(
    settings: Settings,
    db: Session | None = None,
) -> EmailDeliverySettingsResponse:
    runtime = resolve_email_delivery_runtime(db, settings)
    backend = (
        "smtp"
        if runtime.configuration_source == "database"
        else settings.notification_backend
    )
    return _response(runtime, backend=backend)


def _safe_settings_details(
    runtime: EmailDeliveryRuntimeConfig, *, password_changed: bool
) -> dict[str, object]:
    return {
        "enabled": runtime.enabled,
        "sender_email": runtime.sender_email,
        "smtp_host": runtime.smtp_host,
        "smtp_port": runtime.smtp_port,
        "smtp_security": runtime.smtp_security,
        "smtp_auth_enabled": runtime.smtp_auth_enabled,
        "smtp_password_configured": bool(runtime.smtp_password),
        "password_changed": password_changed,
        "configuration_source": "database",
    }


def save_email_delivery_settings(
    db: Session,
    *,
    settings: Settings,
    payload: EmailDeliverySettingsUpdate,
    principal: Principal,
    context: ClientContext,
) -> EmailDeliverySettingsResponse:
    existing = db.get(SystemSetting, SMTP_EMAIL_DELIVERY_SETTING_KEY)
    existing_runtime = _stored_runtime(db, settings) if existing is not None else None
    current_password = existing_runtime.smtp_password if existing_runtime is not None else ""
    if payload.clear_smtp_password:
        password = ""
        password_changed = bool(current_password)
    elif payload.smtp_password is not None:
        password = payload.smtp_password
        password_changed = True
    else:
        password = current_password
        password_changed = False

    username = payload.smtp_username.strip()
    if payload.smtp_auth_enabled and not username:
        raise AppError(
            "admin.email_delivery_invalid_configuration",
            "启用 SMTPAuth 时必须填写 SMTP 用户名",
            status_code=422,
        )
    if (
        payload.smtp_auth_enabled
        and not password
        and not payload.clear_smtp_password
        and existing is None
    ):
        raise AppError(
            "admin.email_delivery_invalid_configuration",
            "启用 SMTPAuth 时必须配置 SMTP 授权码",
            status_code=422,
        )
    if payload.enabled and not payload.smtp_host.strip():
        raise AppError(
            "admin.email_delivery_invalid_configuration",
            "启用 SMTP 投递时必须填写服务器地址",
            status_code=422,
        )

    encrypted: dict[str, str] = {}
    if password:
        secret = build_settings_secret_vault_for_settings(settings).encrypt(password)
        encrypted = {
            "smtp_password_ciphertext": secret.ciphertext,
            "smtp_password_nonce": secret.nonce,
            "smtp_password_key_version": secret.key_version,
        }
    value = {
        "enabled": payload.enabled,
        "sender_name": payload.sender_name,
        "sender_email": str(payload.sender_email),
        "subject_prefix": payload.subject_prefix,
        "footer_text": payload.footer_text,
        "footer_html": payload.footer_html,
        "smtp_host": payload.smtp_host,
        "smtp_port": payload.smtp_port,
        "smtp_security": payload.smtp_security,
        "smtp_username": username,
        "smtp_auth_enabled": payload.smtp_auth_enabled,
        "smtp_timeout_seconds": payload.smtp_timeout_seconds,
        **encrypted,
    }
    now = utc_now()
    if existing is None:
        db.add(
            SystemSetting(
                key=SMTP_EMAIL_DELIVERY_SETTING_KEY,
                value_json=value,
                version=1,
                updated_by=principal.user.id,
                updated_at=now,
            )
        )
    else:
        existing.value_json = value
        existing.version += 1
        existing.updated_by = principal.user.id
        existing.updated_at = now
    runtime = EmailDeliveryRuntimeConfig(
        enabled=payload.enabled,
        sender_name=payload.sender_name,
        sender_email=str(payload.sender_email),
        subject_prefix=payload.subject_prefix,
        footer_text=payload.footer_text,
        footer_html=payload.footer_html,
        smtp_host=payload.smtp_host,
        smtp_port=payload.smtp_port,
        smtp_security=payload.smtp_security,
        smtp_username=username,
        smtp_password=password,
        smtp_auth_enabled=payload.smtp_auth_enabled,
        smtp_timeout_seconds=payload.smtp_timeout_seconds,
        configuration_source="database",
    )
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.email_delivery.settings_saved",
        target_type="notification_provider",
        target_id="smtp",
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details=_safe_settings_details(runtime, password_changed=password_changed),
    )
    db.commit()
    return _response(runtime, backend="smtp")


def send_email_delivery_test(
    db: Session,
    *,
    settings: Settings,
    gateway: NotificationGateway,
    recipient: str,
    principal: Principal,
    context: ClientContext,
) -> EmailDeliveryTestResponse:
    runtime = resolve_email_delivery_runtime(db, settings)
    if not runtime.enabled or not isinstance(gateway, SMTPNotificationGateway):
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
            "security": runtime.smtp_security,
            "provider_message_id": message_id,
        },
    )
    db.commit()
    return EmailDeliveryTestResponse(
        message="SMTP 测试邮件已由服务器接受",
        provider_message_id=message_id,
    )
