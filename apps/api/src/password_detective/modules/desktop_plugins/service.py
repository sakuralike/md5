from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
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
    DesktopPluginInstallEvent,
    DesktopPluginInstallEventKind,
    DesktopPluginPublication,
    DesktopPluginPublicationStatus,
    DesktopPluginReport,
    DesktopPluginReportStatus,
    DesktopPluginReviewEvent,
    DesktopPluginReviewEventKind,
    DesktopPluginRevocation,
    DesktopPluginRevocationScope,
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
from password_detective.db.models.third_party_oauth import ThirdPartyAuthorization
from password_detective.db.models.user import User
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.auth.reauthentication import consume_reauthentication_grant
from password_detective.modules.desktop_plugins.package_verifier import verify_plugin_package
from password_detective.modules.desktop_plugins.review_service import (
    enqueue_static_review,
    list_review_runs,
)
from password_detective.modules.desktop_plugins.schemas import (
    ArtifactUploadResponse,
    DownloadTicketResponse,
    PluginArtifactResponse,
    PluginBrokerAuthorizationRequest,
    PluginBrokerAuthorizationResponse,
    PluginInstallEventRequest,
    PluginInstallEventResponse,
    PluginProjectCreateRequest,
    PluginProjectDetailResponse,
    PluginProjectListResponse,
    PluginProjectResponse,
    PluginProjectUpdateRequest,
    PluginReportCreateRequest,
    PluginReportListResponse,
    PluginReportResponse,
    PluginReportReviewRequest,
    PluginReviewDetailResponse,
    PluginReviewEventResponse,
    PluginReviewQueueItem,
    PluginReviewQueueResponse,
    PluginRevocationListResponse,
    PluginRevocationResponse,
    PluginVersionApproveRequest,
    PluginVersionCreateRequest,
    PluginVersionFinalizeRequest,
    PluginVersionPublishRequest,
    PluginVersionRejectRequest,
    PluginVersionResponse,
    PluginVersionRevokeRequest,
    PluginVersionSubmitRequest,
    PluginVersionYankRequest,
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
_API_CAPABILITY_SCOPES = {
    "api:profile:read": "profile:read",
    "api:hash:read": "hash:read",
    "api:verification:submit": "desktop:verification",
}


def authorize_broker_capability(
    db: Session,
    *,
    plugin_slug: str,
    payload: PluginBrokerAuthorizationRequest,
    principal: Principal,
    context: ClientContext,
) -> PluginBrokerAuthorizationResponse:
    row = db.execute(
        select(DesktopPlugin, DesktopPluginVersion)
        .join(DesktopPluginVersion, DesktopPluginVersion.plugin_id == DesktopPlugin.id)
        .where(
            DesktopPlugin.slug == plugin_slug,
            DesktopPluginVersion.semver == payload.semver,
        )
    ).one_or_none()
    if row is None:
        raise AppError("desktop_plugin.broker_version_not_found", "插件版本不存在", status_code=404)
    plugin, version = row
    if (
        plugin.status != DesktopPluginStatus.ACTIVE
        or version.status != DesktopPluginVersionStatus.PUBLISHED
        or _is_revoked(
            db,
            plugin_id=plugin.id,
            version_id=version.id,
            signing_key_id=version.signing_key_id,
        )
        or payload.capability not in version.approved_capabilities
    ):
        raise AppError(
            "desktop_plugin.broker_capability_denied",
            "插件当前版本未获准使用该平台能力",
            status_code=403,
        )
    scope = _API_CAPABILITY_SCOPES[payload.capability]
    if plugin.linked_third_party_app_id is None:
        raise AppError(
            "desktop_plugin.broker_application_missing",
            "插件未关联已批准的第三方应用",
            status_code=403,
        )
    app = db.scalar(
        select(ThirdPartyApp).where(
            ThirdPartyApp.id == plugin.linked_third_party_app_id,
            ThirdPartyApp.status == ThirdPartyAppStatus.APPROVED,
        )
    )
    if app is None or scope not in {str(item) for item in json.loads(app.approved_scopes_json)}:
        raise AppError(
            "desktop_plugin.broker_application_scope_denied",
            "关联应用的 Scope 已撤销或未批准",
            status_code=403,
        )
    authorization = db.scalar(
        select(ThirdPartyAuthorization).where(
            ThirdPartyAuthorization.app_id == app.id,
            ThirdPartyAuthorization.user_id == principal.user.id,
            ThirdPartyAuthorization.revoked_at.is_(None),
        )
    )
    authorized_scopes = (
        {str(item) for item in json.loads(authorization.scope_json)}
        if authorization is not None
        else set()
    )
    if authorization is None or scope not in authorized_scopes:
        raise AppError(
            "desktop_plugin.broker_user_authorization_required",
            "用户尚未授权该插件所关联的应用 Scope",
            status_code=403,
        )
    now = utc_now()
    authorization.last_used_at = now
    app.last_used_at = now
    app.request_count += 1
    _write_audit(
        db,
        action="desktop_plugin.broker.authorized",
        target_type="desktop_plugin",
        target_id=plugin.id,
        actor_id=principal.user.id,
        context=context,
        details={"capability": payload.capability, "scope": scope},
    )
    db.commit()
    return PluginBrokerAuthorizationResponse(
        allowed=True,
        plugin_slug=plugin.slug,
        semver=version.semver,
        capability=payload.capability,
        scope=scope,
        linked_application_id=app.id,
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _signature_timestamp(value: datetime) -> str:
    return _aware(value).astimezone(UTC).isoformat().replace("+00:00", "Z")


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


def _platform_signature(settings: Settings, payload: dict[str, object]) -> tuple[str, str, str]:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if settings.desktop_plugin_signing_backend == "openbao_transit":
        return _openbao_platform_signature(settings, canonical.encode("utf-8"))
    seed = hashlib.sha256(
        b"password-detective-plugin-platform-signing-v1\0" + settings.app_secret_key.encode("utf-8")
    ).digest()
    private_key = Ed25519PrivateKey.from_private_bytes(seed)
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    key_id = f"platform-ed25519-{hashlib.sha256(public_key).hexdigest()[:16]}"
    signature = private_key.sign(canonical.encode("utf-8"))
    return (
        key_id,
        base64.b64encode(public_key).decode("ascii"),
        base64.b64encode(signature).decode("ascii"),
    )


def _openbao_platform_signature(settings: Settings, message: bytes) -> tuple[str, str, str]:
    base_url = settings.desktop_plugin_signing_url.strip().rstrip("/")
    token = settings.desktop_plugin_signing_token.get_secret_value().strip()
    key_name = settings.desktop_plugin_signing_key.strip()
    if not base_url or not token or not key_name:
        raise AppError(
            "desktop_plugin.signer_unavailable", "OpenBao 签名服务配置不完整", status_code=503
        )

    headers = {"X-Vault-Token": token, "Content-Type": "application/json"}
    sign_url = f"{base_url}/v1/transit/sign/{urllib.parse.quote(key_name, safe='')}"
    request = urllib.request.Request(
        sign_url,
        data=json.dumps(
            {"input": base64.b64encode(message).decode("ascii"), "hash_algorithm": "sha2-256"}
        ).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            signed = json.loads(response.read(256 * 1024).decode("utf-8"))
        signature = str(signed["data"]["signature"])
        if not signature.startswith("vault:"):
            raise ValueError("invalid signature format")
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/v1/transit/keys/{urllib.parse.quote(key_name, safe='')}",
                headers=headers,
            ),
            timeout=5,
        ) as response:
            key_data = json.loads(response.read(256 * 1024).decode("utf-8"))["data"]
        versions = key_data.get("keys", {})
        current = str(key_data.get("latest_version", max(versions, key=int)))
        public_key = str(versions[current]["public_key"])
        try:
            raw_public_key = base64.b64decode(public_key, validate=True)
        except ValueError:
            loaded_key = serialization.load_pem_public_key(public_key.encode("utf-8"))
            raw_public_key = loaded_key.public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        if len(raw_public_key) != 32:
            raise ValueError("invalid ed25519 public key")
        key_id = f"platform-ed25519-{hashlib.sha256(raw_public_key).hexdigest()[:16]}"
        return (
            key_id,
            base64.b64encode(raw_public_key).decode("ascii"),
            base64.b64encode(base64.b64decode(signature.split(":", 2)[-1], validate=True)).decode(
                "ascii"
            ),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        raise AppError(
            "desktop_plugin.signer_unavailable", "OpenBao 签名服务不可用", status_code=503
        ) from exc


def _publication_signature_payload(
    plugin: DesktopPlugin,
    version: DesktopPluginVersion,
    artifacts: list[DesktopPluginArtifact],
    *,
    published_at: datetime,
) -> dict[str, object]:
    return {
        "plugin_slug": plugin.slug,
        "semver": version.semver,
        "manifest_sha256": version.manifest_sha256,
        "approved_capabilities": sorted(version.approved_capabilities),
        "policy": version.review_policy_version,
        "published_at": _signature_timestamp(published_at),
        "artifacts": [
            {
                "architecture": artifact.architecture,
                "sha256": artifact.sha256,
                "size_bytes": artifact.size_bytes,
            }
            for artifact in sorted(artifacts, key=lambda item: item.architecture)
        ],
    }


def _revocation_signature_payload(
    *,
    scope: DesktopPluginRevocationScope,
    plugin: DesktopPlugin | None = None,
    version: DesktopPluginVersion | None = None,
    signing_key_fingerprint: str | None = None,
    reason_code: str,
    affects_historical_versions: bool,
    effective_at: datetime,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "scope": scope.value,
        "reason_code": reason_code,
        "affects_historical_versions": affects_historical_versions,
        "effective_at": _signature_timestamp(effective_at),
    }
    if plugin is not None:
        payload["plugin_slug"] = plugin.slug
    if version is not None:
        payload["semver"] = version.semver
    if signing_key_fingerprint is not None:
        payload["signing_key_fingerprint"] = signing_key_fingerprint
    return payload


def _review_event(
    db: Session,
    *,
    version: DesktopPluginVersion,
    kind: DesktopPluginReviewEventKind,
    actor_id: str | None,
    note: str | None = None,
) -> DesktopPluginReviewEvent:
    event = DesktopPluginReviewEvent(
        version_id=version.id,
        kind=kind,
        actor_user_id=actor_id,
        note=note,
        requested_capabilities=list(version.requested_capabilities),
        approved_capabilities=list(version.approved_capabilities),
        version_number=version.version,
    )
    db.add(event)
    return event


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


def _validate_linked_app(db: Session, *, app_id: str | None, owner_id: str) -> ThirdPartyApp | None:
    if app_id is None:
        return None
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
    return app


def _validate_api_capabilities(
    db: Session, *, plugin: DesktopPlugin, requested_capabilities: list[str]
) -> None:
    required_scopes = {
        _API_CAPABILITY_SCOPES[capability]
        for capability in requested_capabilities
        if capability in _API_CAPABILITY_SCOPES
    }
    if not required_scopes:
        return
    app = _validate_linked_app(
        db,
        app_id=plugin.linked_third_party_app_id,
        owner_id=plugin.owner_user_id,
    )
    if app is None:
        raise AppError(
            "desktop_plugin.linked_application_required",
            "申请平台 API 权限的插件必须关联已批准的第三方应用",
            status_code=422,
        )
    approved_scopes = {str(scope) for scope in json.loads(app.approved_scopes_json)}
    missing_scopes = sorted(required_scopes - approved_scopes)
    if missing_scopes:
        raise AppError(
            "desktop_plugin.linked_application_scope_missing",
            "关联第三方应用未获批插件申请的平台 API Scope",
            status_code=422,
            details={"missing_scopes": missing_scopes},
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
        platform_public_key_base64=version.platform_public_key_base64,
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
    generated_private_key: Ed25519PrivateKey | None = None
    if payload.public_key_base64 is None:
        generated_private_key = Ed25519PrivateKey.generate()
        raw_public_key = generated_private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        public_key_base64 = base64.b64encode(raw_public_key).decode("ascii")
        fingerprint = hashlib.sha256(raw_public_key).hexdigest()
        key_id = payload.key_id or f"generated-ed25519-{fingerprint[:16]}"
    else:
        if payload.key_id is None:
            raise AppError(
                "desktop_plugin.signing_key_id_required",
                "手动登记公钥时必须提供密钥 ID",
                status_code=422,
            )
        _, fingerprint = _decode_public_key(payload.public_key_base64)
        public_key_base64 = payload.public_key_base64
        key_id = payload.key_id
    rotated_from: DesktopPluginSigningKey | None = None
    if payload.rotated_from_id is not None:
        rotated_from = db.scalar(
            select(DesktopPluginSigningKey)
            .where(
                DesktopPluginSigningKey.id == payload.rotated_from_id,
                DesktopPluginSigningKey.owner_user_id == principal.user.id,
            )
            .with_for_update()
        )
        if rotated_from is None:
            raise AppError(
                "desktop_plugin.signing_key_rotation_source_not_found",
                "轮换来源密钥不存在或不属于当前开发者",
                status_code=422,
            )
        if rotated_from.status == DesktopPluginSigningKeyStatus.REVOKED:
            raise AppError(
                "desktop_plugin.signing_key_rotation_source_revoked",
                "已撤销的签名密钥不能作为轮换来源",
                status_code=409,
            )
    if db.scalar(
        select(DesktopPluginSigningKey.id).where(
            or_(
                DesktopPluginSigningKey.key_id == key_id,
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
        key_id=key_id,
        public_key_base64=public_key_base64,
        fingerprint=fingerprint,
    )
    if rotated_from is not None:
        rotated_from.status = DesktopPluginSigningKeyStatus.ROTATING
    db.add(key)
    db.flush()
    _write_audit(
        db,
        action="desktop_plugin.signing_key.registered",
        target_type="desktop_plugin_signing_key",
        target_id=key.id,
        actor_id=principal.user.id,
        context=context,
        details={
            "key_id": key.key_id,
            "fingerprint": fingerprint,
            "generated": generated_private_key is not None,
        },
    )
    db.commit()
    db.refresh(key)
    response = SigningKeyResponse.model_validate(key)
    if generated_private_key is not None:
        response = response.model_copy(
            update={
                "private_key_base64": base64.b64encode(
                    generated_private_key.private_bytes(
                        serialization.Encoding.Raw,
                        serialization.PrivateFormat.Raw,
                        serialization.NoEncryption(),
                    )
                ).decode("ascii")
            }
        )
    return response


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
    settings: Settings,
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
    effective_at = utc_now()
    key.status = DesktopPluginSigningKeyStatus.REVOKED
    key.revoked_at = effective_at
    signature_payload = _revocation_signature_payload(
        scope=DesktopPluginRevocationScope.SIGNING_KEY,
        signing_key_fingerprint=key.fingerprint,
        reason_code="developer_signing_key_revoked",
        affects_historical_versions=True,
        effective_at=effective_at,
    )
    platform_key_id, platform_public_key, platform_signature = _platform_signature(
        settings, signature_payload
    )
    db.add(
        DesktopPluginRevocation(
            scope=DesktopPluginRevocationScope.SIGNING_KEY,
            signing_key_id=key.id,
            reason_code="developer_signing_key_revoked",
            affects_historical_versions=True,
            effective_at=effective_at,
            batch_id=secrets.token_hex(16),
            platform_key_id=platform_key_id,
            platform_public_key_base64=platform_public_key,
            platform_signature_base64=platform_signature,
        )
    )
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
            storage.delete(existing.storage_key)
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
                        & (
                            (
                                DesktopPluginRevocation.scope
                                == DesktopPluginRevocationScope.SIGNING_KEY
                            )
                            | DesktopPluginRevocation.affects_historical_versions.is_(True)
                        )
                    ),
                ),
            )
        )
        is not None
    )


