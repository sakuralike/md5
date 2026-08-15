from __future__ import annotations

import hashlib
import os
import re
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import Request

from password_detective.core.config import Settings
from password_detective.core.errors import AppError

_ALLOWED_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
_ASSET_NAME_PATTERN = re.compile(r"^[0-9a-f]{64}\.(?:png|jpg|webp)$")


@dataclass(frozen=True, slots=True)
class StoredSiteLogo:
    url: str
    content_type: str
    size_bytes: int
    sha256: str


def _detect_content_type(payload: bytes) -> str | None:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith(b"\xff\xd8\xff") and payload.endswith(b"\xff\xd9"):
        return "image/jpeg"
    if len(payload) >= 12 and payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return "image/webp"
    return None


async def store_site_logo(request: Request, settings: Settings) -> StoredSiteLogo:
    declared_content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if declared_content_type not in _ALLOWED_CONTENT_TYPES:
        raise AppError(
            "admin.site_logo_content_type_invalid",
            "Logo 仅支持 PNG、JPEG 或 WebP 图片",
            status_code=415,
        )

    declared_length = request.headers.get("content-length")
    if declared_length:
        try:
            if int(declared_length) > settings.site_logo_max_bytes:
                raise AppError(
                    "admin.site_logo_too_large",
                    "Logo 图片大小超过限制",
                    status_code=413,
                    details={"max_bytes": settings.site_logo_max_bytes},
                )
        except ValueError as exc:
            raise AppError(
                "request.content_length_invalid",
                "Content-Length 请求头无效",
                status_code=400,
            ) from exc

    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > settings.site_logo_max_bytes:
            raise AppError(
                "admin.site_logo_too_large",
                "Logo 图片大小超过限制",
                status_code=413,
                details={"max_bytes": settings.site_logo_max_bytes},
            )
        payload.extend(chunk)
    if not payload:
        raise AppError("admin.site_logo_empty", "Logo 图片不能为空", status_code=422)

    binary = bytes(payload)
    detected_content_type = _detect_content_type(binary)
    if detected_content_type is None or detected_content_type != declared_content_type:
        raise AppError(
            "admin.site_logo_signature_invalid",
            "图片内容与声明的文件类型不一致",
            status_code=422,
        )

    digest = hashlib.sha256(binary).hexdigest()
    suffix = _ALLOWED_CONTENT_TYPES[detected_content_type]
    asset_name = f"{digest}{suffix}"
    storage_root = Path(settings.site_asset_storage_path).expanduser().resolve()
    storage_root.mkdir(parents=True, exist_ok=True)
    target = storage_root / asset_name
    if not target.exists():
        temporary = storage_root / f".{asset_name}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(binary)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            with suppress(OSError):
                target.chmod(0o640)
        finally:
            temporary.unlink(missing_ok=True)

    return StoredSiteLogo(
        url=f"/api/v1/site/assets/logo/{asset_name}",
        content_type=detected_content_type,
        size_bytes=len(binary),
        sha256=digest,
    )


def resolve_site_logo(settings: Settings, asset_name: str) -> tuple[Path, str]:
    if not _ASSET_NAME_PATTERN.fullmatch(asset_name):
        raise AppError("site.logo_not_found", "Logo 图片不存在", status_code=404)
    storage_root = Path(settings.site_asset_storage_path).expanduser().resolve()
    target = (storage_root / asset_name).resolve()
    if target.parent != storage_root or not target.is_file():
        raise AppError("site.logo_not_found", "Logo 图片不存在", status_code=404)
    suffix_content_types = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
    return target, suffix_content_types[target.suffix]


_ANNOUNCEMENT_ASSET_NAME_PATTERN = re.compile(r"^[0-9a-f]{64}\.(?:png|jpg|webp)$")
_ANNOUNCEMENT_ASSET_DIRECTORY = "desktop-announcements"


@dataclass(frozen=True, slots=True)
class StoredDesktopAnnouncementImage:
    url: str
    content_type: str
    size_bytes: int
    sha256: str


