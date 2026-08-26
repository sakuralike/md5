from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.system_setting import SystemSetting
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.desktop_plugins.schemas import (
    PluginReviewPolicyResponse,
    PluginReviewPolicyUpdate,
)
from password_detective.modules.desktop_plugins.static_review import STATIC_REVIEW_POLICY_VERSION

PLUGIN_REVIEW_POLICY_KEY = "desktop_plugin_review_policy"
DYNAMIC_REVIEW_ENGINE_VERSION = "desktop-plugin-dynamic-review-v1"


@dataclass(frozen=True)
class PluginReviewPolicy:
    version: int = 0
    static_lease_seconds: int = 300
    dynamic_lease_seconds: int = 300
    task_token_seconds: int = 900
    maximum_static_attempts: int = 3
    maximum_dynamic_attempts: int = 3
    runner_offline_seconds: int = 90
    revocation_refresh_hours: int = 6
    revocation_max_stale_hours: int = 168
    dynamic_review_enabled: bool = False
    llm_review_enabled: bool = True
    updated_at: object | None = None
    updated_by: str | None = None

    @property
    def policy_version(self) -> str:
        return f"desktop-plugin-review-policy-v{self.version + 1}"


def get_current_review_policy(db: Session) -> PluginReviewPolicy:
    record = db.get(SystemSetting, PLUGIN_REVIEW_POLICY_KEY)
    if record is None:
        return PluginReviewPolicy()
    try:
        payload = PluginReviewPolicyUpdate.model_validate(
            {"version": record.version, **record.value_json.get("value", {})}
        )
    except (TypeError, ValidationError):
        return PluginReviewPolicy()
    return PluginReviewPolicy(
        **payload.model_dump(),
        updated_at=record.updated_at,
        updated_by=record.updated_by,
    )


def review_policy_response(policy: PluginReviewPolicy) -> PluginReviewPolicyResponse:
    return PluginReviewPolicyResponse(
        **{
            key: value
            for key, value in policy.__dict__.items()
            if key not in {"updated_at", "updated_by"}
        },
        policy_version=policy.policy_version,
        static_engine_version=STATIC_REVIEW_POLICY_VERSION,
        dynamic_engine_version=DYNAMIC_REVIEW_ENGINE_VERSION,
        updated_at=policy.updated_at,
        updated_by=policy.updated_by,
    )


def save_review_policy(
    db: Session,
    *,
    payload: PluginReviewPolicyUpdate,
    principal: Principal,
    context: ClientContext,
) -> PluginReviewPolicyResponse:
    record = db.get(SystemSetting, PLUGIN_REVIEW_POLICY_KEY)
    current_version = record.version if record is not None else 0
    if payload.version != current_version:
        raise AppError(
            "desktop_plugin.review_policy_version_conflict",
            "插件审核策略已被其他请求修改",
            status_code=409,
            details={"current_version": current_version},
        )
    now = utc_now()
    values = payload.model_dump(exclude={"version"}, mode="json")
    if record is None:
        record = SystemSetting(
            key=PLUGIN_REVIEW_POLICY_KEY,
            value_json={"value": values},
            version=1,
            updated_by=principal.user.id,
            updated_at=now,
        )
        db.add(record)
    else:
        record.value_json = {"value": values}
        record.version += 1
        record.updated_by = principal.user.id
        record.updated_at = now
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="desktop_plugin.review_policy.saved",
        target_type="desktop_plugin_review_policy",
        target_id="current",
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"version": record.version},
    )
    db.commit()
    return review_policy_response(get_current_review_policy(db))