def _public_version_response(
    db: Session, version: DesktopPluginVersion
) -> PublicPluginVersionResponse | None:
    plugin = db.get(DesktopPlugin, version.plugin_id)
    artifacts = _public_artifacts(db, version.id)
    if (
        version.status != DesktopPluginVersionStatus.PUBLISHED
        or version.manifest_json is None
        or version.manifest_sha256 is None
        or version.published_at is None
        or version.review_policy_version is None
        or version.platform_key_id is None
        or version.platform_public_key_base64 is None
        or version.platform_signature_base64 is None
        or plugin is None
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
        version_id=version.id,
        plugin_slug=plugin.slug,
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
        platform_public_key_base64=version.platform_public_key_base64,
        platform_signature_base64=version.platform_signature_base64,
        platform_signature_payload=(
            _publication_signature_payload(
                plugin,
                version,
                artifacts,
                published_at=version.published_at,
            )
            if version.published_at is not None and version.platform_signature_base64 is not None
            else None
        ),
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
                developer_name=owner.username,
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
    row = db.execute(
        select(DesktopPlugin, User)
        .join(User, User.id == DesktopPlugin.owner_user_id)
        .where(
            DesktopPlugin.slug == slug,
            DesktopPlugin.status == DesktopPluginStatus.ACTIVE,
        )
    ).one_or_none()
    if row is None:
        raise AppError("desktop_plugin.not_found", "插件不存在", status_code=404)
    plugin, owner = row
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
        developer_name=owner.username,
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
                platform_public_key_base64=record.platform_public_key_base64,
                platform_signature_base64=record.platform_signature_base64,
                platform_signature_payload=_revocation_signature_payload(
                    scope=record.scope,
                    plugin=plugin,
                    version=version,
                    signing_key_fingerprint=key.fingerprint if key else None,
                    reason_code=record.reason_code,
                    affects_historical_versions=record.affects_historical_versions,
                    effective_at=record.effective_at,
                ),
            )
        )
    return PluginRevocationListResponse(
        generated_at=max(
            (record.created_at for record in records), default=datetime(1970, 1, 1, tzinfo=UTC)
        ),
        policy_version=_REVOCATION_POLICY_VERSION,
        items=items,
    )


