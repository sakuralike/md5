from __future__ import annotations

from email.utils import parseaddr
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "密码侦探社 API"
    app_env: str = "local"
    app_debug: bool = False
    app_secret_key: str = "local-development-secret-key-change-me"
    access_token_ttl_minutes: int = Field(default=15, ge=5, le=60)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=90)
    account_token_ttl_minutes: int = Field(default=30, ge=5, le=1440)
    reauthentication_ttl_minutes: int = Field(default=5, ge=1, le=15)
    candidate_secret_key_version: str = Field(default="v1", min_length=1, max_length=32)
    daily_reveal_quota: int = Field(default=5, ge=1, le=1000)
    authorization_declaration_version: str = Field(
        default="authorization-v1", min_length=1, max_length=32
    )
    privacy_export_ttl_minutes: int = Field(default=15, ge=5, le=1440)
    privacy_deletion_grace_hours: int = Field(default=168, ge=1, le=720)
    privacy_job_backend: Literal["inline", "celery"] = "inline"
    observability_metrics_enabled: bool = True
    submission_pending_points: int = Field(default=1, ge=0, le=1000)
    verification_reward_points: int = Field(default=1, ge=0, le=1000)
    desktop_challenge_ttl_seconds: int = Field(default=300, ge=60, le=900)
    desktop_receipt_clock_skew_seconds: int = Field(default=300, ge=30, le=900)
    desktop_min_client_version: str = Field(default="0.1.0", min_length=5, max_length=32)
    desktop_max_installations_per_user: int = Field(default=10, ge=1, le=100)
    desktop_update_storage_path: str = ".local/desktop-updates"
    desktop_update_max_artifact_bytes: int = Field(
        default=536_870_912, ge=1_048_576, le=2_147_483_648
    )
    desktop_update_download_cache_seconds: int = Field(
        default=86_400, ge=60, le=31_536_000
    )
    database_url: str = "sqlite:///./.local/password-detective.db"
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    rate_limit_namespace: str = "password-detective"
    notification_backend: Literal["memory", "log", "webhook", "smtp"] = "memory"
    notification_webhook_url: str = ""
    notification_webhook_secret: str = ""
    notification_webhook_timeout_seconds: float = Field(default=10.0, ge=1.0, le=30.0)
    notification_smtp_host: str = ""
    notification_smtp_port: int = Field(default=587, ge=1, le=65535)
    notification_smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    notification_smtp_username: str = ""
    notification_smtp_password: SecretStr = SecretStr("")
    notification_smtp_sender_email: str = ""
    notification_smtp_sender_name: str = Field(default="密码侦探社", max_length=128)
    notification_smtp_timeout_seconds: float = Field(default=10.0, ge=1.0, le=30.0)
    browser_cookie_secure: bool = False
    max_json_body_bytes: int = Field(default=1_048_576, ge=1_024, le=16_777_216)
    cors_origins: str = "http://localhost:5173,http://localhost:5174"
    auto_create_tables: bool = True
    log_level: str = "INFO"

    @field_validator("app_secret_key")
    @classmethod
    def validate_secret(cls, value: str, info) -> str:  # noqa: ANN001
        env = info.data.get("app_env", "local")
        if env not in {"local", "test"} and len(value) < 32:
            raise ValueError("非本地环境的 APP_SECRET_KEY 至少需要 32 个字符")
        return value

    @field_validator("browser_cookie_secure")
    @classmethod
    def validate_browser_cookie(cls, value: bool, info) -> bool:  # noqa: ANN001
        if info.data.get("app_env") == "production" and not value:
            raise ValueError("生产环境必须启用安全 Cookie")
        return value

    @model_validator(mode="after")
    def validate_notification_backend(self) -> Settings:
        if self.notification_backend == "webhook":
            if not self.notification_webhook_url.startswith("https://"):
                raise ValueError("Webhook 通知后端必须配置 HTTPS URL")
            if len(self.notification_webhook_secret) < 32:
                raise ValueError("Webhook 通知签名密钥至少需要 32 个字符")
        elif self.notification_backend == "smtp":
            if not self.notification_smtp_host.strip() or any(
                char in self.notification_smtp_host for char in "\r\n"
            ):
                raise ValueError("SMTP 通知后端必须配置服务器地址")
            sender = self.notification_smtp_sender_email.strip()
            display_name, parsed_sender = parseaddr(sender)
            if (
                not sender
                or display_name
                or parsed_sender != sender
                or "@" not in sender
                or any(char in sender for char in "\r\n")
            ):
                raise ValueError("SMTP 通知后端必须配置有效的发件邮箱")
            if not self.notification_smtp_sender_name.strip() or any(
                char in self.notification_smtp_sender_name for char in "\r\n"
            ):
                raise ValueError("SMTP 发件人名称不能为空或包含换行符")
            password = self.notification_smtp_password.get_secret_value()
            has_username = bool(self.notification_smtp_username.strip())
            has_password = bool(password)
            if has_username != has_password:
                raise ValueError("SMTP 用户名和密码必须同时配置")
            if self.app_env not in {"local", "test"} and not has_username:
                raise ValueError("非本地环境的 SMTP 通知后端必须配置认证凭据")
            if self.app_env not in {"local", "test"} and self.notification_smtp_security == "none":
                raise ValueError("非本地环境的 SMTP 通知后端必须启用 STARTTLS 或 SSL")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def ensure_local_directories(self) -> None:
        if self.database_url.startswith("sqlite:///"):
            raw_path = self.database_url.removeprefix("sqlite:///")
            if raw_path != ":memory:":
                Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.desktop_update_storage_path).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
