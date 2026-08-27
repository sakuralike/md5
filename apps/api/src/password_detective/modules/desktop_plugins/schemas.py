from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PluginArchitecture = Literal["windows-x64", "windows-arm64"]
PluginStatus = Literal["draft", "active", "suspended", "revoked"]
PluginVersionStatus = Literal[
    "draft",
    "uploading",
    "quarantined",
    "review_queued",
    "auto_review_running",
    "auto_review_failed",
    "manual_review_ready",
    "approved",
    "published",
    "yanked",
    "rejected",
    "withdrawn",
    "revoked",
]
PluginCategory = Literal[
    "archive",
    "file-analysis",
    "workflow",
    "report-export",
    "community",
    "development",
    "theme",
]

PLUGIN_CAPABILITIES = frozenset(
    {
        "ui:command",
        "ui:theme",
        "ui:window",
        "storage:private",
        "file:read:selected",
        "api:profile:read",
        "api:hash:read",
        "api:verification:submit",
        "network:internet",
        "secret:candidate:ephemeral",
        "process:spawn",
        "system:persistence",
        "credential:read",
    }
)
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$")
_SEMVER_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_HOST_VERSION_PATTERN = re.compile(
    r"^(?:(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)|(0|[1-9][0-9]*)\.x)$"
)


def _strip(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("字段不能为空")
    return normalized


def _optional_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise ValueError("链接必须是不含凭据的 HTTP(S) URL")
    return normalized


def _normalize_tags(values: list[str]) -> list[str]:
    normalized = [_strip(value).lower() for value in values]
    if any(len(value) > 64 for value in normalized):
        raise ValueError("标签长度不能超过 64 个字符")
    if len(normalized) != len(set(normalized)):
        raise ValueError("标签不能重复")
    return normalized


def _normalize_capabilities(values: list[str]) -> list[str]:
    normalized = [_strip(value) for value in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError("权限不能重复")
    unknown = sorted(set(normalized) - PLUGIN_CAPABILITIES)
    if unknown:
        raise ValueError(f"包含未知插件权限：{', '.join(unknown)}")
    return normalized


class PluginProjectCreateRequest(BaseModel):
    slug: str = Field(min_length=3, max_length=128)
    name: str = Field(min_length=2, max_length=128)
    summary: str = Field(default="", max_length=320)
    description: str = Field(default="", max_length=20_000)
    category: PluginCategory = "development"
    tags: list[str] = Field(default_factory=list, max_length=20)
    website_url: str | None = Field(default=None, max_length=2_000)
    privacy_policy_url: str | None = Field(default=None, max_length=2_000)
    source_url: str | None = Field(default=None, max_length=2_000)
    linked_third_party_app_id: str | None = Field(default=None, min_length=36, max_length=36)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        normalized = _strip(value).lower()
        if not _SLUG_PATTERN.fullmatch(normalized):
            raise ValueError("插件 ID 必须是包含分隔符的小写反向域名式标识")
        return normalized

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return _strip(value)

    @field_validator("summary", "description")
    @classmethod
    def strip_optional_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return _normalize_tags(values)

    @field_validator("website_url", "privacy_policy_url", "source_url")
    @classmethod
    def validate_urls(cls, value: str | None) -> str | None:
        return _optional_url(value)


class PluginProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    summary: str | None = Field(default=None, max_length=320)
    description: str | None = Field(default=None, max_length=20_000)
    category: PluginCategory | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    website_url: str | None = Field(default=None, max_length=2_000)
    privacy_policy_url: str | None = Field(default=None, max_length=2_000)
    source_url: str | None = Field(default=None, max_length=2_000)
    linked_third_party_app_id: str | None = Field(default=None, min_length=36, max_length=36)
    version: int = Field(ge=1)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return _strip(value) if value is not None else None

    @field_validator("summary", "description")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str] | None) -> list[str] | None:
        return _normalize_tags(values) if values is not None else None

    @field_validator("website_url", "privacy_policy_url", "source_url")
    @classmethod
    def validate_urls(cls, value: str | None) -> str | None:
        return _optional_url(value)


