from __future__ import annotations

import hashlib
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path, PurePath
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.desktop_update import (
    CodeSignatureStatus,
    DesktopArchitecture,
    DesktopRelease,
    DesktopReleaseChannel,
    DesktopReleaseStatus,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.desktop_updates.schemas import (
    DesktopReleaseCreateRequest,
    DesktopReleaseListResponse,
    DesktopReleaseResponse,
    DesktopUpdateCheckResponse,
)

_VERSION_PATTERN = re.compile(
    r"^(?P<numeric>0|[1-9]\d*)(?:\.(?P<minor>0|[1-9]\d*))"
    r"(?:\.(?P<patch>0|[1-9]\d*))(?:\.(?P<revision>0|[1-9]\d*))?"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?$"
)
_ALLOWED_ARTIFACT_SUFFIXES = {".msix", ".msixbundle", ".exe"}


def parse_version(
    value: str,
) -> tuple[tuple[int, int, int, int], tuple[tuple[int, int | str], ...]]:
    match = _VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        raise AppError(
            "desktop.update.invalid_version",
            "客户端版本必须使用数字版本格式，例如 1.2.3 或 1.2.3-beta.1",
            status_code=422,
        )
    numeric = (
        int(match.group("numeric")),
        int(match.group("minor")),
        int(match.group("patch")),
        int(match.group("revision") or 0),
    )
    raw_prerelease = match.group("prerelease")
    if raw_prerelease is None:
        return numeric, ((2, ""),)
    identifiers: list[tuple[int, int | str]] = []
    for part in raw_prerelease.split("."):
        identifiers.append((0, int(part)) if part.isdigit() else (1, part.lower()))
    return numeric, tuple(identifiers)


def _validate_release_payload(payload: DesktopReleaseCreateRequest, settings: Settings) -> None:
    version = parse_version(payload.version)
    minimum = parse_version(payload.minimum_supported_version)
    if minimum > version:
        raise AppError(
            "desktop.update.minimum_version_too_high",
            "最低受支持版本不能高于发布版本",
            status_code=422,
        )
    filename = payload.artifact_filename
    if (
        PurePath(filename).name != filename
        or Path(filename).suffix.lower() not in _ALLOWED_ARTIFACT_SUFFIXES
    ):
        raise AppError(
            "desktop.update.invalid_artifact_filename",
            "升级制品必须是无路径的 .msix、.msixbundle 或 .exe 文件名",
            status_code=422,
        )
    if payload.artifact_size_bytes > settings.desktop_update_max_artifact_bytes:
        raise AppError(
            "desktop.update.artifact_too_large",
            "升级制品超过服务端允许的大小",
            status_code=413,
            details={"max_bytes": settings.desktop_update_max_artifact_bytes},
        )
    if not payload.distribution_authorized:
        raise AppError(
            "desktop.update.distribution_authorization_required",
            "发布升级制品前必须确认拥有合法分发授权",
            status_code=422,
        )
    if len(payload.legal_declaration.strip()) < 20:
        raise AppError(
            "desktop.update.legal_declaration_required",
            "发布升级制品前必须提供不少于 20 个字符的合法性声明",
            status_code=422,
        )


def _to_response(release: DesktopRelease) -> DesktopReleaseResponse:
    return DesktopReleaseResponse(
        id=release.id,
        channel=release.channel,
        platform=release.platform,
        architecture=release.architecture,
        version=release.version,
        minimum_supported_version=release.minimum_supported_version,
        status=release.status,
        mandatory=release.mandatory,
        release_notes=release.release_notes,
        artifact_filename=release.artifact_filename,
        artifact_sha256=release.artifact_sha256,
        artifact_size_bytes=release.artifact_size_bytes,
        content_type=release.content_type,
        artifact_uploaded=release.artifact_storage_key is not None,
        distribution_authorized=release.distribution_authorized,
        legal_declaration=release.legal_declaration,
        download_count=release.download_count,
        created_at=release.created_at,
        updated_at=release.updated_at,
        published_at=release.published_at,
        withdrawn_at=release.withdrawn_at,
    )


def create_release(
    db: Session,
    settings: Settings,
    *,
    payload: DesktopReleaseCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> DesktopReleaseResponse:
    _validate_release_payload(payload, settings)
    release = DesktopRelease(
        id=new_id(),
        channel=payload.channel,
        platform=payload.platform,
        architecture=payload.architecture,
        version=payload.version.strip(),
        minimum_supported_version=payload.minimum_supported_version.strip(),
        mandatory=payload.mandatory,
        release_notes=payload.release_notes.strip(),
        artifact_filename=payload.artifact_filename,
        artifact_sha256=payload.artifact_sha256,
        artifact_size_bytes=payload.artifact_size_bytes,
        content_type=payload.content_type.strip().lower(),
        distribution_authorized=payload.distribution_authorized,
        legal_declaration=payload.legal_declaration.strip(),
        code_signature_status=CodeSignatureStatus.UNSIGNED,
        signer_subject=None,
        signer_thumbprint=None,
        created_by=principal.user.id,
    )
    db.add(release)
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="desktop.release.create",
        target_type="desktop_release",
        target_id=release.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "channel": payload.channel.value,
            "architecture": payload.architecture.value,
            "version": payload.version,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            "desktop.update.release_exists",
            "该通道、平台、架构与版本的发布记录已存在",
            status_code=409,
        ) from exc
    db.refresh(release)
    return _to_response(release)


def list_releases(db: Session) -> DesktopReleaseListResponse:
    releases = db.scalars(select(DesktopRelease).order_by(DesktopRelease.created_at.desc())).all()
    return DesktopReleaseListResponse(items=[_to_response(release) for release in releases])


def _require_release(db: Session, release_id: str) -> DesktopRelease:
    release = db.get(DesktopRelease, release_id)
    if release is None:
        raise AppError("desktop.update.release_not_found", "桌面发布记录不存在", status_code=404)
    return release


def _storage_root(settings: Settings) -> Path:
    root = Path(settings.desktop_update_storage_path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _artifact_path(settings: Settings, storage_key: str) -> Path:
    root = _storage_root(settings)
    path = (root / storage_key).resolve()
    if not path.is_relative_to(root):
        raise AppError(
            "desktop.update.invalid_storage_key", "升级制品存储路径无效", status_code=500
        )
    return path


async def upload_artifact(
    db: Session,
    settings: Settings,
    *,
    release_id: str,
    chunks: AsyncIterator[bytes],
    content_length: int | None,
    principal: Principal,
    context: ClientContext,
) -> DesktopReleaseResponse:
    release = _require_release(db, release_id)
    if release.status != DesktopReleaseStatus.DRAFT:
        raise AppError(
            "desktop.update.release_not_editable",
            "仅草稿发布可以上传制品",
            status_code=409,
        )
    maximum = min(settings.desktop_update_max_artifact_bytes, release.artifact_size_bytes)
    if content_length is not None and content_length > maximum:
        raise AppError(
            "desktop.update.artifact_size_mismatch",
            "上传制品大小与发布记录不一致",
            status_code=422,
            details={"expected_bytes": release.artifact_size_bytes},
        )

    root = _storage_root(settings)
    suffix = Path(release.artifact_filename).suffix.lower()
    storage_key = f"{release.id}{suffix}"
    destination = _artifact_path(settings, storage_key)
    temporary = root / f".{release.id}.{uuid4().hex}.upload"
    digest = hashlib.sha256()
    total = 0
    try:
        with temporary.open("xb") as stream:
            async for chunk in chunks:
                if not chunk:
                    continue
                total += len(chunk)
                if total > maximum:
                    raise AppError(
                        "desktop.update.artifact_size_mismatch",
                        "上传制品大小与发布记录不一致",
                        status_code=422,
                        details={"expected_bytes": release.artifact_size_bytes},
                    )
                digest.update(chunk)
                stream.write(chunk)
        calculated = digest.hexdigest()
        if total != release.artifact_size_bytes or calculated != release.artifact_sha256:
            raise AppError(
                "desktop.update.artifact_integrity_mismatch",
                "升级制品的大小或 SHA-256 与发布记录不一致",
                status_code=422,
                details={
                    "expected_bytes": release.artifact_size_bytes,
                    "received_bytes": total,
                    "expected_sha256": release.artifact_sha256,
                    "received_sha256": calculated,
                },
            )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

    release.artifact_storage_key = storage_key
    release.updated_at = utc_now()
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="desktop.release.artifact_upload",
        target_type="desktop_release",
        target_id=release.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"sha256": release.artifact_sha256, "size_bytes": total},
    )
    db.commit()
    db.refresh(release)
    return _to_response(release)