async def store_desktop_announcement_image(
    request: Request,
    settings: Settings,
) -> StoredDesktopAnnouncementImage:
    declared_content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if declared_content_type not in _ALLOWED_CONTENT_TYPES:
        raise AppError(
            "admin.desktop_announcement_image_content_type_invalid",
            "公告图片仅支持 PNG、JPEG 或 WebP 图片",
            status_code=415,
        )

    max_bytes = settings.desktop_announcement_image_max_bytes
    declared_length = request.headers.get("content-length")
    if declared_length:
        try:
            if int(declared_length) > max_bytes:
                raise AppError(
                    "admin.desktop_announcement_image_too_large",
                    "公告图片大小超过限制",
                    status_code=413,
                    details={"max_bytes": max_bytes},
                )
        except ValueError as exc:
            raise AppError(
                "request.content_length_invalid",
                "Content-Length 请求头无效",
                status_code=400,
            ) from exc

    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > max_bytes:
            raise AppError(
                "admin.desktop_announcement_image_too_large",
                "公告图片大小超过限制",
                status_code=413,
                details={"max_bytes": max_bytes},
            )
        payload.extend(chunk)
    if not payload:
        raise AppError(
            "admin.desktop_announcement_image_empty",
            "公告图片不能为空",
            status_code=422,
        )

    binary = bytes(payload)
    detected_content_type = _detect_content_type(binary)
    if detected_content_type is None or detected_content_type != declared_content_type:
        raise AppError(
            "admin.desktop_announcement_image_signature_invalid",
            "图片内容与声明的文件类型不一致",
            status_code=422,
        )

    digest = hashlib.sha256(binary).hexdigest()
    suffix = _ALLOWED_CONTENT_TYPES[detected_content_type]
    storage_root = (
        Path(settings.site_asset_storage_path).expanduser().resolve()
        / _ANNOUNCEMENT_ASSET_DIRECTORY
    )
    storage_root.mkdir(parents=True, exist_ok=True)
    asset_name = f"{digest}{suffix}"
    target = storage_root / asset_name
    if not target.exists():
        temporary = storage_root / f".{asset_name}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(binary)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            with suppress(OSError):
                target.chmod(0o640)
        finally:
            temporary.unlink(missing_ok=True)

    return StoredDesktopAnnouncementImage(
        url=f"/api/v1/desktop/announcements/assets/{asset_name}",
        content_type=detected_content_type,
        size_bytes=len(binary),
        sha256=digest,
    )


def resolve_desktop_announcement_image(settings: Settings, asset_name: str) -> tuple[Path, str]:
    if not _ANNOUNCEMENT_ASSET_NAME_PATTERN.fullmatch(asset_name):
        raise AppError("desktop.announcement_image_not_found", "公告图片不存在", status_code=404)
    storage_root = (
        Path(settings.site_asset_storage_path).expanduser().resolve()
        / _ANNOUNCEMENT_ASSET_DIRECTORY
    )
    target = (storage_root / asset_name).resolve()
    if target.parent != storage_root or not target.is_file():
        raise AppError("desktop.announcement_image_not_found", "公告图片不存在", status_code=404)
    suffix_content_types = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
    return target, suffix_content_types[target.suffix]


_WEB_ANNOUNCEMENT_ASSET_DIRECTORY = "web-announcements"


@dataclass(frozen=True, slots=True)
class StoredWebAnnouncementImage:
    url: str
    content_type: str
    size_bytes: int
    sha256: str


async def store_web_announcement_image(
    request: Request,
    settings: Settings,
) -> StoredWebAnnouncementImage:
    declared_content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if declared_content_type not in _ALLOWED_CONTENT_TYPES:
        raise AppError(
            "admin.web_announcement_image_content_type_invalid",
            "Web 公告图片仅支持 PNG、JPEG 或 WebP 图片",
            status_code=415,
        )

    max_bytes = settings.desktop_announcement_image_max_bytes
    declared_length = request.headers.get("content-length")
    if declared_length:
        try:
            if int(declared_length) > max_bytes:
                raise AppError(
                    "admin.web_announcement_image_too_large",
                    "Web 公告图片大小超过限制",
                    status_code=413,
                    details={"max_bytes": max_bytes},
                )
        except ValueError as exc:
            raise AppError(
                "request.content_length_invalid",
                "Content-Length 请求头无效",
                status_code=400,
            ) from exc

    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > max_bytes:
            raise AppError(
                "admin.web_announcement_image_too_large",
                "Web 公告图片大小超过限制",
                status_code=413,
                details={"max_bytes": max_bytes},
            )
        payload.extend(chunk)
    if not payload:
        raise AppError(
            "admin.web_announcement_image_empty",
            "Web 公告图片不能为空",
            status_code=422,
        )

    binary = bytes(payload)
    detected_content_type = _detect_content_type(binary)
    if detected_content_type is None or detected_content_type != declared_content_type:
        raise AppError(
            "admin.web_announcement_image_signature_invalid",
            "图片内容与声明的文件类型不一致",
            status_code=422,
        )

    digest = hashlib.sha256(binary).hexdigest()
    suffix = _ALLOWED_CONTENT_TYPES[detected_content_type]
    storage_root = (
        Path(settings.site_asset_storage_path).expanduser().resolve()
        / _WEB_ANNOUNCEMENT_ASSET_DIRECTORY
    )
    storage_root.mkdir(parents=True, exist_ok=True)
    asset_name = f"{digest}{suffix}"
    target = storage_root / asset_name
    if not target.exists():
        temporary = storage_root / f".{asset_name}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(binary)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            with suppress(OSError):
                target.chmod(0o640)
        finally:
            temporary.unlink(missing_ok=True)

    return StoredWebAnnouncementImage(
        url=f"/api/v1/web/announcements/assets/{asset_name}",
        content_type=detected_content_type,
        size_bytes=len(binary),
        sha256=digest,
    )