def record_install_event(
    db: Session,
    *,
    payload: PluginInstallEventRequest,
    user_id: str | None,
    idempotency_key: str,
) -> PluginInstallEventResponse:
    if idempotency_key != payload.event_id:
        raise AppError(
            "desktop_plugin.install_event_idempotency_mismatch",
            "安装事件 ID 必须与 Idempotency-Key 一致",
            status_code=422,
        )
    if db.scalar(
        select(DesktopPluginInstallEvent.id).where(
            DesktopPluginInstallEvent.event_id == payload.event_id
        )
    ):
        return PluginInstallEventResponse(accepted=True, event_id=payload.event_id)
    if payload.source == "market_reviewed":
        row = db.execute(
            select(DesktopPluginVersion, DesktopPlugin)
            .join(DesktopPlugin, DesktopPlugin.id == DesktopPluginVersion.plugin_id)
            .where(
                DesktopPlugin.slug == payload.plugin_slug,
                DesktopPluginVersion.semver == payload.semver,
            )
        ).one_or_none()
        if row is None and payload.result == "success":
            raise AppError("desktop_plugin.version_not_found", "插件版本不存在", status_code=404)
        if row is not None:
            version, plugin = row
        else:
            version = plugin = None
        if (
            row is not None
            and payload.result == "success"
            and (
                plugin.status != DesktopPluginStatus.ACTIVE
                or version.status != DesktopPluginVersionStatus.PUBLISHED
                or _is_revoked(
                    db,
                    plugin_id=plugin.id,
                    version_id=version.id,
                    signing_key_id=version.signing_key_id,
                )
                or not _public_artifacts(db, version.id, payload.architecture)
            )
        ):
            raise AppError(
                "desktop_plugin.version_not_available",
                "平台插件版本当前不可用",
                status_code=409,
            )
    db.add(
        DesktopPluginInstallEvent(
            event_id=payload.event_id,
            plugin_slug=payload.plugin_slug,
            semver=payload.semver,
            architecture=payload.architecture,
            source=payload.source,
            kind=DesktopPluginInstallEventKind(payload.kind),
            result=payload.result,
            client_version=payload.client_version,
            user_id=user_id,
        )
    )
    db.commit()
    return PluginInstallEventResponse(accepted=True, event_id=payload.event_id)


