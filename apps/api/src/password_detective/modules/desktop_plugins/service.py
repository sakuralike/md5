from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.security import hash_opaque_token
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.desktop_plugin import (
    DesktopPlugin,
    DesktopPluginArtifact,
    DesktopPluginArtifactStatus,
    DesktopPluginArtifactZone,
    DesktopPluginDownloadTicket,
    DesktopPluginRevocation,
    DesktopPluginSigningKey,
    DesktopPluginSigningKeyStatus,
    DesktopPluginStatus,
    DesktopPluginUploadSession,
    DesktopPluginUploadSessionStatus,
    DesktopPluginVersion,
    DesktopPluginVersionStatus,
)
from password_detective.db.models.reauthentication_grant import ReauthenticationPurpose
from password_detective.db.models.third_party_app import ThirdPartyApp, ThirdPartyAppStatus
from password_detective.db.models.user import User
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.auth.reauthentication import consume_reauthentication_grant
from password_detective.modules.desktop_plugins.package_verifier import verify_plugin_package
from password_detective.modules.desktop_plugins.schemas import (
    ArtifactUploadResponse,
    DownloadTicketResponse,
    PluginArtifactResponse,
    PluginProjectCreateRequest,
    PluginProjectDetailResponse,
    PluginProjectListResponse,
    PluginProjectResponse,
    PluginProjectUpdateRequest,
    PluginRevocationListResponse,
    PluginRevocationResponse,
    PluginVersionCreateRequest,
    PluginVersionFinalizeRequest,
    PluginVersionResponse,
    PublicPluginArtifactResponse,
    PublicPluginCatalogItem,
    PublicPluginCatalogResponse,
    PublicPluginDetailResponse,
    PublicPluginVersionResponse,
    SigningKeyCreateRequest,
    SigningKeyListResponse,
    SigningKeyResponse,
    UploadSessionCreateRequest,
    UploadSessionResponse,
)
from password_detective.modules.desktop_plugins.storage import DesktopPluginStorage

_REVOCATION_POLICY_VERSION = "desktop-plugin-control-plane-v1"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _require_verified(principal: Principal) -> None:
    if not principal.user.email_verified:
        raise AppError(
            "desktop_plugin.email_verification_required",
            "完成邮箱验证后才能管理插件",
            status_code=403,
        )


def _write_audit(
    db: Session,
    *,
    action: str,
    target_type: str,
    target_id: str,
    actor_id: str | None,
    context: ClientContext | None,
    details: dict | None = None,
) -> None:
    write_audit_log(
        db,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        result="success",
        ip_prefix=context.ip_prefix if context else None,
        request_id=context.request_id if context else None,
        details=details or {},
    )


def _owned_project(
    db: Session, *, plugin_id: str, owner_id: str, lock: bool = False
) -> DesktopPlugin:
    statement = select(DesktopPlugin).where(
        DesktopPlugin.id == plugin_id,
        DesktopPlugin.owner_user_id == owner_id,
    )
    if lock:
        statement = statement.with_for_update()
    plugin = db.scalar(statement)
    if plugin is None:
        raise AppError("desktop_plugin.not_found", "插件项目不存在", status_code=404)
    return plugin


def _owned_version(
    db: Session, *, version_id: str, owner_id: str, lock: bool = False
) -> tuple[DesktopPlugin, DesktopPluginVersion]:
    statement = (
        select(DesktopPlugin, DesktopPluginVersion)
        .join(DesktopPluginVersion, DesktopPluginVersion.plugin_id == DesktopPlugin.id)
        .where(
            DesktopPluginVersion.id == version_id,
            DesktopPlugin.owner_user_id == owner_id,
        )
    )
    if lock:
        statement = statement.with_for_update()
    row = db.execute(statement).one_or_none()
    if row is None:
        raise AppError("desktop_plugin.version_not_found", "插件版本不存在", status_code=404)
    return row[0], row[1]


def _validate_linked_app(db: Session, *, app_id: str | None, owner_id: str) -> None:
    if app_id is None:
        return
    app = db.scalar(
        select(ThirdPartyApp).where(
            ThirdPartyApp.id == app_id,
            ThirdPartyApp.submitted_by_user_id == owner_id,
            ThirdPartyApp.status == ThirdPartyAppStatus.APPROVED,
        )
    )
    if app is None:
        raise AppError(
            "desktop_plugin.invalid_linked_application",
            "关联的第三方应用不存在、未批准或不属于当前开发者",
            status_code=422,
        )


def _artifact_response(artifact: DesktopPluginArtifact) -> PluginArtifactResponse:
    return PluginArtifactResponse.model_validate(artifact)