def resolve_web_announcement_image(settings: Settings, asset_name: str) -> tuple[Path, str]:
    if not _ANNOUNCEMENT_ASSET_NAME_PATTERN.fullmatch(asset_name):
        raise AppError("web.announcement_image_not_found", "Web 公告图片不存在", status_code=404)
    storage_root = (
        Path(settings.site_asset_storage_path).expanduser().resolve()
        / _WEB_ANNOUNCEMENT_ASSET_DIRECTORY
    )
    target = (storage_root / asset_name).resolve()
    if target.parent != storage_root or not target.is_file():
        raise AppError("web.announcement_image_not_found", "Web 公告图片不存在", status_code=404)
    suffix_content_types = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
    return target, suffix_content_types[target.suffix]


_COMMUNITY_AVATAR_ASSET_DIRECTORY = "community-avatars"


@dataclass(frozen=True, slots=True)
class StoredCommunityAvatar:
    url: str
    content_type: str
    size_bytes: int
    sha256: str


async def store_community_avatar(request: Request, settings: Settings) -> StoredCommunityAvatar:
    declared_content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if declared_content_type not in _ALLOWED_CONTENT_TYPES:
        raise AppError(
            "community.avatar_content_type_invalid",
            "头像仅支持 PNG、JPEG 或 WebP 图片",
            status_code=415,
        )
    declared_length = request.headers.get("content-length")
    if declared_length:
        try:
            if int(declared_length) > settings.community_avatar_max_bytes:
                raise AppError(
                    "community.avatar_too_large",
                    "头像图片大小超过限制",
                    status_code=413,
                    details={"max_bytes": settings.community_avatar_max_bytes},
                )
        except ValueError as exc:
            raise AppError(
                "request.content_length_invalid", "Content-Length 请求头无效", status_code=400
            ) from exc
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > settings.community_avatar_max_bytes:
            raise AppError(
                "community.avatar_too_large",
                "头像图片大小超过限制",
                status_code=413,
                details={"max_bytes": settings.community_avatar_max_bytes},
            )
        payload.extend(chunk)
    if not payload:
        raise AppError("community.avatar_empty", "头像图片不能为空", status_code=422)
    binary = bytes(payload)
    detected_content_type = _detect_content_type(binary)
    if detected_content_type is None or detected_content_type != declared_content_type:
        raise AppError(
            "community.avatar_signature_invalid", "图片内容与声明的文件类型不一致", status_code=422
        )
    digest = hashlib.sha256(binary).hexdigest()
    asset_name = f"{digest}{_ALLOWED_CONTENT_TYPES[detected_content_type]}"
    storage_root = (
        Path(settings.site_asset_storage_path).expanduser().resolve()
        / _COMMUNITY_AVATAR_ASSET_DIRECTORY
    )
    storage_root.mkdir(parents=True, exist_ok=True)
    target = storage_root / asset_name
    if not target.exists():
        temporary = storage_root / f".{asset_name}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(binary)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            with suppress(OSError):
                target.chmod(0o640)
        finally:
            temporary.unlink(missing_ok=True)
    return StoredCommunityAvatar(
        url=f"/api/v1/site/assets/avatars/{asset_name}",
        content_type=detected_content_type,
        size_bytes=len(binary),
        sha256=digest,
    )


def resolve_community_avatar(settings: Settings, asset_name: str) -> tuple[Path, str]:
    if not _ASSET_NAME_PATTERN.fullmatch(asset_name):
        raise AppError("community.avatar_not_found", "头像图片不存在", status_code=404)
    storage_root = (
        Path(settings.site_asset_storage_path).expanduser().resolve()
        / _COMMUNITY_AVATAR_ASSET_DIRECTORY
    )
    target = (storage_root / asset_name).resolve()
    if target.parent != storage_root or not target.is_file():
        raise AppError("community.avatar_not_found", "头像图片不存在", status_code=404)
    content_types = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
    return target, content_types[target.suffix]
