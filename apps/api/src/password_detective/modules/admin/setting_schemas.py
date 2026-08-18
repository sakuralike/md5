from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class SiteNavigationItem(BaseModel):
    label: str = Field(min_length=1, max_length=20)
    path: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    requires_auth: bool = False

    @field_validator("label", "path")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("导航路径必须是站内绝对路径")
        if any(character in value for character in ("\\", "<", ">", '"', "'")):
            raise ValueError("导航路径包含不允许的字符")
        return value


def default_site_navigation() -> list[SiteNavigationItem]:
    return [
        SiteNavigationItem(label="首页", path="/"),
        SiteNavigationItem(label="社区", path="/community"),
    ]


class UserLevelDefinition(BaseModel):
    code: str = Field(min_length=2, max_length=32, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=2, max_length=64)
    description: str = Field(min_length=2, max_length=200)
    min_growth_points: int = Field(ge=0, le=10_000_000)
    daily_reveal_quota: int = Field(ge=1, le=1000)
    can_submit: bool = True


def default_user_levels() -> list[UserLevelDefinition]:
    return [
        UserLevelDefinition(
            code="rookie",
            name="新手侦探",
            description="完成注册并开始参与社区协作。",
            min_growth_points=0,
            daily_reveal_quota=20,
        ),
        UserLevelDefinition(
            code="apprentice",
            name="见习侦探",
            description="持续贡献有效档案或验证反馈。",
            min_growth_points=100,
            daily_reveal_quota=30,
        ),
        UserLevelDefinition(
            code="senior",
            name="资深侦探",
            description="具备稳定、长期的有效社区贡献。",
            min_growth_points=500,
            daily_reveal_quota=50,
        ),
        UserLevelDefinition(
            code="expert",
            name="专家侦探",
            description="在贡献和验证活动中保持高质量表现。",
            min_growth_points=1500,
            daily_reveal_quota=75,
        ),
        UserLevelDefinition(
            code="chief",
            name="首席侦探",
            description="达到社区成长体系的最高长期贡献等级。",
            min_growth_points=5000,
            daily_reveal_quota=100,
        ),
    ]