class SigningKeyCreateRequest(BaseModel):
    key_id: str | None = Field(default=None, min_length=3, max_length=128)
    public_key_base64: str | None = Field(default=None, min_length=40, max_length=128)
    reauth_token: str = Field(min_length=32, max_length=256)
    rotated_from_id: str | None = Field(default=None, min_length=36, max_length=36)

    @field_validator("key_id", "public_key_base64", "reauth_token")
    @classmethod
    def strip_values(cls, value: str | None) -> str | None:
        return _strip(value) if value is not None else None


class SigningKeyRevokeRequest(BaseModel):
    reauth_token: str = Field(min_length=32, max_length=256)


class SigningKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key_id: str
    public_key_base64: str
    fingerprint: str
    status: str
    rotated_from_id: str | None
    created_at: datetime
    revoked_at: datetime | None
    private_key_base64: str | None = None


class SigningKeyListResponse(BaseModel):
    items: list[SigningKeyResponse]


class PluginArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    architecture: PluginArchitecture
    status: str
    zone: str
    artifact_filename: str
    size_bytes: int
    expanded_size_bytes: int | None
    sha256: str
    created_at: datetime
    updated_at: datetime


class PluginVersionCreateRequest(BaseModel):
    semver: str = Field(min_length=5, max_length=32)
    signing_key_id: str = Field(min_length=36, max_length=36)
    protocol_min: int = Field(default=1, ge=1, le=1)
    protocol_max: int = Field(default=1, ge=1, le=1)
    host_min: str = Field(default="0.1.0", min_length=5, max_length=32)
    host_max: str = Field(default="0.x", min_length=3, max_length=32)
    requested_capabilities: list[str] = Field(default_factory=list, max_length=64)
    release_notes: str = Field(default="", max_length=20_000)
    source_review_mode: Literal["source", "reproducible", "binary_only"] = "binary_only"

    @field_validator("semver")
    @classmethod
    def validate_semver(cls, value: str) -> str:
        normalized = _strip(value)
        if not _SEMVER_PATTERN.fullmatch(normalized):
            raise ValueError("插件版本必须是严格 SemVer x.y.z")
        return normalized

    @field_validator("host_min", "host_max")
    @classmethod
    def validate_host_version(cls, value: str) -> str:
        normalized = _strip(value)
        if not _HOST_VERSION_PATTERN.fullmatch(normalized):
            raise ValueError("宿主版本必须是 x.y.z 或 x.x")
        return normalized

    @field_validator("requested_capabilities")
    @classmethod
    def normalize_capabilities(cls, values: list[str]) -> list[str]:
        return _normalize_capabilities(values)


class PluginVersionFinalizeRequest(BaseModel):
    version: int = Field(ge=1)


class PluginVersionSubmitRequest(BaseModel):
    version: int = Field(ge=1)