def submit_version_for_review(
    db: Session,
    *,
    version_id: str,
    payload: PluginVersionSubmitRequest,
    principal: Principal,
    context: ClientContext,
) -> PluginVersionResponse:
    _require_verified(principal)
    plugin, version = _owned_version(
        db, version_id=version_id, owner_id=principal.user.id, lock=True
    )
    if version.version != payload.version:
        raise AppError(
            "desktop_plugin.version_conflict", "插件版本已被其他请求修改", status_code=409
        )
    if version.status != DesktopPluginVersionStatus.QUARANTINED:
        raise AppError(
            "desktop_plugin.version_not_submittable", "插件版本不处于待审核状态", status_code=409
        )
    _validate_api_capabilities(
        db,
        plugin=plugin,
        requested_capabilities=list(version.requested_capabilities),
    )
    version.status = DesktopPluginVersionStatus.REVIEW_QUEUED
    version.submitted_at = utc_now()
    version.version += 1
    review_run = enqueue_static_review(db, version=version)
    _review_event(
        db, version=version, kind=DesktopPluginReviewEventKind.SUBMITTED, actor_id=principal.user.id
    )
    _write_audit(
        db,
        action="desktop_plugin.version.submitted",
        target_type="desktop_plugin_version",
        target_id=version.id,
        actor_id=principal.user.id,
        context=context,
        details={"review_run_id": review_run.id},
    )
    db.commit()
    db.refresh(version)
    return _version_response(db, version)