def _version_response(db: Session, version: DesktopPluginVersion) -> PluginVersionResponse:
    artifacts = list(
        db.scalars(
            select(DesktopPluginArtifact)
            .where(DesktopPluginArtifact.plugin_version_id == version.id)
            .order_by(DesktopPluginArtifact.architecture)
        ).all()
    )
    return PluginVersionResponse(
        id=version.id,
        plugin_id=version.plugin_id,
        semver=version.semver,
        status=version.status.value,
        signing_key_id=version.signing_key_id,
        signing_key_fingerprint=version.signing_key_fingerprint,
        manifest_json=version.manifest_json,
        manifest_sha256=version.manifest_sha256,
        protocol_min=version.protocol_min,
        protocol_max=version.protocol_max,
        host_min=version.host_min,
        host_max=version.host_max,
        requested_capabilities=list(version.requested_capabilities),
        approved_capabilities=list(version.approved_capabilities),
        risk_tier=version.risk_tier,
        release_notes=version.release_notes,
        source_review_mode=version.source_review_mode,
        review_policy_version=version.review_policy_version,
        platform_key_id=version.platform_key_id,
        platform_signature_base64=version.platform_signature_base64,
        version=version.version,
        created_at=version.created_at,
        updated_at=version.updated_at,
        finalized_at=version.finalized_at,
        published_at=version.published_at,
        artifacts=[_artifact_response(artifact) for artifact in artifacts],
    )


def _project_response(plugin: DesktopPlugin) -> PluginProjectResponse:
    return PluginProjectResponse.model_validate(plugin)


def _project_detail(db: Session, plugin: DesktopPlugin) -> PluginProjectDetailResponse:
    versions = list(
        db.scalars(
            select(DesktopPluginVersion)
            .where(DesktopPluginVersion.plugin_id == plugin.id)
            .order_by(DesktopPluginVersion.created_at.desc())
        ).all()
    )
    return PluginProjectDetailResponse(
        **_project_response(plugin).model_dump(),
        versions=[_version_response(db, version) for version in versions],
    )