class PluginVersionApproveRequest(BaseModel):
    version: int = Field(ge=1)
    approved_capabilities: list[str] = Field(default_factory=list, max_length=64)
    review_note: str = Field(min_length=1, max_length=2_000)

    @field_validator("approved_capabilities")
    @classmethod
    def normalize_capabilities(cls, values: list[str]) -> list[str]:
        return _normalize_capabilities(values)

    @field_validator("review_note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return _strip(value)


class PluginVersionRejectRequest(BaseModel):
    version: int = Field(ge=1)
    review_note: str = Field(min_length=1, max_length=2_000)
    remediation_days: int = Field(default=7, ge=1, le=30)

    @field_validator("review_note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return _strip(value)


class PluginVersionPublishRequest(BaseModel):
    version: int = Field(ge=1)
    channel: str = Field(default="stable", min_length=1, max_length=32)

    @field_validator("channel")
    @classmethod
    def normalize_channel(cls, value: str) -> str:
        normalized = _strip(value).lower()
        if normalized != "stable":
            raise ValueError("当前仅支持 stable 发布通道")
        return normalized


class PluginVersionYankRequest(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)
    remediation_days: int = Field(default=7, ge=1, le=30)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _strip(value)


class PluginVersionRevokeRequest(BaseModel):
    version: int = Field(ge=1)
    reason_code: str = Field(min_length=3, max_length=64)
    reason: str = Field(min_length=1, max_length=2_000)
    affects_historical_versions: bool = False

    @field_validator("reason_code", "reason")
    @classmethod
    def normalize_values(cls, value: str) -> str:
        return _strip(value)


class PluginReviewEventResponse(BaseModel):
    id: str
    kind: str
    actor_user_id: str | None
    note: str | None
    requested_capabilities: list[str]
    approved_capabilities: list[str]
    version_number: int
    created_at: datetime


class PluginStaticFindingResponse(BaseModel):
    id: str
    stage: str
    rule_id: str
    severity: str
    title: str
    detail: str
    file_path: str | None
    evidence: dict
    blocked: bool
    created_at: datetime


class PluginDynamicTaskResponse(BaseModel):
    id: str
    artifact_id: str
    architecture: str
    status: str
    runner_id: str | None
    attempt: int
    lease_expires_at: datetime | None
    evidence_complete: bool
    fresh_environment: bool
    destruction_proof_sha256: str | None
    error_code: str | None
    error_message: str | None
    result_summary: dict
    completed_at: datetime | None
    created_at: datetime


class PluginStaticReviewRunResponse(BaseModel):
    id: str
    policy_version: str
    status: str
    attempt: int
    summary: dict
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    findings: list[PluginStaticFindingResponse]
    dynamic_tasks: list[PluginDynamicTaskResponse]


class PluginStaticReviewReportResponse(BaseModel):
    version_id: str
    version_status: PluginVersionStatus
    runs: list[PluginStaticReviewRunResponse]


class PluginRunnerCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=128)
    architecture: PluginArchitecture
    certificate_fingerprint: str = Field(min_length=64, max_length=64)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _strip(value)

    @field_validator("certificate_fingerprint")
    @classmethod
    def normalize_fingerprint(cls, value: str) -> str:
        normalized = _strip(value).lower()
        if any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("证书指纹必须是 SHA-256 十六进制摘要")
        return normalized


class PluginRunnerResponse(BaseModel):
    id: str
    name: str
    architecture: PluginArchitecture
    certificate_fingerprint: str
    status: str
    policy_version: str | None
    image_digest: str | None
    probe_version: str | None
    last_heartbeat_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class PluginRunnerRegistrationResponse(PluginRunnerResponse):
    runner_secret: str | None


class PluginRunnerListResponse(BaseModel):
    items: list[PluginRunnerResponse]


class PluginReviewMetricsResponse(BaseModel):
    generated_at: datetime
    review_run_counts: dict[str, int]
    version_status_counts: dict[str, int]
    dynamic_task_counts: dict[str, int]
    runner_status_counts: dict[str, int]
    runner_capacity_by_architecture: dict[str, int]
    runner_active_by_architecture: dict[str, int]
    queue_depth_by_architecture: dict[str, int]
    oldest_queued_seconds: float | None
    average_review_seconds: float | None
    p95_review_seconds: float | None
    completed_last_24_hours: int
    install_events_last_24_hours: int


class PluginReviewPolicyUpdate(BaseModel):
    version: int = Field(ge=0)
    static_lease_seconds: int = Field(default=300, ge=60, le=1_800)
    dynamic_lease_seconds: int = Field(default=300, ge=60, le=1_800)
    task_token_seconds: int = Field(default=900, ge=60, le=3_600)
    maximum_static_attempts: int = Field(default=3, ge=1, le=5)
    maximum_dynamic_attempts: int = Field(default=3, ge=1, le=5)
    runner_offline_seconds: int = Field(default=90, ge=30, le=600)
    revocation_refresh_hours: int = Field(default=6, ge=1, le=24)
    revocation_max_stale_hours: int = Field(default=168, ge=24, le=720)
    dynamic_review_enabled: bool = False
    llm_review_enabled: bool = False
    llm_provider: Literal["disabled", "openai_compatible", "anthropic_compatible"] = "disabled"
    llm_base_url: str = Field(default="", max_length=2_000)
    llm_model: str = Field(default="", max_length=128)
    llm_timeout_seconds: int = Field(default=30, ge=5, le=120)

    @model_validator(mode="after")
    def validate_revocation_window(self) -> PluginReviewPolicyUpdate:
        if self.revocation_max_stale_hours <= self.revocation_refresh_hours:
            raise ValueError("撤销缓存最大离线时长必须大于刷新间隔")
        if self.llm_provider != "disabled" and (
            not _optional_url(self.llm_base_url) or not _strip(self.llm_model)
        ):
            raise ValueError("启用 LLM Provider 时必须配置 HTTPS API 地址和模型名")
        return self


class PluginReviewPolicyResponse(PluginReviewPolicyUpdate):
    policy_version: str
    static_engine_version: str
    dynamic_engine_version: str
    updated_at: datetime | None
    updated_by: str | None
    llm_api_key_configured: bool


class PluginReviewLlmKeyUpdate(BaseModel):
    api_key: str = Field(min_length=12, max_length=1_024)

    @field_validator("api_key")
    @classmethod
    def normalize_api_key(cls, value: str) -> str:
        return _strip(value)


class PluginReviewLlmEnabledUpdate(BaseModel):
    enabled: bool


class PluginReviewDynamicEnabledUpdate(BaseModel):
    enabled: bool


class PluginSourceLlmReviewRequest(BaseModel):
    instruction: str = Field(
        default="请分析源码中的恶意行为、数据外传和权限滥用风险。", min_length=1, max_length=2_000
    )

    @field_validator("instruction")
    @classmethod
    def normalize_instruction(cls, value: str) -> str:
        return _strip(value)


class PluginReviewLlmConnectionResponse(BaseModel):
    connected: Literal[True]
    provider: Literal["openai_compatible", "anthropic_compatible"]
    model: str


class PluginReviewSourceFileResponse(BaseModel):
    path: str
    content: str
    truncated: bool


class PluginReviewSourceResponse(BaseModel):
    version_id: str
    files: list[PluginReviewSourceFileResponse]


class PluginRunnerHeartbeatRequest(BaseModel):
    policy_version: str = Field(min_length=3, max_length=64)
    image_digest: str = Field(min_length=64, max_length=64)
    probe_version: str = Field(min_length=1, max_length=64)
    fresh_environment_ready: bool

    @field_validator("policy_version", "probe_version")
    @classmethod
    def normalize_values(cls, value: str) -> str:
        return _strip(value)

    @field_validator("image_digest")
    @classmethod
    def normalize_image_digest(cls, value: str) -> str:
        normalized = _strip(value).lower()
        if any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("镜像摘要必须是 SHA-256 十六进制摘要")
        return normalized


class PluginRunnerTaskLeaseResponse(BaseModel):
    task_id: str
    review_run_id: str
    plugin_id: str
    plugin_slug: str
    version_id: str
    semver: str
    artifact_id: str
    architecture: PluginArchitecture
    artifact_sha256: str
    artifact_size_bytes: int
    requested_capabilities: list[str]
    policy_version: str
    artifact_url: str
    task_token: str
    expires_at: datetime


class PluginRunnerTaskHeartbeatResponse(BaseModel):
    task_id: str
    lease_expires_at: datetime


EvidenceValue = bool | int | float | None


class PluginDynamicFindingRequest(BaseModel):
    stage: Literal[
        "dynamic_protocol",
        "dynamic_resource",
        "dynamic_file",
        "dynamic_process",
        "dynamic_network",
        "dynamic_cleanup",
    ]
    rule_id: str = Field(min_length=3, max_length=64)
    severity: Literal["info", "low", "medium", "high", "critical"]
    title: str = Field(min_length=1, max_length=255)
    detail: str = Field(min_length=1, max_length=2_000)
    file_path: str | None = Field(default=None, max_length=512)
    evidence: dict[str, EvidenceValue] = Field(default_factory=dict, max_length=16)
    blocked: bool = False

    @field_validator("rule_id", "title", "detail")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("file_path")
    @classmethod
    def validate_relative_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _strip(value)
        if (
            not normalized
            or "\\" in normalized
            or ":" in normalized
            or normalized.startswith("/")
            or ".." in normalized.split("/")
        ):
            raise ValueError("动态证据文件路径必须是安全相对路径")
        return normalized


class PluginRunnerTaskCompleteRequest(BaseModel):
    outcome: Literal["passed", "blocked", "infrastructure_failed"]
    evidence_complete: bool
    fresh_environment: bool
    destruction_proof_sha256: str = Field(min_length=64, max_length=64)
    summary: dict[str, EvidenceValue] = Field(default_factory=dict, max_length=32)
    findings: list[PluginDynamicFindingRequest] = Field(default_factory=list, max_length=128)
    error_code: str | None = Field(default=None, max_length=128)
    error_message: str | None = Field(default=None, max_length=2_000)

    @field_validator("destruction_proof_sha256")
    @classmethod
    def normalize_destruction_proof(cls, value: str) -> str:
        normalized = _strip(value).lower()
        if any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("销毁证明必须是 SHA-256 十六进制摘要")
        return normalized

    @field_validator("error_code", "error_message")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _strip(value) if value is not None else None


class PluginReviewQueueItem(BaseModel):
    version_id: str
    plugin_id: str
    plugin_slug: str
    plugin_name: str
    owner_user_id: str
    semver: str
    status: PluginVersionStatus
    requested_capabilities: list[str]
    approved_capabilities: list[str]
    signing_key_fingerprint: str
    manifest_sha256: str | None
    risk_tier: str
    submitted_at: datetime | None
    updated_at: datetime
    version: int


class PluginReviewQueueResponse(BaseModel):
    items: list[PluginReviewQueueItem]
    page: int
    page_size: int
    total: int


class PluginReviewDetailResponse(PluginReviewQueueItem):
    manifest_json: dict | None
    release_notes: str
    source_review_mode: str
    review_policy_version: str | None
    platform_key_id: str | None
    platform_public_key_base64: str | None
    platform_signature_base64: str | None
    platform_signature_payload: dict | None
    artifacts: list[PluginArtifactResponse]
    events: list[PluginReviewEventResponse]
    review_runs: list[PluginStaticReviewRunResponse]
    remediation_deadline_at: datetime | None = None


class PluginReportCreateRequest(BaseModel):
    version_id: str | None = Field(default=None, min_length=36, max_length=36)
    category: Literal["malware", "privacy", "copyright", "misleading", "other"]
    description: str = Field(min_length=10, max_length=4_000)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return _strip(value)


class PluginReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    plugin_id: str
    version_id: str | None
    reporter_user_id: str
    category: str
    description: str
    status: str
    reviewer_user_id: str | None
    resolution_note: str | None
    created_at: datetime
    updated_at: datetime


class PluginReportListResponse(BaseModel):
    items: list[PluginReportResponse]
    page: int
    page_size: int
    total: int


class PluginReportReviewRequest(BaseModel):
    status: Literal["acknowledged", "resolved", "dismissed"]
    resolution_note: str = Field(min_length=1, max_length=2_000)

    @field_validator("resolution_note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return _strip(value)


class PluginVersionResponse(BaseModel):
    id: str
    plugin_id: str
    semver: str
    status: PluginVersionStatus
    signing_key_id: str
    signing_key_fingerprint: str
    manifest_json: dict | None
    manifest_sha256: str | None
    protocol_min: int
    protocol_max: int
    host_min: str
    host_max: str
    requested_capabilities: list[str]
    approved_capabilities: list[str]
    risk_tier: str
    release_notes: str
    source_review_mode: str
    review_policy_version: str | None
    platform_key_id: str | None
    platform_public_key_base64: str | None
    platform_signature_base64: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    finalized_at: datetime | None
    published_at: datetime | None
    remediation_deadline_at: datetime | None = None
    artifacts: list[PluginArtifactResponse] = Field(default_factory=list)


class PluginProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    owner_user_id: str
    linked_third_party_app_id: str | None
    name: str
    summary: str
    description: str
    category: str
    tags: list[str]
    website_url: str | None
    privacy_policy_url: str | None
    source_url: str | None
    status: PluginStatus
    version: int
    created_at: datetime
    updated_at: datetime


class PluginProjectDetailResponse(PluginProjectResponse):
    versions: list[PluginVersionResponse] = Field(default_factory=list)


class PluginProjectListResponse(BaseModel):
    items: list[PluginProjectResponse]
    page: int
    page_size: int
    total: int


class UploadSessionCreateRequest(BaseModel):
    architecture: PluginArchitecture
    artifact_filename: str = Field(default="plugin.pdpkg", min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)

    @field_validator("artifact_filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        normalized = _strip(value)
        if "/" in normalized or "\\" in normalized or normalized != "plugin.pdpkg":
            raise ValueError("插件制品文件名必须为 plugin.pdpkg")
        return normalized

    @field_validator("sha256")
    @classmethod
    def normalize_sha256(cls, value: str) -> str:
        normalized = _strip(value).lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("sha256 必须是 64 位十六进制摘要")
        return normalized


class UploadSessionResponse(BaseModel):
    id: str
    plugin_version_id: str
    artifact_id: str
    architecture: PluginArchitecture
    expected_size_bytes: int
    expected_sha256: str
    status: str
    expires_at: datetime
    upload_url: str


class ArtifactUploadResponse(BaseModel):
    artifact_id: str
    status: Literal["uploaded"]
    size_bytes: int
    sha256: str


class PublicPluginArtifactResponse(BaseModel):
    architecture: PluginArchitecture
    size_bytes: int
    sha256: str
    artifact_filename: str


class PublicPluginVersionResponse(BaseModel):
    version_id: str
    plugin_slug: str
    semver: str
    status: Literal["published"]
    manifest_json: dict
    manifest_sha256: str
    signing_key_fingerprint: str
    protocol_min: int
    protocol_max: int
    host_min: str
    host_max: str
    approved_capabilities: list[str]
    risk_tier: str
    review_policy_version: str
    platform_key_id: str
    platform_public_key_base64: str
    platform_signature_base64: str
    platform_signature_payload: dict
    published_at: datetime
    artifacts: list[PublicPluginArtifactResponse]


class PublicPluginDetailResponse(BaseModel):
    slug: str
    name: str
    developer_name: str
    summary: str
    description: str
    category: str
    tags: list[str]
    website_url: str | None
    privacy_policy_url: str | None
    source_url: str | None
    versions: list[PublicPluginVersionResponse]


class PublicPluginCatalogItem(BaseModel):
    slug: str
    name: str
    developer_name: str
    summary: str
    category: str
    tags: list[str]
    latest_version: str
    risk_tier: str
    review_policy_version: str
    published_at: datetime
    architectures: list[PluginArchitecture]


class PublicPluginCatalogResponse(BaseModel):
    items: list[PublicPluginCatalogItem]
    page: int
    page_size: int
    total: int


class DownloadTicketRequest(BaseModel):
    architecture: PluginArchitecture
    semver: str = Field(min_length=5, max_length=32)

    @field_validator("semver")
    @classmethod
    def validate_semver(cls, value: str) -> str:
        normalized = _strip(value)
        if not _SEMVER_PATTERN.fullmatch(normalized):
            raise ValueError("插件版本必须是严格 SemVer x.y.z")
        return normalized


class DownloadTicketResponse(BaseModel):
    download_url: str
    expires_at: datetime
    artifact_sha256: str
    artifact_size_bytes: int


class PluginInstallEventRequest(BaseModel):
    event_id: str = Field(min_length=16, max_length=64)
    plugin_slug: str = Field(min_length=3, max_length=128)
    semver: str = Field(min_length=5, max_length=32)
    architecture: PluginArchitecture
    source: Literal["market_reviewed", "local_unreviewed"]
    kind: Literal[
        "installed",
        "upgraded",
        "rolled_back",
        "enabled",
        "disabled",
        "uninstalled",
        "download_failed",
    ]
    result: Literal["success", "failure"] = "success"
    client_version: str | None = Field(default=None, max_length=32)

    @field_validator("event_id", "plugin_slug", "semver")
    @classmethod
    def normalize_event_values(cls, value: str) -> str:
        return _strip(value)


class PluginInstallEventResponse(BaseModel):
    accepted: bool
    event_id: str


class PluginBrokerAuthorizationRequest(BaseModel):
    semver: str = Field(min_length=5, max_length=32)
    capability: Literal[
        "api:profile:read",
        "api:hash:read",
        "api:verification:submit",
    ]

    @field_validator("semver")
    @classmethod
    def validate_semver(cls, value: str) -> str:
        normalized = _strip(value)
        if not _SEMVER_PATTERN.fullmatch(normalized):
            raise ValueError("插件版本必须是严格 SemVer x.y.z")
        return normalized


class PluginBrokerAuthorizationResponse(BaseModel):
    allowed: Literal[True]
    plugin_slug: str
    semver: str
    capability: str
    scope: str
    linked_application_id: str


class PluginRevocationResponse(BaseModel):
    id: str
    scope: Literal["plugin", "version", "signing_key"]
    plugin_slug: str | None
    semver: str | None
    signing_key_fingerprint: str | None
    reason_code: str
    affects_historical_versions: bool
    effective_at: datetime
    batch_id: str
    platform_key_id: str
    platform_public_key_base64: str
    platform_signature_base64: str
    platform_signature_payload: dict


class PluginRevocationListResponse(BaseModel):
    generated_at: datetime
    policy_version: str
    items: list[PluginRevocationResponse]