def withdraw_version(
    db: Session,
    *,
    version_id: str,
    payload: PluginVersionSubmitRequest,
    principal: Principal,
    context: ClientContext,
) -> PluginVersionResponse:
    _require_verified(principal)
    _, version = _owned_version(db, version_id=version_id, owner_id=principal.user.id, lock=True)
    if version.version != payload.version:
        raise AppError(
            "desktop_plugin.version_conflict", "插件版本已被其他请求修改", status_code=409
        )
    if version.status not in {
        DesktopPluginVersionStatus.QUARANTINED,
        DesktopPluginVersionStatus.REVIEW_QUEUED,
        DesktopPluginVersionStatus.AUTO_REVIEW_RUNNING,
        DesktopPluginVersionStatus.AUTO_REVIEW_FAILED,
        DesktopPluginVersionStatus.MANUAL_REVIEW_READY,
        DesktopPluginVersionStatus.REJECTED,
    }:
        raise AppError(
            "desktop_plugin.version_not_withdrawable", "当前版本不能撤回", status_code=409
        )
    version.status = DesktopPluginVersionStatus.WITHDRAWN
    version.version += 1
    _review_event(
        db,
        version=version,
        kind=DesktopPluginReviewEventKind.WITHDRAWN,
        actor_id=principal.user.id,
    )
    _write_audit(
        db,
        action="desktop_plugin.version.withdrawn",
        target_type="desktop_plugin_version",
        target_id=version.id,
        actor_id=principal.user.id,
        context=context,
        details={},
    )
    db.commit()
    db.refresh(version)
    return _version_response(db, version)


def _queue_item(plugin: DesktopPlugin, version: DesktopPluginVersion) -> PluginReviewQueueItem:
    return PluginReviewQueueItem(
        version_id=version.id,
        plugin_id=plugin.id,
        plugin_slug=plugin.slug,
        plugin_name=plugin.name,
        owner_user_id=plugin.owner_user_id,
        semver=version.semver,
        status=version.status.value,
        requested_capabilities=list(version.requested_capabilities),
        approved_capabilities=list(version.approved_capabilities),
        signing_key_fingerprint=version.signing_key_fingerprint,
        manifest_sha256=version.manifest_sha256,
        risk_tier=version.risk_tier,
        submitted_at=version.submitted_at,
        updated_at=version.updated_at,
        version=version.version,
    )


