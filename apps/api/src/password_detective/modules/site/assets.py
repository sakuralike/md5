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
