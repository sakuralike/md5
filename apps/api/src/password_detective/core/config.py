from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
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
    database_url: str = "sqlite:///./.local/password-detective.db"
    redis_url: str = "redis://localhost:6379/0"
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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def ensure_local_directories(self) -> None:
        if self.database_url.startswith("sqlite:///"):
            raw_path = self.database_url.removeprefix("sqlite:///")
            if raw_path != ":memory:":
                Path(raw_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