def list_review_queue(
    db: Session, *, page: int, page_size: int, status_filter: str | None
) -> PluginReviewQueueResponse:
    statuses = {
        DesktopPluginVersionStatus.REVIEW_QUEUED,
        DesktopPluginVersionStatus.AUTO_REVIEW_RUNNING,
        DesktopPluginVersionStatus.MANUAL_REVIEW_READY,
        DesktopPluginVersionStatus.AUTO_REVIEW_FAILED,
        DesktopPluginVersionStatus.APPROVED,
        DesktopPluginVersionStatus.REJECTED,
        DesktopPluginVersionStatus.PUBLISHED,
        DesktopPluginVersionStatus.YANKED,
        DesktopPluginVersionStatus.REVOKED,
    }
    statement = (
        select(DesktopPlugin, DesktopPluginVersion)
        .join(DesktopPluginVersion, DesktopPluginVersion.plugin_id == DesktopPlugin.id)
        .where(DesktopPluginVersion.status.in_(statuses))
    )
    if status_filter:
        try:
            status = DesktopPluginVersionStatus(status_filter)
        except ValueError as exc:
            raise AppError(
                "desktop_plugin.invalid_review_status", "审核状态无效", status_code=422
            ) from exc
        statement = statement.where(DesktopPluginVersion.status == status)
    rows = list(
        db.execute(
            statement.order_by(DesktopPluginVersion.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    total_statement = select(func.count()).select_from(
        statement.order_by(None).limit(None).offset(None).subquery()
    )
    total = db.scalar(total_statement) or 0
    return PluginReviewQueueResponse(
        items=[_queue_item(plugin, version) for plugin, version in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_review_detail(db: Session, *, version_id: str) -> PluginReviewDetailResponse:
    row = db.execute(
        select(DesktopPlugin, DesktopPluginVersion)
        .join(DesktopPluginVersion, DesktopPluginVersion.plugin_id == DesktopPlugin.id)
        .where(DesktopPluginVersion.id == version_id)
    ).one_or_none()
    if row is None:
        raise AppError("desktop_plugin.version_not_found", "插件版本不存在", status_code=404)
    plugin, version = row
    artifacts = list(
        db.scalars(
            select(DesktopPluginArtifact).where(
                DesktopPluginArtifact.plugin_version_id == version.id
            )
        ).all()
    )
    events = list(
        db.scalars(
            select(DesktopPluginReviewEvent)
            .where(DesktopPluginReviewEvent.version_id == version.id)
            .order_by(DesktopPluginReviewEvent.created_at)
        ).all()
    )
    return PluginReviewDetailResponse(
        **_queue_item(plugin, version).model_dump(),
        manifest_json=version.manifest_json,
        release_notes=version.release_notes,
        source_review_mode=version.source_review_mode,
        review_policy_version=version.review_policy_version,
        platform_key_id=version.platform_key_id,
        platform_public_key_base64=version.platform_public_key_base64,
        platform_signature_base64=version.platform_signature_base64,
        platform_signature_payload=(
            _publication_signature_payload(
                plugin,
                version,
                artifacts,
                published_at=version.published_at,
            )
            if version.published_at is not None and version.platform_signature_base64 is not None
            else None
        ),
        artifacts=[_artifact_response(artifact) for artifact in artifacts],
        events=[
            PluginReviewEventResponse(
                id=event.id,
                kind=event.kind.value,
                actor_user_id=event.actor_user_id,
                note=event.note,
                requested_capabilities=list(event.requested_capabilities),
                approved_capabilities=list(event.approved_capabilities),
                version_number=event.version_number,
                created_at=event.created_at,
            )
            for event in events
        ],
        review_runs=list_review_runs(db, version_id=version.id, developer_visible_only=False),
    )


def get_review_source(
    db: Session,
    settings: Settings,
    *,
    version_id: str,
) -> dict:
    _, version = _admin_version(db, version_id=version_id)
    artifact = db.scalar(
        select(DesktopPluginArtifact).where(
            DesktopPluginArtifact.plugin_version_id == version.id,
            DesktopPluginArtifact.storage_key.is_not(None),
        )
    )
    if artifact is None or artifact.storage_key is None:
        raise AppError("desktop_plugin.source_not_found", "插件源码制品不存在", status_code=404)
    allowed = {
        ".cs",
        ".csproj",
        ".go",
        ".json",
        ".md",
        ".ps1",
        ".py",
        ".rs",
        ".toml",
        ".xml",
        ".yaml",
        ".yml",
    }
    files = []
    with zipfile.ZipFile(
        DesktopPluginStorage(settings).quarantine_path(artifact.storage_key)
    ) as archive:
        for entry in archive.infolist():
            path = entry.filename.rstrip("/")
            if (
                not path.startswith("source/")
                or entry.is_dir()
                or Path(path).suffix.lower() not in allowed
            ):
                continue
            raw = archive.read(entry, 262_145)
            files.append(
                {
                    "path": path,
                    "content": raw[:262_144].decode("utf-8", errors="replace"),
                    "truncated": len(raw) > 262_144,
                }
            )
            if len(files) == 32:
                break
    return {"version_id": version.id, "files": files}


def _admin_version(
    db: Session, *, version_id: str, lock: bool = False
) -> tuple[DesktopPlugin, DesktopPluginVersion]:
    statement = (
        select(DesktopPlugin, DesktopPluginVersion)
        .join(DesktopPluginVersion, DesktopPluginVersion.plugin_id == DesktopPlugin.id)
        .where(DesktopPluginVersion.id == version_id)
    )
    if lock:
        statement = statement.with_for_update()
    row = db.execute(statement).one_or_none()
    if row is None:
        raise AppError("desktop_plugin.version_not_found", "插件版本不存在", status_code=404)
    return row[0], row[1]


def rerun_static_review(
    db: Session,
    *,
    version_id: str,
    principal: Principal,
    context: ClientContext,
) -> PluginReviewDetailResponse:
    plugin, version = _admin_version(db, version_id=version_id, lock=True)
    if version.status not in {
        DesktopPluginVersionStatus.AUTO_REVIEW_FAILED,
        DesktopPluginVersionStatus.REVIEW_QUEUED,
    }:
        raise AppError(
            "desktop_plugin.version_not_rerunnable", "当前版本不能重新执行自动审核", status_code=409
        )
    version.status = DesktopPluginVersionStatus.REVIEW_QUEUED
    version.version += 1
    run = enqueue_static_review(db, version=version)
    _review_event(
        db,
        version=version,
        kind=DesktopPluginReviewEventKind.SUBMITTED,
        actor_id=principal.user.id,
        note="管理员要求重新执行自动审核。",
    )
    _write_audit(
        db,
        action="desktop_plugin.version.static_review_rerun",
        target_type="desktop_plugin_version",
        target_id=version.id,
        actor_id=principal.user.id,
        context=context,
        details={"review_run_id": run.id},
    )
    db.commit()
    return get_review_detail(db, version_id=version.id)


def approve_version(
    db: Session,
    settings: Settings,
    *,
    version_id: str,
    payload: PluginVersionApproveRequest,
    principal: Principal,
    context: ClientContext,
) -> PluginReviewDetailResponse:
    plugin, version = _admin_version(db, version_id=version_id, lock=True)
    if version.version != payload.version:
        raise AppError(
            "desktop_plugin.version_conflict", "插件版本已被其他请求修改", status_code=409
        )
    if version.status != DesktopPluginVersionStatus.MANUAL_REVIEW_READY:
        raise AppError(
            "desktop_plugin.version_not_approvable", "插件版本不处于人工审核状态", status_code=409
        )
    source = get_review_source(db, settings, version_id=version.id)
    if not source["files"]:
        raise AppError(
            "desktop_plugin.source_required_for_approval",
            "管理员批准前必须提供可审文本源码",
            status_code=409,
        )
    _validate_api_capabilities(
        db,
        plugin=plugin,
        requested_capabilities=list(version.requested_capabilities),
    )
    requested = set(version.requested_capabilities)
    approved = set(payload.approved_capabilities)
    if not approved.issubset(requested):
        raise AppError(
            "desktop_plugin.capability_not_requested", "管理员不能批准未申请的权限", status_code=422
        )
    version.status = DesktopPluginVersionStatus.APPROVED
    version.approved_capabilities = sorted(approved)
    version.reviewer_user_id = principal.user.id
    version.review_policy_version = "manual-review-v1"
    version.approved_at = utc_now()
    version.version += 1
    _review_event(
        db,
        version=version,
        kind=DesktopPluginReviewEventKind.APPROVED,
        actor_id=principal.user.id,
        note=payload.review_note,
    )
    _write_audit(
        db,
        action="desktop_plugin.version.approved",
        target_type="desktop_plugin_version",
        target_id=version.id,
        actor_id=principal.user.id,
        context=context,
        details={"approved_capabilities": sorted(approved)},
    )
    db.commit()
    return get_review_detail(db, version_id=version.id)


def reject_version(
    db: Session,
    *,
    version_id: str,
    payload: PluginVersionRejectRequest,
    principal: Principal,
    context: ClientContext,
) -> PluginReviewDetailResponse:
    plugin, version = _admin_version(db, version_id=version_id, lock=True)
    del plugin
    if version.version != payload.version:
        raise AppError(
            "desktop_plugin.version_conflict", "插件版本已被其他请求修改", status_code=409
        )
    if version.status not in {
        DesktopPluginVersionStatus.REVIEW_QUEUED,
        DesktopPluginVersionStatus.AUTO_REVIEW_FAILED,
        DesktopPluginVersionStatus.MANUAL_REVIEW_READY,
    }:
        raise AppError(
            "desktop_plugin.version_not_rejectable", "插件版本不处于人工审核状态", status_code=409
        )
    version.status = DesktopPluginVersionStatus.REJECTED
    version.reviewer_user_id = principal.user.id
    version.review_policy_version = "manual-review-v1"
    version.version += 1
    _review_event(
        db,
        version=version,
        kind=DesktopPluginReviewEventKind.REJECTED,
        actor_id=principal.user.id,
        note=payload.review_note,
    )
    _write_audit(
        db,
        action="desktop_plugin.version.rejected",
        target_type="desktop_plugin_version",
        target_id=version.id,
        actor_id=principal.user.id,
        context=context,
        details={"reason": payload.review_note},
    )
    db.commit()
    return get_review_detail(db, version_id=version.id)


def publish_version(
    db: Session,
    settings: Settings,
    *,
    version_id: str,
    payload: PluginVersionPublishRequest,
    principal: Principal,
    context: ClientContext,
) -> PluginReviewDetailResponse:
    plugin, version = _admin_version(db, version_id=version_id, lock=True)
    if version.version != payload.version:
        raise AppError(
            "desktop_plugin.version_conflict", "插件版本已被其他请求修改", status_code=409
        )
    if version.status != DesktopPluginVersionStatus.APPROVED:
        raise AppError(
            "desktop_plugin.version_not_publishable", "只有批准版本才能发布", status_code=409
        )
    artifacts = list(
        db.scalars(
            select(DesktopPluginArtifact)
            .where(DesktopPluginArtifact.plugin_version_id == version.id)
            .with_for_update()
        ).all()
    )
    storage = DesktopPluginStorage(settings)
    for artifact in artifacts:
        if artifact.status != DesktopPluginArtifactStatus.QUARANTINED or not artifact.storage_key:
            raise AppError(
                "desktop_plugin.artifact_not_ready", "制品未处于隔离待发布状态", status_code=409
            )
        public_key = storage.public_key(version.id, artifact.architecture, artifact.id)
        storage.publish(artifact.storage_key, public_key)
        artifact.public_storage_key = public_key
        artifact.status = DesktopPluginArtifactStatus.PUBLIC
        artifact.zone = DesktopPluginArtifactZone.PUBLIC
    now = utc_now()
    signature_payload = _publication_signature_payload(
        plugin,
        version,
        artifacts,
        published_at=now,
    )
    key_id, public_key, signature = _platform_signature(
        settings,
        signature_payload,
    )
    version.platform_key_id = key_id
    version.platform_public_key_base64 = public_key
    version.platform_signature_base64 = signature
    version.status = DesktopPluginVersionStatus.PUBLISHED
    version.published_at = now
    version.version += 1
    plugin.status = DesktopPluginStatus.ACTIVE
    publication = DesktopPluginPublication(
        version_id=version.id,
        channel=payload.channel,
        published_by_user_id=principal.user.id,
        published_at=now,
    )
    db.add(publication)
    _review_event(
        db, version=version, kind=DesktopPluginReviewEventKind.PUBLISHED, actor_id=principal.user.id
    )
    _write_audit(
        db,
        action="desktop_plugin.version.published",
        target_type="desktop_plugin_version",
        target_id=version.id,
        actor_id=principal.user.id,
        context=context,
        details={"channel": payload.channel, "platform_key_id": key_id},
    )
    db.commit()
    return get_review_detail(db, version_id=version.id)


def yank_version(
    db: Session,
    *,
    version_id: str,
    payload: PluginVersionYankRequest,
    principal: Principal,
    context: ClientContext,
) -> PluginReviewDetailResponse:
    plugin, version = _admin_version(db, version_id=version_id, lock=True)
    if version.version != payload.version:
        raise AppError(
            "desktop_plugin.version_conflict", "插件版本已被其他请求修改", status_code=409
        )
    if version.status != DesktopPluginVersionStatus.PUBLISHED:
        raise AppError(
            "desktop_plugin.version_not_yankable", "只有已发布版本才能下架", status_code=409
        )
    publication = db.scalar(
        select(DesktopPluginPublication)
        .where(
            DesktopPluginPublication.version_id == version.id,
            DesktopPluginPublication.channel == "stable",
        )
        .with_for_update()
    )
    if publication:
        publication.status = DesktopPluginPublicationStatus.YANKED
        publication.yanked_at = utc_now()
        publication.yanked_by_user_id = principal.user.id
    version.status = DesktopPluginVersionStatus.YANKED
    version.yanked_at = utc_now()
    version.version += 1
    for artifact in db.scalars(
        select(DesktopPluginArtifact)
        .where(DesktopPluginArtifact.plugin_version_id == version.id)
        .with_for_update()
    ).all():
        artifact.status = DesktopPluginArtifactStatus.YANKED
    _review_event(
        db,
        version=version,
        kind=DesktopPluginReviewEventKind.YANKED,
        actor_id=principal.user.id,
        note=payload.reason,
    )
    _write_audit(
        db,
        action="desktop_plugin.version.yanked",
        target_type="desktop_plugin_version",
        target_id=version.id,
        actor_id=principal.user.id,
        context=context,
        details={"reason": payload.reason},
    )
    db.commit()
    return get_review_detail(db, version_id=version.id)


def revoke_version(
    db: Session,
    settings: Settings,
    *,
    version_id: str,
    payload: PluginVersionRevokeRequest,
    principal: Principal,
    context: ClientContext,
) -> PluginReviewDetailResponse:
    plugin, version = _admin_version(db, version_id=version_id, lock=True)
    if version.version != payload.version:
        raise AppError(
            "desktop_plugin.version_conflict", "插件版本已被其他请求修改", status_code=409
        )
    if version.status not in {
        DesktopPluginVersionStatus.PUBLISHED,
        DesktopPluginVersionStatus.YANKED,
        DesktopPluginVersionStatus.APPROVED,
    }:
        raise AppError(
            "desktop_plugin.version_not_revokeable", "插件版本当前不能撤销", status_code=409
        )
    now = utc_now()
    key_id, public_key, signature = _platform_signature(
        settings,
        _revocation_signature_payload(
            scope=DesktopPluginRevocationScope.VERSION,
            plugin=plugin,
            version=version,
            reason_code=payload.reason_code,
            affects_historical_versions=payload.affects_historical_versions,
            effective_at=now,
        ),
    )
    db.add(
        DesktopPluginRevocation(
            scope=DesktopPluginRevocationScope.VERSION,
            plugin_version_id=version.id,
            reason_code=payload.reason_code,
            affects_historical_versions=payload.affects_historical_versions,
            effective_at=now,
            batch_id=secrets.token_hex(16),
            platform_key_id=key_id,
            platform_public_key_base64=public_key,
            platform_signature_base64=signature,
        )
    )
    version.status = DesktopPluginVersionStatus.REVOKED
    version.version += 1
    storage = DesktopPluginStorage(settings)
    for artifact in db.scalars(
        select(DesktopPluginArtifact)
        .where(DesktopPluginArtifact.plugin_version_id == version.id)
        .with_for_update()
    ).all():
        revoked_key = storage.revoked_key(version.id, artifact.architecture, artifact.id)
        source_keys = [key for key in (artifact.public_storage_key, artifact.storage_key) if key]
        storage.move_to_revoked(source_keys, revoked_key)
        artifact.storage_key = revoked_key
        artifact.public_storage_key = None
        artifact.status = DesktopPluginArtifactStatus.REVOKED
        artifact.zone = DesktopPluginArtifactZone.REVOKED
    _review_event(
        db,
        version=version,
        kind=DesktopPluginReviewEventKind.REVOKED,
        actor_id=principal.user.id,
        note=payload.reason,
    )
    _write_audit(
        db,
        action="desktop_plugin.version.revoked",
        target_type="desktop_plugin_version",
        target_id=version.id,
        actor_id=principal.user.id,
        context=context,
        details={"reason_code": payload.reason_code},
    )
    db.commit()
    return get_review_detail(db, version_id=version.id)


def create_report(
    db: Session,
    *,
    plugin_slug: str,
    payload: PluginReportCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> PluginReportResponse:
    plugin = db.scalar(
        select(DesktopPlugin).where(
            DesktopPlugin.slug == plugin_slug, DesktopPlugin.status == DesktopPluginStatus.ACTIVE
        )
    )
    if plugin is None:
        raise AppError("desktop_plugin.not_found", "插件不存在", status_code=404)
    if payload.version_id:
        version = db.scalar(
            select(DesktopPluginVersion).where(
                DesktopPluginVersion.id == payload.version_id,
                DesktopPluginVersion.plugin_id == plugin.id,
            )
        )
        if version is None:
            raise AppError("desktop_plugin.version_not_found", "插件版本不存在", status_code=404)
    report = DesktopPluginReport(
        plugin_id=plugin.id,
        version_id=payload.version_id,
        reporter_user_id=principal.user.id,
        category=payload.category,
        description=payload.description,
    )
    db.add(report)
    db.flush()
    _write_audit(
        db,
        action="desktop_plugin.report.created",
        target_type="desktop_plugin_report",
        target_id=report.id,
        actor_id=principal.user.id,
        context=context,
        details={"category": report.category},
    )
    db.commit()
    db.refresh(report)
    return PluginReportResponse.model_validate(report)


def list_reports(
    db: Session, *, page: int, page_size: int, status_filter: str | None
) -> PluginReportListResponse:
    statement = select(DesktopPluginReport)
    if status_filter:
        try:
            statement = statement.where(
                DesktopPluginReport.status == DesktopPluginReportStatus(status_filter)
            )
        except ValueError as exc:
            raise AppError(
                "desktop_plugin.invalid_report_status", "举报状态无效", status_code=422
            ) from exc
    rows = list(
        db.scalars(
            statement.order_by(DesktopPluginReport.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    total = (
        db.scalar(
            select(func.count()).select_from(
                statement.order_by(None).limit(None).offset(None).subquery()
            )
        )
        or 0
    )
    return PluginReportListResponse(
        items=[PluginReportResponse.model_validate(report) for report in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def review_report(
    db: Session,
    *,
    report_id: str,
    payload: PluginReportReviewRequest,
    principal: Principal,
    context: ClientContext,
) -> PluginReportResponse:
    report = db.scalar(
        select(DesktopPluginReport).where(DesktopPluginReport.id == report_id).with_for_update()
    )
    if report is None:
        raise AppError("desktop_plugin.report_not_found", "举报不存在", status_code=404)
    report.status = DesktopPluginReportStatus(payload.status)
    report.reviewer_user_id = principal.user.id
    report.resolution_note = payload.resolution_note
    _write_audit(
        db,
        action="desktop_plugin.report.reviewed",
        target_type="desktop_plugin_report",
        target_id=report.id,
        actor_id=principal.user.id,
        context=context,
        details={"status": payload.status},
    )
    db.commit()
    db.refresh(report)
    return PluginReportResponse.model_validate(report)