class OperationalSettingsSnapshot(BaseModel):
    site_name: str = Field(default="密码侦探社", min_length=2, max_length=32)
    site_logo_url: str = Field(default="", max_length=500)
    site_navigation: list[SiteNavigationItem] = Field(
        default_factory=default_site_navigation, min_length=1, max_length=8
    )
    daily_reveal_quota: int = Field(ge=1, le=1000)
    reauthentication_ttl_minutes: int = Field(ge=1, le=15)
    privacy_deletion_grace_hours: int = Field(ge=1, le=720)
    desktop_min_client_version: str = Field(min_length=5, max_length=32)
    desktop_update_download_cache_seconds: int = Field(ge=60, le=31_536_000)
    user_levels: list[UserLevelDefinition] = Field(
        default_factory=default_user_levels, min_length=1, max_length=20
    )

    @field_validator("site_name", "site_logo_url")
    @classmethod
    def normalize_site_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("site_logo_url")
    @classmethod
    def validate_logo_url(cls, value: str) -> str:
        if not value:
            return value
        if value.startswith("/") and not value.startswith("//"):
            return value
        if value.startswith(("https://", "http://")):
            return value
        raise ValueError("Logo 地址必须是站内路径或 HTTP(S) 地址")

    @model_validator(mode="after")
    def validate_site_navigation(self) -> OperationalSettingsSnapshot:
        paths = [item.path for item in self.site_navigation]
        if len(paths) != len(set(paths)):
            raise ValueError("导航按钮路径不能重复")
        if not any(item.enabled for item in self.site_navigation):
            raise ValueError("至少需要启用一个导航按钮")
        return self

    @model_validator(mode="after")
    def validate_user_levels(self) -> OperationalSettingsSnapshot:
        codes = [item.code for item in self.user_levels]
        thresholds = [item.min_growth_points for item in self.user_levels]
        if len(codes) != len(set(codes)):
            raise ValueError("用户等级代码不能重复")
        if len(thresholds) != len(set(thresholds)):
            raise ValueError("用户等级成长值门槛不能重复")
        if thresholds[0] != 0:
            raise ValueError("首个用户等级必须从 0 成长值开始")
        if thresholds != sorted(thresholds):
            raise ValueError("用户等级必须按成长值门槛升序排列")
        return self

    @field_validator("desktop_min_client_version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) != 3 or any(not part.isdigit() for part in parts):
            raise ValueError("桌面最低版本必须使用 x.y.z 格式")
        return value


class OperationalSettingsResponse(BaseModel):
    settings: OperationalSettingsSnapshot
    updated_at: datetime | None
    updated_by: str | None


class SeoSettings(BaseModel):
    enabled: bool = True
    indexing_enabled: bool = False
    home_title: str = Field(default="", max_length=120)
    keywords: list[str] = Field(default_factory=list, max_length=8)
    description: str = Field(default="", max_length=320)
    title_separator: Literal["-", "_", "|", "·"] = "-"
    default_image_url: str = Field(default="", max_length=500)
    open_graph_enabled: bool = True
    sitemap_enabled: bool = True

    @field_validator("home_title", "description")
    @classmethod
    def normalize_plain_text(cls, value: str) -> str:
        normalized = value.strip()
        if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
            raise ValueError("SEO 文本不能包含换行符或控制字符")
        if "<" in normalized or ">" in normalized:
            raise ValueError("SEO 文本不能包含 HTML 标签")
        return normalized

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        normalized_keywords: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = value.strip()
            if not normalized:
                continue
            if len(normalized) > 32:
                raise ValueError("单个 SEO 关键词不能超过 32 个字符")
            if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
                raise ValueError("SEO 关键词不能包含换行符或控制字符")
            if "<" in normalized or ">" in normalized:
                raise ValueError("SEO 关键词不能包含 HTML 标签")
            if normalized not in seen:
                normalized_keywords.append(normalized)
                seen.add(normalized)
        return normalized_keywords

    @field_validator("default_image_url")
    @classmethod
    def validate_default_image_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            return normalized
        if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
            raise ValueError("默认分享图地址不能包含控制字符")
        if any(character in normalized for character in ("<", ">", '"', "'", "\\")):
            raise ValueError("默认分享图地址包含不允许的字符")
        if normalized.startswith("/") and not normalized.startswith("//"):
            return normalized
        if normalized.startswith(("https://", "http://")):
            return normalized
        raise ValueError("默认分享图地址必须是站内路径或 HTTP(S) 地址")


class SeoSettingsResponse(BaseModel):
    settings: SeoSettings
    updated_at: datetime | None
    updated_by: str | None


class SiteLogoUploadResponse(BaseModel):
    url: str
    content_type: Literal["image/png", "image/jpeg", "image/webp"]
    size_bytes: int
    sha256: str


class EmailDeliverySettingsUpdate(BaseModel):
    enabled: bool
    sender_name: str = Field(min_length=1, max_length=120)
    sender_email: EmailStr
    subject_prefix: str = Field(min_length=1, max_length=120)
    footer_text: str = Field(default="", max_length=1200)
    footer_html: str = Field(default="", max_length=4000)
    smtp_host: str = Field(min_length=1, max_length=255)
    smtp_port: int = Field(ge=1, le=65535)
    smtp_security: Literal["starttls", "ssl", "none"]
    smtp_username: str = Field(default="", max_length=255)
    smtp_auth_enabled: bool
    smtp_timeout_seconds: float = Field(ge=1, le=60)
    smtp_password: str | None = Field(default=None, max_length=1024)
    clear_smtp_password: bool = False

    @field_validator("sender_name", "subject_prefix", "smtp_host", "smtp_username")
    @classmethod
    def normalize_single_line_email_text(cls, value: str) -> str:
        normalized = value.strip()
        if "\r" in normalized or "\n" in normalized:
            raise ValueError("邮件头部和服务器配置不能包含换行符")
        return normalized

    @field_validator("footer_text", "footer_html")
    @classmethod
    def normalize_email_footer(cls, value: str) -> str:
        return value.strip()

    @field_validator("smtp_password")
    @classmethod
    def normalize_smtp_password(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value or None

    @model_validator(mode="after")
    def validate_password_update(self) -> EmailDeliverySettingsUpdate:
        if self.clear_smtp_password and self.smtp_password is not None:
            raise ValueError("不能同时设置和清除 SMTP 授权码")
        return self


class EmailDeliverySettingsResponse(BaseModel):
    backend: Literal["memory", "log", "webhook", "smtp"]
    enabled: bool
    smtp_configured: bool
    sender_name: str
    sender_email: str
    subject_prefix: str
    footer_text: str
    footer_html: str = ""
    content_format: Literal["multipart"] = "multipart"
    smtp_host: str
    smtp_port: int
    smtp_security: Literal["starttls", "ssl", "none"]
    smtp_username: str
    smtp_auth_enabled: bool
    smtp_password_configured: bool
    smtp_timeout_seconds: float
    configuration_source: Literal["database", "deployment_environment"]


class EmailDeliveryTestRequest(BaseModel):
    recipient: EmailStr


class EmailDeliveryTestResponse(BaseModel):
    message: str
    provider_message_id: str
