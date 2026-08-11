from __future__ import annotations

import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.reauthentication_grant import ReauthenticationPurpose
from password_detective.db.models.setting_version import SettingVersionStatus, SystemSettingVersion
from password_detective.db.models.system_setting import SystemSetting
from password_detective.modules.admin.setting_schemas import (
    OperationalSettingsSnapshot,
    SettingDifference,
    SettingVersionCreateRequest,
    SettingVersionDetail,
    SettingVersionListResponse,
    SettingVersionMutationResponse,
    SettingVersionPublishRequest,
    SettingVersionRollbackRequest,
    SettingVersionSummary,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.auth.reauthentication import consume_reauthentication_grant
from password_detective.modules.reputation.levels import rebuild_all_level_profiles


def _snapshot_hash(snapshot: OperationalSettingsSnapshot) -> str:
    payload = json.dumps(snapshot.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _published(db: Session, *, lock: bool = False) -> SystemSettingVersion | None:
    query = (
        select(SystemSettingVersion)
        .where(SystemSettingVersion.status == SettingVersionStatus.PUBLISHED)
        .order_by(SystemSettingVersion.published_at.desc(), SystemSettingVersion.created_at.desc())
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def _summary(record: SystemSettingVersion) -> SettingVersionSummary:
    return SettingVersionSummary(
        id=record.id,
        status=record.status,
        schema_version=record.schema_version,
        snapshot_hash=record.snapshot_hash,
        base_version_id=record.base_version_id,
        rollback_of_id=record.rollback_of_id,
        reason_code=record.reason_code,
        created_by=record.created_by,
        published_by=record.published_by,
        created_at=record.created_at,
        published_at=record.published_at,
        effective_at=record.effective_at,
    )


def _differences(
    snapshot: OperationalSettingsSnapshot,
    base: OperationalSettingsSnapshot | None,
) -> list[SettingDifference]:
    current = snapshot.model_dump(mode="json")
    previous = base.model_dump(mode="json") if base else {}
    return [
        SettingDifference(key=key, previous=previous.get(key), current=value)
        for key, value in current.items()
        if previous.get(key) != value
    ]


def _detail(db: Session, record: SystemSettingVersion) -> SettingVersionDetail:
    snapshot = OperationalSettingsSnapshot.model_validate(record.snapshot_json)
    base_record = (
        db.get(SystemSettingVersion, record.base_version_id) if record.base_version_id else None
    )
    base = (
        OperationalSettingsSnapshot.model_validate(base_record.snapshot_json)
        if base_record is not None
        else None
    )
    return SettingVersionDetail(
        **_summary(record).model_dump(), snapshot=snapshot, differences=_differences(snapshot, base)
    )


def list_setting_versions(db: Session, *, page: int, page_size: int) -> SettingVersionListResponse:
    total = db.scalar(select(func.count()).select_from(SystemSettingVersion)) or 0
    records = db.scalars(
        select(SystemSettingVersion)
        .order_by(SystemSettingVersion.created_at.desc(), SystemSettingVersion.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    current = _published(db)
    return SettingVersionListResponse(
        items=[_summary(record) for record in records],
        page=page,
        page_size=page_size,
        total=total,
        published_version_id=current.id if current else None,
    )


def get_setting_version(db: Session, version_id: str) -> SettingVersionDetail:
    record = db.get(SystemSettingVersion, version_id)
    if record is None:
        raise AppError("admin.setting_version_not_found", "配置版本不存在", status_code=404)
    return _detail(db, record)


def create_setting_version(
    db: Session,
    *,
    payload: SettingVersionCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> SettingVersionMutationResponse:
    current = _published(db)
    current_id = current.id if current else None
    if payload.expected_base_version_id != current_id:
        raise AppError(
            "admin.setting_base_conflict",
            "当前已发布配置发生变化，请刷新后重新创建草稿",
            status_code=409,
            details={"published_version_id": current_id},
        )
    if current and current.snapshot_hash == _snapshot_hash(payload.snapshot):
        raise AppError("admin.setting_no_changes", "配置内容没有变化", status_code=409)
    record = SystemSettingVersion(
        status=SettingVersionStatus.DRAFT,
        snapshot_json=payload.snapshot.model_dump(mode="json"),
        snapshot_hash=_snapshot_hash(payload.snapshot),
        base_version_id=current_id,
        created_by=principal.user.id,
        reason_code=payload.reason_code.value,
    )
    db.add(record)
    db.flush()
    audit = write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.settings.draft_created",
        target_type="system_setting_version",
        target_id=record.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "base_version_id": current_id,
            "snapshot_hash": record.snapshot_hash,
            "reason_code": record.reason_code,
        },
    )
    db.commit()
    db.refresh(record)
    return SettingVersionMutationResponse(
        version=_detail(db, record), audit_id=audit.id, request_id=context.request_id
    )


def _consume_settings_grant(db: Session, *, token: str, principal: Principal) -> None:
    grant = consume_reauthentication_grant(
        db,
        raw_token=token,
        user_id=principal.user.id,
        session_family_id=principal.session_family_id,
        expected_purpose=ReauthenticationPurpose.ADMIN_SETTINGS_GOVERNANCE,
    )
    if not grant.mfa_verified:
        raise AppError(
            "auth.mfa_reauthentication_required", "配置发布需要完成 TOTP 再认证", status_code=403
        )


def _apply_snapshot(
    db: Session,
    *,
    snapshot: OperationalSettingsSnapshot,
    actor_id: str,
) -> None:
    now = utc_now()
    for key, value in snapshot.model_dump(mode="json").items():
        record = db.get(SystemSetting, key)
        if record is None:
            db.add(
                SystemSetting(
                    key=key,
                    value_json={"value": value},
                    version=1,
                    updated_by=actor_id,
                    updated_at=now,
                )
            )
        else:
            record.value_json = {"value": value}
            record.version += 1
            record.updated_by = actor_id
            record.updated_at = now


def publish_setting_version(
    db: Session,
    *,
    version_id: str,
    payload: SettingVersionPublishRequest,
    principal: Principal,
    context: ClientContext,
) -> SettingVersionMutationResponse:
    record = db.scalar(
        select(SystemSettingVersion).where(SystemSettingVersion.id == version_id).with_for_update()
    )
    if record is None:
        raise AppError("admin.setting_version_not_found", "配置版本不存在", status_code=404)
    if record.status != SettingVersionStatus.DRAFT:
        raise AppError("admin.setting_version_not_draft", "仅草稿版本可以发布", status_code=409)
    current = _published(db, lock=True)
    current_id = current.id if current else None
    if payload.expected_published_version_id != current_id or record.base_version_id != current_id:
        raise AppError(
            "admin.setting_publish_conflict",
            "已发布配置发生变化，请基于最新版本重新创建草稿",
            status_code=409,
            details={"published_version_id": current_id},
        )
    _consume_settings_grant(db, token=payload.reauth_token, principal=principal)
    now = utc_now()
    if current:
        current.status = SettingVersionStatus.SUPERSEDED
    record.status = SettingVersionStatus.PUBLISHED
    record.published_by = principal.user.id
    record.published_at = now
    record.effective_at = now
    record.reason_code = payload.reason_code.value
    snapshot = OperationalSettingsSnapshot.model_validate(record.snapshot_json)
    _apply_snapshot(db, snapshot=snapshot, actor_id=principal.user.id)
    db.flush()
    rebuilt_level_profiles = rebuild_all_level_profiles(db)
    audit = write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.settings.published",
        target_type="system_setting_version",
        target_id=record.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "previous_version_id": current_id,
            "snapshot_hash": record.snapshot_hash,
            "reason_code": record.reason_code,
            "rebuilt_level_profiles": rebuilt_level_profiles,
        },
    )
    db.commit()
    db.refresh(record)
    return SettingVersionMutationResponse(
        version=_detail(db, record), audit_id=audit.id, request_id=context.request_id
    )


def rollback_setting_version(
    db: Session,
    *,
    version_id: str,
    payload: SettingVersionRollbackRequest,
    principal: Principal,
    context: ClientContext,
) -> SettingVersionMutationResponse:
    target = db.get(SystemSettingVersion, version_id)
    if target is None or target.published_at is None:
        raise AppError(
            "admin.setting_rollback_target_invalid", "只能回滚到历史已发布版本", status_code=409
        )
    current = _published(db, lock=True)
    current_id = current.id if current else None
    if current_id != payload.expected_published_version_id:
        raise AppError(
            "admin.setting_rollback_conflict",
            "已发布配置发生变化，请刷新后重试",
            status_code=409,
            details={"published_version_id": current_id},
        )
    if current_id == target.id:
        raise AppError("admin.setting_no_changes", "目标版本已经生效", status_code=409)
    _consume_settings_grant(db, token=payload.reauth_token, principal=principal)
    now = utc_now()
    if current:
        current.status = SettingVersionStatus.SUPERSEDED
    record = SystemSettingVersion(
        status=SettingVersionStatus.PUBLISHED,
        snapshot_json=target.snapshot_json,
        snapshot_hash=target.snapshot_hash,
        base_version_id=current_id,
        rollback_of_id=target.id,
        created_by=principal.user.id,
        published_by=principal.user.id,
        reason_code=payload.reason_code.value,
        published_at=now,
        effective_at=now,
    )
    db.add(record)
    db.flush()
    snapshot = OperationalSettingsSnapshot.model_validate(record.snapshot_json)
    _apply_snapshot(db, snapshot=snapshot, actor_id=principal.user.id)
    db.flush()
    rebuilt_level_profiles = rebuild_all_level_profiles(db)
    audit = write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.settings.rolled_back",
        target_type="system_setting_version",
        target_id=record.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "previous_version_id": current_id,
            "rollback_of_id": target.id,
            "snapshot_hash": record.snapshot_hash,
            "reason_code": record.reason_code,
            "rebuilt_level_profiles": rebuilt_level_profiles,
        },
    )
    db.commit()
    db.refresh(record)
    return SettingVersionMutationResponse(
        version=_detail(db, record), audit_id=audit.id, request_id=context.request_id
    )
