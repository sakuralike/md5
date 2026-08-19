from __future__ import annotations

import json
import os
import re
from email.utils import parseaddr
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from password_detective.core.client_ip import normalize_network_cidrs

FILE_BACKED_SETTING_ENVIRONMENTS: dict[str, str] = {
    "app_secret_key": "APP_SECRET_KEY",
    "database_url": "DATABASE_URL",
    "redis_url": "REDIS_URL",
    "candidate_secret_key_version": "CANDIDATE_SECRET_KEY_VERSION",
    "candidate_secret_keyring": "CANDIDATE_SECRET_KEYRING",
    "candidate_secret_dedup_key": "CANDIDATE_SECRET_DEDUP_KEY",
    "direct_message_key_version": "DIRECT_MESSAGE_KEY_VERSION",
    "direct_message_keyring": "DIRECT_MESSAGE_KEYRING",
    "notification_webhook_secret": "NOTIFICATION_WEBHOOK_SECRET",
    "notification_smtp_password": "NOTIFICATION_SMTP_PASSWORD",
}
MAX_SECRET_FILE_BYTES = 64 * 1024


def _read_file_backed_setting(raw_path: str, environment_name: str) -> str:
    path = Path(raw_path).expanduser()
    if path.is_symlink():
        raise ValueError(f"{environment_name}_FILE 必须指向普通文件")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise ValueError(f"{environment_name}_FILE 指向的秘密文件不可读取") from exc
    if not path.is_file():
        raise ValueError(f"{environment_name}_FILE 必须指向普通文件")
    if metadata.st_size > MAX_SECRET_FILE_BYTES:
        raise ValueError(f"{environment_name}_FILE 超过允许的大小限制")
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"{environment_name}_FILE 必须是 UTF-8 文本文件") from exc
    if "\x00" in value:
        raise ValueError(f"{environment_name}_FILE 不能包含 NUL 字符")
    return value.rstrip("\r\n")


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
    access_token_ttl_minutes: int = Field(default=120, ge=5, le=1440)
    refresh_token_ttl_days: int = Field(default=90, ge=1, le=365)
    account_token_ttl_minutes: int = Field(default=30, ge=5, le=1440)
    reauthentication_ttl_minutes: int = Field(default=5, ge=1, le=15)
    candidate_secret_key_version: str = Field(default="v1", min_length=1, max_length=32)
    candidate_secret_keyring: SecretStr = SecretStr("")
    candidate_secret_dedup_key: SecretStr = SecretStr("")
    direct_message_key_version: str = Field(default="v1", min_length=1, max_length=32)
    direct_message_keyring: SecretStr = SecretStr("")
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
    site_asset_storage_path: str = ".local/site-assets"
    site_logo_max_bytes: int = Field(default=2_097_152, ge=1_024, le=10_485_760)
    community_avatar_max_bytes: int = Field(default=2_097_152, ge=1_024, le=10_485_760)
    desktop_announcement_image_max_bytes: int = Field(default=5_242_880, ge=1_024, le=20_971_520)
    desktop_update_storage_path: str = ".local/desktop-updates"
    desktop_update_max_artifact_bytes: int = Field(
        default=536_870_912, ge=1_048_576, le=2_147_483_648
    )
    desktop_update_download_cache_seconds: int = Field(default=86_400, ge=60, le=31_536_000)
    database_url: str = "sqlite:///./.local/password-detective.db"
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)
    database_pool_timeout_seconds: int = Field(default=30, ge=1, le=120)
    database_pool_recycle_seconds: int = Field(default=1800, ge=30, le=86400)
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    web_login_rate_limit: int = Field(default=10, ge=1, le=1000)
    admin_login_rate_limit: int = Field(default=10, ge=1, le=1000)
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
    community_notification_digest_window_minutes: int = Field(default=60, ge=15, le=1440)
    browser_cookie_secure: bool = False
    max_json_body_bytes: int = Field(default=1_048_576, ge=1_024, le=16_777_216)
    cors_origins: str = "http://localhost:5173,http://localhost:5174"
    public_origin: str = "http://localhost:5173"
    trusted_proxy_cidrs: str = "127.0.0.1/32,::1/128"
    maintenance_force_disabled: bool = False
    auto_create_tables: bool = True
    log_level: str = "INFO"

    @model_validator(mode="before")
    @classmethod
    def load_file_backed_settings(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        values = dict(data)
        for field_name, environment_name in FILE_BACKED_SETTING_ENVIRONMENTS.items():
            raw_path = os.environ.get(f"{environment_name}_FILE", "").strip()
            if not raw_path:
                continue
            direct_value = values.get(field_name)
            if direct_value not in (None, ""):
                raise ValueError(f"{environment_name} 和 {environment_name}_FILE 不能同时配置")
            values[field_name] = _read_file_backed_setting(raw_path, environment_name)
        return values

    @field_validator("app_secret_key")
    @classmethod
    def validate_secret(cls, value: str, info) -> str:  # noqa: ANN001
        env = info.data.get("app_env", "local")
        if env not in {"local", "test"} and len(value) < 32:
            raise ValueError("非本地环境的 APP_SECRET_KEY 至少需要 32 个字符")
        return value

    @field_validator("public_origin")
    @classmethod
    def validate_public_origin(cls, value: str) -> str:
        origin = value.strip().rstrip("/")
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("PUBLIC_ORIGIN 必须是带主机的 HTTP(S) Origin")
        if parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError("PUBLIC_ORIGIN 不得包含路径、查询参数、片段或用户凭据")
        return origin

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def validate_trusted_proxy_cidrs(cls, value: str) -> str:
        try:
            networks = normalize_network_cidrs(value.split(","))
        except ValueError as exc:
            raise ValueError("TRUSTED_PROXY_CIDRS 必须是逗号分隔的 IPv4/IPv6 CIDR") from exc
        return ",".join(networks)

    @field_validator("browser_cookie_secure")
    @classmethod
    def validate_browser_cookie(cls, value: bool, info) -> bool:  # noqa: ANN001
        if info.data.get("app_env") == "production" and not value:
            raise ValueError("生产环境必须启用安全 Cookie")
        return value

    @model_validator(mode="after")
    def validate_candidate_secret_keys(self) -> Settings:
        version_pattern = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
        if not version_pattern.fullmatch(self.candidate_secret_key_version):
            raise ValueError("候选秘密密钥版本只能包含字母、数字、点、下划线和连字符")
        keyring = self.candidate_secret_key_map
        if keyring and self.candidate_secret_key_version not in keyring:
            raise ValueError("CANDIDATE_SECRET_KEYRING 必须包含当前密钥版本")
        if len(keyring) > 8:
            raise ValueError("CANDIDATE_SECRET_KEYRING 最多允许 8 个版本")
        for version, secret in keyring.items():
            if not version_pattern.fullmatch(version):
                raise ValueError(f"候选秘密密钥版本无效: {version}")
            if not secret:
                raise ValueError(f"候选秘密密钥不能为空: {version}")
            if self.app_env not in {"local", "test"} and len(secret) < 32:
                raise ValueError(f"非本地环境的候选秘密密钥至少需要 32 个字符: {version}")
        dedup_key = self.candidate_secret_dedup_key.get_secret_value()
        if keyring and not dedup_key:
            raise ValueError("配置 CANDIDATE_SECRET_KEYRING 时必须提供稳定去重密钥")
        if self.app_env not in {"local", "test"} and dedup_key and len(dedup_key) < 32:
            raise ValueError("非本地环境的候选秘密去重密钥至少需要 32 个字符")
        return self

    @model_validator(mode="after")
    def validate_direct_message_keys(self) -> Settings:
        version_pattern = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
        if not version_pattern.fullmatch(self.direct_message_key_version):
            raise ValueError("私信密钥版本只能包含字母、数字、点、下划线和连字符")
        keyring = self.direct_message_key_map
        if keyring and self.direct_message_key_version not in keyring:
            raise ValueError("DIRECT_MESSAGE_KEYRING 必须包含当前密钥版本")
        if len(keyring) > 8:
            raise ValueError("DIRECT_MESSAGE_KEYRING 最多允许 8 个版本")
        for version, secret in keyring.items():
            if not version_pattern.fullmatch(version):
                raise ValueError(f"私信密钥版本无效: {version}")
            if not secret:
                raise ValueError(f"私信密钥不能为空: {version}")
            if self.app_env not in {"local", "test"} and len(secret) < 32:
                raise ValueError(f"非本地环境的私信密钥至少需要 32 个字符: {version}")
        return self


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
    def candidate_secret_key_map(self) -> dict[str, str]:
        raw = self.candidate_secret_keyring.get_secret_value().strip()
        if not raw:
            return {}

        def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"CANDIDATE_SECRET_KEYRING 存在重复版本: {key}")
                result[key] = value
            return result

        try:
            parsed = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError("CANDIDATE_SECRET_KEYRING 必须是无重复键的 JSON 对象") from exc
        if not isinstance(parsed, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in parsed.items()
        ):
            raise ValueError("CANDIDATE_SECRET_KEYRING 必须是字符串到字符串的 JSON 对象")
        return parsed

    @property
    def direct_message_key_map(self) -> dict[str, str]:
        raw = self.direct_message_keyring.get_secret_value().strip()
        if not raw:
            return {}

        def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"DIRECT_MESSAGE_KEYRING 存在重复版本: {key}")
                result[key] = value
            return result

        try:
            parsed = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError("DIRECT_MESSAGE_KEYRING 必须是无重复键的 JSON 对象") from exc
        if not isinstance(parsed, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in parsed.items()
        ):
            raise ValueError("DIRECT_MESSAGE_KEYRING 必须是字符串到字符串的 JSON 对象")
        return parsed


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
