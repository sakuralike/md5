from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from password_detective.db.models.setting_version import SettingVersionStatus


class SettingChangeReasonCode(StrEnum):
    SECURITY_HARDENING = "security_hardening"
    CAPACITY_ADJUSTMENT = "capacity_adjustment"
    PRODUCT_POLICY = "product_policy"
    INCIDENT_RESPONSE = "incident_response"
    ROLLBACK = "rollback"


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
    daily_reveal_quota: int = Field(ge=1, le=1000)
    reauthentication_ttl_minutes: int = Field(ge=1, le=15)
    privacy_deletion_grace_hours: int = Field(ge=1, le=720)
    desktop_min_client_version: str = Field(min_length=5, max_length=32)
    desktop_update_download_cache_seconds: int = Field(ge=60, le=31_536_000)
    user_levels: list[UserLevelDefinition] = Field(
        default_factory=default_user_levels, min_length=1, max_length=20
    )

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


class SettingVersionCreateRequest(BaseModel):
    expected_base_version_id: str | None = Field(default=None, max_length=36)
    reason_code: SettingChangeReasonCode
    snapshot: OperationalSettingsSnapshot


class SettingVersionPublishRequest(BaseModel):
    expected_published_version_id: str | None = Field(default=None, max_length=36)
    reason_code: SettingChangeReasonCode
    reauth_token: str = Field(min_length=16, max_length=256)


class SettingVersionRollbackRequest(BaseModel):
    expected_published_version_id: str = Field(max_length=36)
    reason_code: SettingChangeReasonCode = SettingChangeReasonCode.ROLLBACK
    reauth_token: str = Field(min_length=16, max_length=256)


class SettingDifference(BaseModel):
    key: str
    previous: int | str | list[UserLevelDefinition] | None
    current: int | str | list[UserLevelDefinition]


class SettingVersionSummary(BaseModel):
    id: str
    status: SettingVersionStatus
    schema_version: str
    snapshot_hash: str
    base_version_id: str | None
    rollback_of_id: str | None
    reason_code: str
    created_by: str
    published_by: str | None
    created_at: datetime
    published_at: datetime | None
    effective_at: datetime | None


class SettingVersionDetail(SettingVersionSummary):
    snapshot: OperationalSettingsSnapshot
    differences: list[SettingDifference]


class SettingVersionListResponse(BaseModel):
    items: list[SettingVersionSummary]
    page: int
    page_size: int
    total: int
    published_version_id: str | None


class SettingVersionMutationResponse(BaseModel):
    version: SettingVersionDetail
    audit_id: str
    request_id: str | None
