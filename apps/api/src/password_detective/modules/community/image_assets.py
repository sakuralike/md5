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
_DIRECTORY = "community-images"


@dataclass(frozen=True, slots=True)
class StoredCommunityPostImage:
    asset_name: str
    content_type: str
    size_bytes: int
    sha256: str
    width: int
    height: int


def _png_dimensions(payload: bytes) -> tuple[int, int]:
    if len(payload) < 33 or not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("invalid png")
    if any(marker in payload for marker in (b"eXIf", b"tEXt", b"iTXt", b"zTXt", b"acTL")):
        raise ValueError("png metadata or animation is not allowed")
    width = int.from_bytes(payload[16:20], "big")
    height = int.from_bytes(payload[20:24], "big")
    offset = 8
    while offset + 12 <= len(payload):
        length = int.from_bytes(payload[offset : offset + 4], "big")
        chunk_type = payload[offset + 4 : offset + 8]
        if chunk_type in {b"eXIf", b"tEXt", b"iTXt", b"zTXt", b"acTL"}:
            raise ValueError("png metadata or animation is not allowed")
        offset += 12 + length
    return width, height


def _jpeg_dimensions(payload: bytes) -> tuple[int, int]:
    if len(payload) < 4 or not payload.startswith(b"\xff\xd8") or not payload.endswith(b"\xff\xd9"):
        raise ValueError("invalid jpeg")
    offset = 2
    dimensions: tuple[int, int] | None = None
    while offset + 4 <= len(payload):
        if payload[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(payload) and payload[offset] == 0xFF:
            offset += 1
        if offset >= len(payload):
            break
        marker = payload[offset]
        offset += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(payload):
            break
        length = int.from_bytes(payload[offset : offset + 2], "big")
        if length < 2 or offset + length > len(payload):
            raise ValueError("invalid jpeg segment")
        if 0xE1 <= marker <= 0xEF or marker == 0xFE:
            raise ValueError("jpeg metadata is not allowed")
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if length < 7:
                raise ValueError("invalid jpeg dimensions")
            height = int.from_bytes(payload[offset + 3 : offset + 5], "big")
            width = int.from_bytes(payload[offset + 5 : offset + 7], "big")
            dimensions = (width, height)
        if marker == 0xDA:
            break
        offset += length
    if dimensions is None:
        raise ValueError("jpeg dimensions missing")
    return dimensions


def _webp_dimensions(payload: bytes) -> tuple[int, int]:
    if len(payload) < 30 or not payload.startswith(b"RIFF") or payload[8:12] != b"WEBP":
        raise ValueError("invalid webp")
    offset = 12
    dimensions: tuple[int, int] | None = None
    while offset + 8 <= len(payload):
        chunk_type = payload[offset : offset + 4]
        length = int.from_bytes(payload[offset + 4 : offset + 8], "little")
        data = payload[offset + 8 : offset + 8 + length]
        if len(data) != length:
            raise ValueError("invalid webp chunk")
        if chunk_type in {b"EXIF", b"XMP ", b"ANIM", b"ANMF"}:
            raise ValueError("webp metadata or animation is not allowed")
        if chunk_type == b"VP8X" and len(data) >= 10:
            if data[0] & 0x0E:
                raise ValueError("webp metadata or animation is not allowed")
            dimensions = (
                int.from_bytes(data[4:7], "little") + 1,
                int.from_bytes(data[7:10], "little") + 1,
            )
        elif chunk_type == b"VP8 " and len(data) >= 10 and data[3:6] == b"\x9d\x01\x2a":
            dimensions = (
                int.from_bytes(data[6:8], "little") & 0x3FFF,
                int.from_bytes(data[8:10], "little") & 0x3FFF,
            )
        elif chunk_type == b"VP8L" and len(data) >= 5 and data[0] == 0x2F:
            bits = int.from_bytes(data[1:5], "little")
            dimensions = ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        offset += 8 + length + (length % 2)
    if dimensions is None:
        raise ValueError("webp dimensions missing")
    return dimensions


def _inspect_image(payload: bytes, content_type: str) -> tuple[int, int]:
    inspectors = {
        "image/png": _png_dimensions,
        "image/jpeg": _jpeg_dimensions,
        "image/webp": _webp_dimensions,
    }
    try:
        width, height = inspectors[content_type](payload)
    except (KeyError, ValueError) as exc:
        raise AppError(
            "community.image_signature_invalid",
            "图片内容、元数据或声明的文件类型不符合要求",
            status_code=422,
        ) from exc
    if width <= 0 or height <= 0:
        raise AppError("community.image_dimensions_invalid", "图片尺寸无效", status_code=422)
    return width, height


async def store_community_post_image(
    request: Request,
    settings: Settings,
    *,
    max_bytes: int,
    max_pixels: int,
) -> StoredCommunityPostImage:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise AppError(
            "community.image_content_type_invalid",
            "主题图片仅支持 PNG、JPEG 或 WebP",
            status_code=415,
        )
    declared_length = request.headers.get("content-length")
    if declared_length:
        try:
            if int(declared_length) > max_bytes:
                raise AppError(
                    "community.image_too_large",
                    "主题图片大小超过配置限制",
                    status_code=413,
                    details={"max_bytes": max_bytes},
                )
        except ValueError as exc:
            raise AppError(
                "request.content_length_invalid", "Content-Length 请求头无效", status_code=400
            ) from exc
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > max_bytes:
            raise AppError(
                "community.image_too_large",
                "主题图片大小超过配置限制",
                status_code=413,
                details={"max_bytes": max_bytes},
            )
        payload.extend(chunk)
    if not payload:
        raise AppError("community.image_empty", "主题图片不能为空", status_code=422)
    binary = bytes(payload)
    width, height = _inspect_image(binary, content_type)
    if width * height > max_pixels:
        raise AppError(
            "community.image_pixels_exceeded",
            "主题图片像素总量超过配置限制",
            status_code=413,
            details={"max_pixels": max_pixels},
        )
    digest = hashlib.sha256(binary).hexdigest()
    asset_name = f"{digest}{_ALLOWED_CONTENT_TYPES[content_type]}"
    storage_root = Path(settings.site_asset_storage_path).expanduser().resolve() / _DIRECTORY
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
    return StoredCommunityPostImage(
        asset_name=asset_name,
        content_type=content_type,
        size_bytes=len(binary),
        sha256=digest,
        width=width,
        height=height,
    )


def resolve_community_post_image(settings: Settings, asset_name: str) -> tuple[Path, str]:
    if not _ASSET_NAME_PATTERN.fullmatch(asset_name):
        raise AppError("community.image_not_found", "主题图片不存在", status_code=404)
    storage_root = Path(settings.site_asset_storage_path).expanduser().resolve() / _DIRECTORY
    target = (storage_root / asset_name).resolve()
    if target.parent != storage_root or not target.is_file():
        raise AppError("community.image_not_found", "主题图片不存在", status_code=404)
    content_types = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
    return target, content_types[target.suffix]