def _verify_stored_artifact(release: DesktopRelease, settings: Settings) -> None:
    if release.artifact_storage_key is None:
        raise AppError(
            "desktop.update.artifact_missing",
            "发布前必须上传升级制品",
            status_code=409,
        )
    path = _artifact_path(settings, release.artifact_storage_key)
    if not path.is_file():
        raise AppError(
            "desktop.update.artifact_missing",
            "服务端找不到升级制品",
            status_code=409,
        )
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(chunk)
            digest.update(chunk)
    if total != release.artifact_size_bytes or digest.hexdigest() != release.artifact_sha256:
        raise AppError(
            "desktop.update.artifact_integrity_mismatch",
            "服务端升级制品完整性校验失败",
            status_code=409,
        )


def publish_release(
    db: Session,
    settings: Settings,
    *,
    release_id: str,
    principal: Principal,
    context: ClientContext,
) -> DesktopReleaseResponse:
    release = _require_release(db, release_id)
    if release.status != DesktopReleaseStatus.DRAFT:
        raise AppError("desktop.update.release_not_publishable", "仅草稿可以发布", status_code=409)
    _verify_stored_artifact(release, settings)
    if not release.distribution_authorized or len(release.legal_declaration.strip()) < 20:
        raise AppError(
            "desktop.update.distribution_authorization_required",
            "发布升级制品前必须保留完整的合法分发授权声明",
            status_code=409,
        )
    release.status = DesktopReleaseStatus.PUBLISHED
    release.published_at = utc_now()
    release.updated_at = release.published_at
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="desktop.release.publish",
        target_type="desktop_release",
        target_id=release.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "channel": release.channel.value,
            "architecture": release.architecture.value,
            "version": release.version,
            "artifact_sha256": release.artifact_sha256,
            "distribution_authorized": release.distribution_authorized,
            "legal_declaration_sha256": hashlib.sha256(
                release.legal_declaration.encode("utf-8")
            ).hexdigest(),
        },
    )
    db.commit()
    db.refresh(release)
    return _to_response(release)