def create_project(
    db: Session,
    *,
    payload: PluginProjectCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> PluginProjectDetailResponse:
    _require_verified(principal)
    _validate_linked_app(db, app_id=payload.linked_third_party_app_id, owner_id=principal.user.id)
    if db.scalar(select(DesktopPlugin.id).where(DesktopPlugin.slug == payload.slug)):
        raise AppError("desktop_plugin.slug_conflict", "插件 ID 已存在", status_code=409)
    plugin = DesktopPlugin(
        owner_user_id=principal.user.id,
        **payload.model_dump(),
    )
    db.add(plugin)
    db.flush()
    _write_audit(
        db,
        action="desktop_plugin.project.created",
        target_type="desktop_plugin",
        target_id=plugin.id,
        actor_id=principal.user.id,
        context=context,
        details={"slug": plugin.slug},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("desktop_plugin.slug_conflict", "插件 ID 已存在", status_code=409) from exc
    db.refresh(plugin)
    return _project_detail(db, plugin)


def list_projects(
    db: Session, *, principal: Principal, page: int, page_size: int
) -> PluginProjectListResponse:
    _require_verified(principal)
    base = select(DesktopPlugin).where(DesktopPlugin.owner_user_id == principal.user.id)
    total = db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    items = list(
        db.scalars(
            base.order_by(DesktopPlugin.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return PluginProjectListResponse(
        items=[_project_response(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_project(
    db: Session, *, plugin_id: str, principal: Principal
) -> PluginProjectDetailResponse:
    _require_verified(principal)
    return _project_detail(db, _owned_project(db, plugin_id=plugin_id, owner_id=principal.user.id))


def update_project(
    db: Session,
    *,
    plugin_id: str,
    payload: PluginProjectUpdateRequest,
    principal: Principal,
    context: ClientContext,
) -> PluginProjectDetailResponse:
    _require_verified(principal)
    plugin = _owned_project(db, plugin_id=plugin_id, owner_id=principal.user.id, lock=True)
    if plugin.status != DesktopPluginStatus.DRAFT:
        raise AppError(
            "desktop_plugin.project_not_editable",
            "非草稿插件项目不能直接修改公开元数据",
            status_code=409,
        )
    if plugin.version != payload.version:
        raise AppError(
            "desktop_plugin.version_conflict",
            "插件项目已被其他请求修改",
            status_code=409,
            details={"current_version": plugin.version},
        )
    changes = payload.model_dump(exclude={"version"}, exclude_unset=True)
    if "linked_third_party_app_id" in changes:
        _validate_linked_app(
            db, app_id=changes["linked_third_party_app_id"], owner_id=principal.user.id
        )
    for key, value in changes.items():
        setattr(plugin, key, value)
    plugin.version += 1
    _write_audit(
        db,
        action="desktop_plugin.project.updated",
        target_type="desktop_plugin",
        target_id=plugin.id,
        actor_id=principal.user.id,
        context=context,
        details={"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(plugin)
    return _project_detail(db, plugin)


def _decode_public_key(value: str) -> tuple[bytes, str]:
    try:
        raw = base64.b64decode(value, validate=True)
        Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, TypeError) as exc:
        raise AppError(
            "desktop_plugin.invalid_signing_key",
            "签名公钥必须是 32 字节 Ed25519 公钥的 Base64",
            status_code=422,
        ) from exc
    return raw, hashlib.sha256(raw).hexdigest()


def register_signing_key(
    db: Session,
    *,
    payload: SigningKeyCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> SigningKeyResponse:
    _require_verified(principal)
    _, fingerprint = _decode_public_key(payload.public_key_base64)
    if db.scalar(
        select(DesktopPluginSigningKey.id).where(
            or_(
                DesktopPluginSigningKey.key_id == payload.key_id,
                DesktopPluginSigningKey.fingerprint == fingerprint,
            )
        )
    ):
        raise AppError("desktop_plugin.signing_key_conflict", "签名密钥已登记", status_code=409)
    consume_reauthentication_grant(
        db,
        raw_token=payload.reauth_token,
        user_id=principal.user.id,
        session_family_id=principal.session_family_id,
        expected_purpose=ReauthenticationPurpose.DESKTOP_PLUGIN_SIGNING_KEY,
    )
    key = DesktopPluginSigningKey(
        owner_user_id=principal.user.id,
        key_id=payload.key_id,
        public_key_base64=payload.public_key_base64,
        fingerprint=fingerprint,
    )
    db.add(key)
    db.flush()
    _write_audit(
        db,
        action="desktop_plugin.signing_key.registered",
        target_type="desktop_plugin_signing_key",
        target_id=key.id,
        actor_id=principal.user.id,
        context=context,
        details={"key_id": key.key_id, "fingerprint": fingerprint},
    )
    db.commit()
    db.refresh(key)
    return SigningKeyResponse.model_validate(key)


def list_signing_keys(db: Session, *, principal: Principal) -> SigningKeyListResponse:
    _require_verified(principal)
    keys = list(
        db.scalars(
            select(DesktopPluginSigningKey)
            .where(DesktopPluginSigningKey.owner_user_id == principal.user.id)
            .order_by(DesktopPluginSigningKey.created_at.desc())
        ).all()
    )
    return SigningKeyListResponse(items=[SigningKeyResponse.model_validate(key) for key in keys])


def revoke_signing_key(
    db: Session,
    *,
    key_id: str,
    reauth_token: str,
    principal: Principal,
    context: ClientContext,
) -> SigningKeyResponse:
    _require_verified(principal)
    key = db.scalar(
        select(DesktopPluginSigningKey)
        .where(
            DesktopPluginSigningKey.id == key_id,
            DesktopPluginSigningKey.owner_user_id == principal.user.id,
        )
        .with_for_update()
    )
    if key is None:
        raise AppError("desktop_plugin.signing_key_not_found", "签名密钥不存在", status_code=404)
    if key.status == DesktopPluginSigningKeyStatus.REVOKED:
        raise AppError(
            "desktop_plugin.signing_key_already_revoked", "签名密钥已撤销", status_code=409
        )
    consume_reauthentication_grant(
        db,
        raw_token=reauth_token,
        user_id=principal.user.id,
        session_family_id=principal.session_family_id,
        expected_purpose=ReauthenticationPurpose.DESKTOP_PLUGIN_SIGNING_KEY,
    )
    key.status = DesktopPluginSigningKeyStatus.REVOKED
    key.revoked_at = utc_now()
    _write_audit(
        db,
        action="desktop_plugin.signing_key.revoked",
        target_type="desktop_plugin_signing_key",
        target_id=key.id,
        actor_id=principal.user.id,
        context=context,
        details={"fingerprint": key.fingerprint},
    )
    db.commit()
    db.refresh(key)
    return SigningKeyResponse.model_validate(key)


def create_version(
    db: Session,
    *,
    plugin_id: str,
    payload: PluginVersionCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> PluginVersionResponse:
    _require_verified(principal)
    plugin = _owned_project(db, plugin_id=plugin_id, owner_id=principal.user.id)
    if plugin.status not in {DesktopPluginStatus.DRAFT, DesktopPluginStatus.ACTIVE}:
        raise AppError(
            "desktop_plugin.project_unavailable",
            "插件项目当前不能创建版本",
            status_code=409,
        )
    key = db.scalar(
        select(DesktopPluginSigningKey).where(
            DesktopPluginSigningKey.id == payload.signing_key_id,
            DesktopPluginSigningKey.owner_user_id == principal.user.id,
            DesktopPluginSigningKey.status == DesktopPluginSigningKeyStatus.ACTIVE,
        )
    )
    if key is None:
        raise AppError(
            "desktop_plugin.invalid_signing_key",
            "签名密钥不存在、已撤销或不属于当前开发者",
            status_code=422,
        )
    if db.scalar(
        select(DesktopPluginVersion.id).where(
            DesktopPluginVersion.plugin_id == plugin.id,
            DesktopPluginVersion.semver == payload.semver,
        )
    ):
        raise AppError("desktop_plugin.version_conflict", "同一插件版本已存在", status_code=409)
    version = DesktopPluginVersion(
        plugin_id=plugin.id,
        signing_key_fingerprint=key.fingerprint,
        **payload.model_dump(),
    )
    db.add(version)
    db.flush()
    _write_audit(
        db,
        action="desktop_plugin.version.created",
        target_type="desktop_plugin_version",
        target_id=version.id,
        actor_id=principal.user.id,
        context=context,
        details={"plugin_id": plugin.id, "semver": version.semver},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            "desktop_plugin.version_conflict", "同一插件版本已存在", status_code=409
        ) from exc
    db.refresh(version)
    return _version_response(db, version)


def create_upload_session(
    db: Session,
    settings: Settings,
    *,
    version_id: str,
    payload: UploadSessionCreateRequest,
    principal: Principal,
    context: ClientContext,
    upload_url_builder,
) -> UploadSessionResponse:
    _require_verified(principal)
    _, version = _owned_version(db, version_id=version_id, owner_id=principal.user.id, lock=True)
    if version.status not in {
        DesktopPluginVersionStatus.DRAFT,
        DesktopPluginVersionStatus.UPLOADING,
    }:
        raise AppError(
            "desktop_plugin.version_not_uploadable",
            "插件版本已冻结，不能替换制品",
            status_code=409,
        )
    if payload.size_bytes > settings.desktop_plugin_max_package_bytes:
        raise AppError("desktop_plugin.upload_too_large", "插件制品超过允许的大小", status_code=413)
    storage = DesktopPluginStorage(settings)
    existing = db.scalar(
        select(DesktopPluginArtifact).where(
            DesktopPluginArtifact.plugin_version_id == version.id,
            DesktopPluginArtifact.architecture == payload.architecture,
        )
    )
    if existing is not None:
        sessions = list(
            db.scalars(
                select(DesktopPluginUploadSession).where(
                    DesktopPluginUploadSession.artifact_id == existing.id
                )
            ).all()
        )
        for session in sessions:
            db.delete(session)
        if existing.storage_key:
            storage.quarantine_path(existing.storage_key).unlink(missing_ok=True)
        db.delete(existing)
        db.flush()
    raw_token = "plugin_upload_" + secrets.token_urlsafe(32)
    artifact = DesktopPluginArtifact(
        plugin_version_id=version.id,
        architecture=payload.architecture,
        artifact_filename=payload.artifact_filename,
        size_bytes=payload.size_bytes,
        sha256=payload.sha256,
    )
    db.add(artifact)
    db.flush()
    session = DesktopPluginUploadSession(
        plugin_version_id=version.id,
        artifact_id=artifact.id,
        token_hash=hash_opaque_token(raw_token),
        expected_size_bytes=payload.size_bytes,
        expected_sha256=payload.sha256,
        expires_at=utc_now() + timedelta(minutes=settings.desktop_plugin_upload_ttl_minutes),
    )
    db.add(session)
    db.flush()
    artifact.storage_key = storage.quarantine_key(version.id, payload.architecture, session.id)
    version.status = DesktopPluginVersionStatus.UPLOADING
    version.version += 1
    _write_audit(
        db,
        action="desktop_plugin.upload_session.created",
        target_type="desktop_plugin_upload_session",
        target_id=session.id,
        actor_id=principal.user.id,
        context=context,
        details={
            "plugin_version_id": version.id,
            "architecture": payload.architecture,
            "size_bytes": payload.size_bytes,
        },
    )
    db.commit()
    return UploadSessionResponse(
        id=session.id,
        plugin_version_id=session.plugin_version_id,
        artifact_id=artifact.id,
        architecture=payload.architecture,
        expected_size_bytes=session.expected_size_bytes,
        expected_sha256=session.expected_sha256,
        status=session.status.value,
        expires_at=session.expires_at,
        upload_url=upload_url_builder(session.id, raw_token),
    )


async def upload_artifact(
    db: Session,
    settings: Settings,
    *,
    session_id: str,
    raw_token: str,
    chunks,
    content_length: int | None,
) -> ArtifactUploadResponse:
    session = db.scalar(
        select(DesktopPluginUploadSession)
        .where(
            DesktopPluginUploadSession.id == session_id,
            DesktopPluginUploadSession.token_hash == hash_opaque_token(raw_token),
        )
        .with_for_update()
    )
    now = utc_now()
    if session is None:
        raise AppError("desktop_plugin.invalid_upload_token", "上传凭据无效", status_code=401)
    if session.status != DesktopPluginUploadSessionStatus.OPEN:
        raise AppError("desktop_plugin.upload_session_closed", "上传会话已关闭", status_code=409)
    if _aware(session.expires_at) <= now:
        session.status = DesktopPluginUploadSessionStatus.EXPIRED
        db.commit()
        raise AppError("desktop_plugin.upload_session_expired", "上传会话已过期", status_code=410)
    if content_length is not None and content_length != session.expected_size_bytes:
        raise AppError(
            "desktop_plugin.artifact_integrity_mismatch",
            "Content-Length 与上传会话声明不一致",
            status_code=422,
        )
    artifact = db.get(DesktopPluginArtifact, session.artifact_id)
    if artifact is None or not artifact.storage_key:
        raise AppError("desktop_plugin.artifact_missing", "上传制品记录不存在", status_code=404)
    storage = DesktopPluginStorage(settings)
    total = await storage.write_quarantine(
        key=artifact.storage_key,
        chunks=chunks,
        expected_size=session.expected_size_bytes,
        expected_sha256=session.expected_sha256,
    )
    session.status = DesktopPluginUploadSessionStatus.UPLOADED
    session.uploaded_at = now
    artifact.status = DesktopPluginArtifactStatus.QUARANTINED
    _write_audit(
        db,
        action="desktop_plugin.artifact.uploaded",
        target_type="desktop_plugin_artifact",
        target_id=artifact.id,
        actor_id=None,
        context=None,
        details={"plugin_version_id": session.plugin_version_id, "size_bytes": total},
    )
    db.commit()
    return ArtifactUploadResponse(
        artifact_id=artifact.id,
        status="uploaded",
        size_bytes=total,
        sha256=artifact.sha256,
    )


def finalize_version(
    db: Session,
    settings: Settings,
    *,
    version_id: str,
    payload: PluginVersionFinalizeRequest,
    principal: Principal,
    context: ClientContext,
) -> PluginVersionResponse:
    _require_verified(principal)
    plugin, version = _owned_version(
        db, version_id=version_id, owner_id=principal.user.id, lock=True
    )
    if version.status != DesktopPluginVersionStatus.UPLOADING:
        raise AppError(
            "desktop_plugin.version_not_finalizable",
            "插件版本不处于可冻结的上传状态",
            status_code=409,
        )
    if version.version != payload.version:
        raise AppError(
            "desktop_plugin.version_conflict",
            "插件版本已被其他请求修改",
            status_code=409,
            details={"current_version": version.version},
        )
    key = db.get(DesktopPluginSigningKey, version.signing_key_id)
    if (
        key is None
        or key.owner_user_id != principal.user.id
        or key.status != DesktopPluginSigningKeyStatus.ACTIVE
        or key.fingerprint != version.signing_key_fingerprint
    ):
        raise AppError(
            "desktop_plugin.invalid_signing_key",
            "签名密钥已撤销或与版本快照不一致",
            status_code=409,
        )
    artifacts = list(
        db.scalars(
            select(DesktopPluginArtifact)
            .where(DesktopPluginArtifact.plugin_version_id == version.id)
            .order_by(DesktopPluginArtifact.architecture)
            .with_for_update()
        ).all()
    )
    if not artifacts:
        raise AppError("desktop_plugin.artifact_required", "至少上传一个插件制品", status_code=422)
    sessions = {
        session.artifact_id: session
        for session in db.scalars(
            select(DesktopPluginUploadSession)
            .where(DesktopPluginUploadSession.plugin_version_id == version.id)
            .with_for_update()
        ).all()
    }
    storage = DesktopPluginStorage(settings)
    inspections = []
    for artifact in artifacts:
        session = sessions.get(artifact.id)
        if (
            session is None
            or session.status != DesktopPluginUploadSessionStatus.UPLOADED
            or artifact.status != DesktopPluginArtifactStatus.QUARANTINED
            or not artifact.storage_key
        ):
            raise AppError(
                "desktop_plugin.artifact_not_uploaded",
                "所有架构制品必须完成上传后才能冻结版本",
                status_code=409,
            )
        path = storage.quarantine_path(artifact.storage_key)
        if not path.is_file():
            raise AppError(
                "desktop_plugin.artifact_missing", "隔离区插件制品不存在", status_code=422
            )
        inspection = verify_plugin_package(
            path,
            architecture=artifact.architecture,
            project_slug=plugin.slug,
            semver=version.semver,
            signing_key_id=key.key_id,
            public_key_base64=key.public_key_base64,
            protocol_min=version.protocol_min,
            protocol_max=version.protocol_max,
            host_min=version.host_min,
            host_max=version.host_max,
            requested_capabilities=list(version.requested_capabilities),
            max_expanded_bytes=settings.desktop_plugin_max_expanded_bytes,
        )
        artifact.expanded_size_bytes = inspection.expanded_size_bytes
        artifact.developer_signature_base64 = inspection.signature_base64
        inspections.append(inspection)
    manifest_hashes = {inspection.manifest_sha256 for inspection in inspections}
    if len(manifest_hashes) != 1:
        raise AppError(
            "desktop_plugin.manifest_mismatch",
            "不同架构制品的插件清单不一致",
            status_code=422,
        )
    now = utc_now()
    version.manifest_json = inspections[0].manifest
    version.manifest_sha256 = inspections[0].manifest_sha256
    version.status = DesktopPluginVersionStatus.QUARANTINED
    version.finalized_at = now
    version.version += 1
    for session in sessions.values():
        session.status = DesktopPluginUploadSessionStatus.FINALIZED
        session.finalized_at = now
    _write_audit(
        db,
        action="desktop_plugin.version.finalized",
        target_type="desktop_plugin_version",
        target_id=version.id,
        actor_id=principal.user.id,
        context=context,
        details={
            "manifest_sha256": version.manifest_sha256,
            "artifacts": [artifact.sha256 for artifact in artifacts],
        },
    )
    db.commit()
    db.refresh(version)
    return _version_response(db, version)


def _parse_semver(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        return (-1, -1, -1)
    return int(parts[0]), int(parts[1]), int(parts[2])


def _host_compatible(minimum: str, maximum: str, current: str) -> bool:
    current_tuple = _parse_semver(current)
    if current_tuple < _parse_semver(minimum):
        return False
    if maximum.endswith(".x"):
        return current_tuple[0] == int(maximum[:-2])
    return current_tuple <= _parse_semver(maximum)


def _public_artifacts(
    db: Session, version_id: str, architecture: str | None = None
) -> list[DesktopPluginArtifact]:
    statement = select(DesktopPluginArtifact).where(
        DesktopPluginArtifact.plugin_version_id == version_id,
        DesktopPluginArtifact.status == DesktopPluginArtifactStatus.PUBLIC,
        DesktopPluginArtifact.zone == DesktopPluginArtifactZone.PUBLIC,
        DesktopPluginArtifact.public_storage_key.is_not(None),
    )
    if architecture:
        statement = statement.where(DesktopPluginArtifact.architecture == architecture)
    return list(db.scalars(statement.order_by(DesktopPluginArtifact.architecture)).all())


def _is_revoked(db: Session, *, plugin_id: str, version_id: str, signing_key_id: str) -> bool:
    return (
        db.scalar(
            select(DesktopPluginRevocation.id).where(
                DesktopPluginRevocation.effective_at <= utc_now(),
                or_(
                    DesktopPluginRevocation.plugin_id == plugin_id,
                    DesktopPluginRevocation.plugin_version_id == version_id,
                    (
                        (DesktopPluginRevocation.signing_key_id == signing_key_id)
                        & DesktopPluginRevocation.affects_historical_versions.is_(True)
                    ),
                ),
            )
        )
        is not None
    )


def _public_version_response(
    db: Session, version: DesktopPluginVersion
) -> PublicPluginVersionResponse | None:
    artifacts = _public_artifacts(db, version.id)
    if (
        version.status != DesktopPluginVersionStatus.PUBLISHED
        or version.manifest_json is None
        or version.manifest_sha256 is None
        or version.published_at is None
        or version.review_policy_version is None
        or version.platform_key_id is None
        or version.platform_signature_base64 is None
        or not artifacts
        or _is_revoked(
            db,
            plugin_id=version.plugin_id,
            version_id=version.id,
            signing_key_id=version.signing_key_id,
        )
    ):
        return None
    return PublicPluginVersionResponse(
        semver=version.semver,
        status="published",
        manifest_json=version.manifest_json,
        manifest_sha256=version.manifest_sha256,
        signing_key_fingerprint=version.signing_key_fingerprint,
        protocol_min=version.protocol_min,
        protocol_max=version.protocol_max,
        host_min=version.host_min,
        host_max=version.host_max,
        approved_capabilities=list(version.approved_capabilities),
        risk_tier=version.risk_tier,
        review_policy_version=version.review_policy_version,
        platform_key_id=version.platform_key_id,
        platform_signature_base64=version.platform_signature_base64,
        published_at=version.published_at,
        artifacts=[
            PublicPluginArtifactResponse(
                architecture=artifact.architecture,
                size_bytes=artifact.size_bytes,
                sha256=artifact.sha256,
                artifact_filename=artifact.artifact_filename,
            )
            for artifact in artifacts
        ],
    )


def list_public_catalog(
    db: Session,
    *,
    query: str | None,
    category: str | None,
    architecture: str,
    host_version: str,
    protocol_version: int,
    page: int,
    page_size: int,
) -> PublicPluginCatalogResponse:
    statement = (
        select(DesktopPlugin, User)
        .join(User, User.id == DesktopPlugin.owner_user_id)
        .where(DesktopPlugin.status == DesktopPluginStatus.ACTIVE)
    )
    if category:
        statement = statement.where(DesktopPlugin.category == category)
    rows = db.execute(statement.order_by(DesktopPlugin.updated_at.desc())).all()
    normalized_query = query.strip().lower() if query else None
    items: list[PublicPluginCatalogItem] = []
    for plugin, owner in rows:
        haystack = " ".join(
            [plugin.name, plugin.summary, " ".join(plugin.tags), owner.username]
        ).lower()
        if normalized_query and normalized_query not in haystack:
            continue
        versions = list(
            db.scalars(
                select(DesktopPluginVersion).where(
                    DesktopPluginVersion.plugin_id == plugin.id,
                    DesktopPluginVersion.status == DesktopPluginVersionStatus.PUBLISHED,
                    DesktopPluginVersion.protocol_min <= protocol_version,
                    DesktopPluginVersion.protocol_max >= protocol_version,
                )
            ).all()
        )
        compatible = [
            version
            for version in versions
            if _host_compatible(version.host_min, version.host_max, host_version)
            and _public_artifacts(db, version.id, architecture)
            and _public_version_response(db, version) is not None
        ]
        if not compatible:
            continue
        latest = max(compatible, key=lambda version: _parse_semver(version.semver))
        public = _public_version_response(db, latest)
        assert public is not None
        items.append(
            PublicPluginCatalogItem(
                slug=plugin.slug,
                name=plugin.name,
                summary=plugin.summary,
                category=plugin.category,
                tags=list(plugin.tags),
                latest_version=latest.semver,
                risk_tier=latest.risk_tier,
                review_policy_version=latest.review_policy_version or "",
                published_at=latest.published_at,
                architectures=[artifact.architecture for artifact in public.artifacts],
            )
        )
    items.sort(key=lambda item: (item.published_at, item.slug), reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    return PublicPluginCatalogResponse(
        items=items[start : start + page_size],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_public_plugin(db: Session, *, slug: str) -> PublicPluginDetailResponse:
    plugin = db.scalar(
        select(DesktopPlugin).where(
            DesktopPlugin.slug == slug,
            DesktopPlugin.status == DesktopPluginStatus.ACTIVE,
        )
    )
    if plugin is None:
        raise AppError("desktop_plugin.not_found", "插件不存在", status_code=404)
    versions = list(
        db.scalars(
            select(DesktopPluginVersion)
            .where(
                DesktopPluginVersion.plugin_id == plugin.id,
                DesktopPluginVersion.status == DesktopPluginVersionStatus.PUBLISHED,
            )
            .order_by(DesktopPluginVersion.published_at.desc())
        ).all()
    )
    public_versions = [
        response
        for version in versions
        if (response := _public_version_response(db, version)) is not None
    ]
    if not public_versions:
        raise AppError("desktop_plugin.not_found", "插件不存在", status_code=404)
    return PublicPluginDetailResponse(
        slug=plugin.slug,
        name=plugin.name,
        summary=plugin.summary,
        description=plugin.description,
        category=plugin.category,
        tags=list(plugin.tags),
        website_url=plugin.website_url,
        privacy_policy_url=plugin.privacy_policy_url,
        source_url=plugin.source_url,
        versions=public_versions,
    )


def get_public_version(db: Session, *, slug: str, semver: str) -> PublicPluginVersionResponse:
    row = db.execute(
        select(DesktopPluginVersion, DesktopPlugin)
        .join(DesktopPlugin, DesktopPlugin.id == DesktopPluginVersion.plugin_id)
        .where(
            DesktopPlugin.slug == slug,
            DesktopPlugin.status == DesktopPluginStatus.ACTIVE,
            DesktopPluginVersion.semver == semver,
            DesktopPluginVersion.status == DesktopPluginVersionStatus.PUBLISHED,
        )
    ).one_or_none()
    if row is None or (response := _public_version_response(db, row[0])) is None:
        raise AppError("desktop_plugin.version_not_found", "插件版本不存在", status_code=404)
    return response


def create_download_ticket(
    db: Session,
    settings: Settings,
    *,
    slug: str,
    semver: str,
    architecture: str,
    download_url_builder,
) -> DownloadTicketResponse:
    row = db.execute(
        select(DesktopPluginArtifact, DesktopPluginVersion, DesktopPlugin)
        .join(
            DesktopPluginVersion,
            DesktopPluginVersion.id == DesktopPluginArtifact.plugin_version_id,
        )
        .join(DesktopPlugin, DesktopPlugin.id == DesktopPluginVersion.plugin_id)
        .where(
            DesktopPlugin.slug == slug,
            DesktopPlugin.status == DesktopPluginStatus.ACTIVE,
            DesktopPluginVersion.semver == semver,
            DesktopPluginVersion.status == DesktopPluginVersionStatus.PUBLISHED,
            DesktopPluginVersion.platform_signature_base64.is_not(None),
            DesktopPluginArtifact.architecture == architecture,
            DesktopPluginArtifact.status == DesktopPluginArtifactStatus.PUBLIC,
            DesktopPluginArtifact.zone == DesktopPluginArtifactZone.PUBLIC,
            DesktopPluginArtifact.public_storage_key.is_not(None),
        )
    ).one_or_none()
    if row is None:
        raise AppError("desktop_plugin.artifact_missing", "可下载插件制品不存在", status_code=404)
    artifact = row[0]
    if _is_revoked(
        db,
        plugin_id=row[2].id,
        version_id=row[1].id,
        signing_key_id=row[1].signing_key_id,
    ):
        raise AppError("desktop_plugin.artifact_missing", "可下载插件制品不存在", status_code=404)
    raw_token = "plugin_download_" + secrets.token_urlsafe(32)
    ticket = DesktopPluginDownloadTicket(
        artifact_id=artifact.id,
        token_hash=hash_opaque_token(raw_token),
        expires_at=utc_now()
        + timedelta(seconds=settings.desktop_plugin_download_ticket_ttl_seconds),
    )
    db.add(ticket)
    db.flush()
    _write_audit(
        db,
        action="desktop_plugin.download_ticket.issued",
        target_type="desktop_plugin_version",
        target_id=row[1].id,
        actor_id=None,
        context=None,
        details={"architecture": architecture, "result": "issued"},
    )
    db.commit()
    return DownloadTicketResponse(
        download_url=download_url_builder(raw_token),
        expires_at=ticket.expires_at,
        artifact_sha256=artifact.sha256,
        artifact_size_bytes=artifact.size_bytes,
    )


def prepare_download(
    db: Session, settings: Settings, *, raw_token: str
) -> tuple[DesktopPluginArtifact, Path]:
    ticket = db.scalar(
        select(DesktopPluginDownloadTicket)
        .where(DesktopPluginDownloadTicket.token_hash == hash_opaque_token(raw_token))
        .with_for_update()
    )
    if ticket is None or ticket.downloaded_at is not None or _aware(ticket.expires_at) <= utc_now():
        raise AppError(
            "desktop_plugin.download_ticket_invalid",
            "下载票据无效、已使用或已过期",
            status_code=410,
        )
    row = db.execute(
        select(DesktopPluginArtifact, DesktopPluginVersion, DesktopPlugin)
        .join(
            DesktopPluginVersion,
            DesktopPluginVersion.id == DesktopPluginArtifact.plugin_version_id,
        )
        .join(DesktopPlugin, DesktopPlugin.id == DesktopPluginVersion.plugin_id)
        .where(DesktopPluginArtifact.id == ticket.artifact_id)
    ).one_or_none()
    if row is None:
        raise AppError("desktop_plugin.artifact_missing", "公开插件制品不存在", status_code=404)
    artifact, version, plugin = row
    if (
        plugin.status != DesktopPluginStatus.ACTIVE
        or version.status != DesktopPluginVersionStatus.PUBLISHED
        or artifact.status != DesktopPluginArtifactStatus.PUBLIC
        or artifact.zone != DesktopPluginArtifactZone.PUBLIC
        or not artifact.public_storage_key
        or _is_revoked(
            db,
            plugin_id=plugin.id,
            version_id=version.id,
            signing_key_id=version.signing_key_id,
        )
    ):
        raise AppError("desktop_plugin.artifact_missing", "公开插件制品不存在", status_code=404)
    path = DesktopPluginStorage(settings).read_public(artifact.public_storage_key)
    ticket.downloaded_at = utc_now()
    db.commit()
    return artifact, path


def list_revocations(db: Session) -> PluginRevocationListResponse:
    now = utc_now()
    records = list(
        db.scalars(
            select(DesktopPluginRevocation)
            .where(DesktopPluginRevocation.effective_at <= now)
            .order_by(DesktopPluginRevocation.effective_at, DesktopPluginRevocation.id)
        ).all()
    )
    items: list[PluginRevocationResponse] = []
    for record in records:
        plugin = db.get(DesktopPlugin, record.plugin_id) if record.plugin_id else None
        version = (
            db.get(DesktopPluginVersion, record.plugin_version_id)
            if record.plugin_version_id
            else None
        )
        if version is not None and plugin is None:
            plugin = db.get(DesktopPlugin, version.plugin_id)
        key = (
            db.get(DesktopPluginSigningKey, record.signing_key_id)
            if record.signing_key_id
            else None
        )
        items.append(
            PluginRevocationResponse(
                id=record.id,
                scope=record.scope.value,
                plugin_slug=plugin.slug if plugin else None,
                semver=version.semver if version else None,
                signing_key_fingerprint=key.fingerprint if key else None,
                reason_code=record.reason_code,
                affects_historical_versions=record.affects_historical_versions,
                effective_at=record.effective_at,
                batch_id=record.batch_id,
                platform_key_id=record.platform_key_id,
                platform_signature_base64=record.platform_signature_base64,
            )
        )
    return PluginRevocationListResponse(
        generated_at=max(
            (record.created_at for record in records), default=datetime(1970, 1, 1, tzinfo=UTC)
        ),
        policy_version=_REVOCATION_POLICY_VERSION,
        items=items,
    )