def withdraw_release(
    db: Session,
    *,
    release_id: str,
    principal: Principal,
    context: ClientContext,
) -> DesktopReleaseResponse:
    release = _require_release(db, release_id)
    if release.status != DesktopReleaseStatus.PUBLISHED:
        raise AppError(
            "desktop.update.release_not_withdrawable",
            "仅已发布版本可以撤回",
            status_code=409,
        )
    release.status = DesktopReleaseStatus.WITHDRAWN
    release.withdrawn_at = utc_now()
    release.updated_at = release.withdrawn_at
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="desktop.release.withdraw",
        target_type="desktop_release",
        target_id=release.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"version": release.version},
    )
    db.commit()
    db.refresh(release)
    return _to_response(release)


def check_for_update(
    db: Session,
    *,
    current_version: str,
    channel: DesktopReleaseChannel,
    platform: str,
    architecture: DesktopArchitecture,
    download_url_builder,
) -> DesktopUpdateCheckResponse:
    current = parse_version(current_version)
    releases = db.scalars(
        select(DesktopRelease).where(
            DesktopRelease.status == DesktopReleaseStatus.PUBLISHED,
            DesktopRelease.channel == channel,
            DesktopRelease.platform == platform,
            DesktopRelease.architecture == architecture,
            DesktopRelease.artifact_storage_key.is_not(None),
            DesktopRelease.distribution_authorized.is_(True),
            DesktopRelease.legal_declaration != "",
        )
    ).all()
    latest = max(releases, key=lambda item: parse_version(item.version), default=None)
    if latest is None:
        return DesktopUpdateCheckResponse(
            update_available=False,
            mandatory=False,
            current_version=current_version,
            latest_version=None,
            minimum_supported_version=None,
            channel=channel,
            platform=platform,
            architecture=architecture,
            release_id=None,
            release_notes="",
            published_at=None,
            download_url=None,
            artifact_filename=None,
            artifact_sha256=None,
            artifact_size_bytes=None,
            artifact_integrity=None,
            distribution_authorized=None,
        )
    update_available = current < parse_version(latest.version)
    mandatory = update_available and (
        latest.mandatory or current < parse_version(latest.minimum_supported_version)
    )
    return DesktopUpdateCheckResponse(
        update_available=update_available,
        mandatory=mandatory,
        current_version=current_version,
        latest_version=latest.version,
        minimum_supported_version=latest.minimum_supported_version,
        channel=channel,
        platform=platform,
        architecture=architecture,
        release_id=latest.id if update_available else None,
        release_notes=latest.release_notes if update_available else "",
        published_at=latest.published_at if update_available else None,
        download_url=str(download_url_builder(latest.id)) if update_available else None,
        artifact_filename=latest.artifact_filename if update_available else None,
        artifact_sha256=latest.artifact_sha256 if update_available else None,
        artifact_size_bytes=latest.artifact_size_bytes if update_available else None,
        artifact_integrity="sha256-verified" if update_available else None,
        distribution_authorized=latest.distribution_authorized if update_available else None,
    )


def prepare_download(
    db: Session,
    settings: Settings,
    *,
    release_id: str,
) -> tuple[DesktopRelease, Path]:
    release = _require_release(db, release_id)
    if (
        release.status != DesktopReleaseStatus.PUBLISHED
        or release.artifact_storage_key is None
        or not release.distribution_authorized
        or not release.legal_declaration.strip()
    ):
        raise AppError(
            "desktop.update.download_unavailable",
            "该升级制品当前不可下载",
            status_code=404,
        )
    path = _artifact_path(settings, release.artifact_storage_key)
    if not path.is_file():
        raise AppError(
            "desktop.update.download_unavailable",
            "该升级制品当前不可下载",
            status_code=404,
        )
    _verify_stored_artifact(release, settings)
    release.download_count += 1
    db.commit()
    return release, path


