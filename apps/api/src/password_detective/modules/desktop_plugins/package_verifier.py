from __future__ import annotations

import base64
import hashlib
import json
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from password_detective.core.errors import AppError
from password_detective.modules.desktop_plugins.schemas import PLUGIN_CAPABILITIES

_MANIFEST_PATH = "manifest.json"
_SIGNATURE_PATH = "signature.ed25519"
_MAX_ENTRIES = 2_048
_MAX_MANIFEST_BYTES = 128 * 1024
_MAX_SIGNATURE_BYTES = 256
_MAX_SINGLE_FILE_BYTES = 256 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 100


@dataclass(frozen=True)
class VerifiedPluginPackage:
    manifest: dict[str, Any]
    manifest_sha256: str
    signature_base64: str
    expanded_size_bytes: int


def _invalid(message: str, *, code: str = "desktop_plugin.invalid_package") -> AppError:
    return AppError(code, message, status_code=422)


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid("插件清单包含重复字段")
        result[key] = value
    return result


def _read_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, AppError):
            raise
        raise _invalid(f"{label}不是有效的严格 UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise _invalid(f"{label}必须是 JSON 对象")
    return value


def _validate_archive_path(info: zipfile.ZipInfo) -> str:
    raw = info.filename
    if (
        not raw
        or len(raw) > 512
        or "\\" in raw
        or ":" in raw
        or raw.startswith("/")
        or any(ord(character) < 32 for character in raw)
    ):
        raise _invalid("插件包包含非法路径")
    normalized = raw[:-1] if raw.endswith("/") else raw
    parts = PurePosixPath(normalized).parts
    if not normalized or any(part in {"", ".", ".."} for part in parts):
        raise _invalid("插件包包含绝对路径或路径穿越")
    unix_type = (info.external_attr >> 16) & 0xF000
    if unix_type in {stat.S_IFLNK, stat.S_IFBLK, stat.S_IFCHR, stat.S_IFIFO, stat.S_IFSOCK}:
        raise _invalid("插件包不允许链接、设备文件或其他特殊文件")
    if info.flag_bits & 0x1:
        raise _invalid("插件包不允许加密 ZIP 条目")
    return normalized


def _hash_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(info, "r") as stream:
        while chunk := stream.read(64 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_bounded(archive: zipfile.ZipFile, info: zipfile.ZipInfo, maximum: int) -> bytes:
    if info.file_size > maximum:
        raise _invalid(f"{info.filename} 超出大小限制")
    with archive.open(info, "r") as stream:
        content = stream.read(maximum + 1)
    if len(content) > maximum:
        raise _invalid(f"{info.filename} 超出大小限制")
    return content


def _list_of_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise _invalid(f"插件清单 {label} 必须是字符串数组")
    return value


def _dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid(f"插件清单 {label} 必须是对象")
    return value


def _validate_manifest(
    manifest: dict[str, Any],
    *,
    entries: dict[str, zipfile.ZipInfo],
    architecture: str,
    project_slug: str,
    semver: str,
    signing_key_id: str,
    public_key_base64: str,
    protocol_min: int,
    protocol_max: int,
    host_min: str,
    host_max: str,
    requested_capabilities: list[str],
) -> None:
    required_fields = {
        "schema",
        "plugin_id",
        "version",
        "display_name",
        "description",
        "publisher_key_id",
        "publisher_public_key",
        "protocol",
        "host",
        "runtime",
        "commands",
        "capabilities",
        "limits",
    }
    if set(manifest) != required_fields:
        raise _invalid("插件清单字段不完整或包含未知字段")
    if (
        manifest["schema"] != "pd.plugin/v1"
        or manifest["plugin_id"] != project_slug
        or manifest["version"] != semver
        or manifest["publisher_key_id"] != signing_key_id
    ):
        raise _invalid("插件清单 ID、版本或签名密钥与版本草稿不一致")
    try:
        package_public_key = base64.b64decode(manifest["publisher_public_key"], validate=True)
        registered_public_key = base64.b64decode(public_key_base64, validate=True)
    except (TypeError, ValueError) as exc:
        raise _invalid("插件清单开发者公钥不是有效 Base64") from exc
    if package_public_key != registered_public_key:
        raise _invalid("插件清单开发者公钥与登记密钥不一致")

    protocol = _dict(manifest["protocol"], "protocol")
    host = _dict(manifest["host"], "host")
    runtime = _dict(manifest["runtime"], "runtime")
    capabilities = _dict(manifest["capabilities"], "capabilities")
    if protocol != {"min": protocol_min, "max": protocol_max}:
        raise _invalid("插件清单协议范围与版本草稿不一致")
    if host != {"min_version": host_min, "max_version": host_max}:
        raise _invalid("插件清单宿主范围与版本草稿不一致")
    if runtime.get("kind") != "process":
        raise _invalid("插件运行时必须为 process")
    entrypoints = _dict(runtime.get("entrypoints"), "runtime.entrypoints")
    entrypoint = entrypoints.get(architecture)
    if (
        not isinstance(entrypoint, str)
        or not entrypoint.startswith("bin/")
        or not entrypoint.lower().endswith(".exe")
        or entrypoint not in entries
        or entries[entrypoint].is_dir()
    ):
        raise _invalid(f"插件包不包含 {architecture} 的有效入口程序")

    required = _list_of_strings(capabilities.get("required"), "capabilities.required")
    optional = _list_of_strings(capabilities.get("optional"), "capabilities.optional")
    if set(required) & set(optional) or len(required + optional) != len(set(required + optional)):
        raise _invalid("插件权限包含重复项")
    if set(required + optional) - PLUGIN_CAPABILITIES:
        raise _invalid("插件清单包含未知权限")
    if set(required + optional) != set(requested_capabilities):
        raise _invalid("插件清单权限与版本草稿申请权限不一致")
    if "ui:command" not in required:
        raise _invalid("命令型插件必须把 ui:command 声明为必需权限")

    commands = manifest["commands"]
    if not isinstance(commands, list) or not 1 <= len(commands) <= 64:
        raise _invalid("插件命令数量无效")
    command_ids: set[str] = set()
    for command in commands:
        if not isinstance(command, dict) or set(command) != {"id", "title", "input_schema"}:
            raise _invalid("插件命令定义无效")
        command_id = command["id"]
        schema_path = command["input_schema"]
        if not isinstance(command_id, str) or not command_id or command_id in command_ids:
            raise _invalid("插件命令 ID 无效或重复")
        command_ids.add(command_id)
        if (
            not isinstance(schema_path, str)
            or not schema_path.startswith("schemas/")
            or schema_path not in entries
            or entries[schema_path].is_dir()
        ):
            raise _invalid("插件命令输入 Schema 缺失")

        try:
            schema = _read_json(_read_bounded(archive, entries[schema_path], _MAX_MANIFEST_BYTES), "命令输入 Schema")
        except AppError:
            raise
        for field in schema.get("properties", {}).values():
            if not isinstance(field, dict):
                continue
            if field.get("format") == "theme-background" and "ui:theme" not in required + optional:
                raise _invalid("主题背景输入必须申请 ui:theme 权限")
            if field.get("format") not in {None, "file", "theme-background"}:
                raise _invalid("命令输入 Schema 包含不支持的格式")


def verify_plugin_package(
    path: Path,
    *,
    architecture: str,
    project_slug: str,
    semver: str,
    signing_key_id: str,
    public_key_base64: str,
    protocol_min: int,
    protocol_max: int,
    host_min: str,
    host_max: str,
    requested_capabilities: list[str],
    max_expanded_bytes: int,
) -> VerifiedPluginPackage:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            if not 3 <= len(archive.infolist()) <= _MAX_ENTRIES:
                raise _invalid("插件包文件数量超出允许范围")
            entries: dict[str, zipfile.ZipInfo] = {}
            files: list[tuple[str, int, str]] = []
            expanded_size = 0
            for info in archive.infolist():
                normalized = _validate_archive_path(info)
                folded = normalized.casefold()
                if any(existing.casefold() == folded for existing in entries):
                    raise _invalid("插件包包含重复或仅大小写不同的路径")
                entries[normalized] = info
                if info.is_dir():
                    continue
                expanded_size += info.file_size
                ratio = info.file_size / info.compress_size if info.compress_size else 0
                if (
                    info.file_size > _MAX_SINGLE_FILE_BYTES
                    or expanded_size > max_expanded_bytes
                    or (info.file_size > 1_024 and not info.compress_size)
                    or ratio > _MAX_COMPRESSION_RATIO
                ):
                    raise _invalid("插件包单文件、展开大小或压缩比超出允许范围")
                files.append((normalized, info.file_size, _hash_entry(archive, info)))

            manifest_info = entries.get(_MANIFEST_PATH)
            signature_info = entries.get(_SIGNATURE_PATH)
            if (
                manifest_info is None
                or signature_info is None
                or manifest_info.is_dir()
                or signature_info.is_dir()
            ):
                raise _invalid("插件包缺少 manifest.json 或 signature.ed25519")
            manifest_bytes = _read_bounded(archive, manifest_info, _MAX_MANIFEST_BYTES)
            manifest = _read_json(manifest_bytes, "插件清单")
            _validate_manifest(
                manifest,
                entries=entries,
                architecture=architecture,
                project_slug=project_slug,
                semver=semver,
                signing_key_id=signing_key_id,
                public_key_base64=public_key_base64,
                protocol_min=protocol_min,
                protocol_max=protocol_max,
                host_min=host_min,
                host_max=host_max,
                requested_capabilities=requested_capabilities,
            )
            for command in manifest["commands"]:
                schema_info = entries[command["input_schema"]]
                _read_json(
                    _read_bounded(archive, schema_info, _MAX_MANIFEST_BYTES),
                    "命令输入 Schema",
                )
            try:
                signature_base64 = _read_bounded(
                    archive, signature_info, _MAX_SIGNATURE_BYTES
                ).decode("utf-8")
                signature = base64.b64decode(signature_base64, validate=True)
                public_key = base64.b64decode(public_key_base64, validate=True)
            except (UnicodeDecodeError, ValueError) as exc:
                raise _invalid("插件签名或公钥不是有效 Base64") from exc
            payload = "PD-PDPKG-SIGNATURE-V1\n" + "".join(
                f"{filename}\n{length}\n{digest}\n"
                for filename, length, digest in sorted(
                    (item for item in files if item[0].casefold() != _SIGNATURE_PATH),
                    key=lambda item: item[0].encode("utf-16-be"),
                )
            )
            try:
                Ed25519PublicKey.from_public_bytes(public_key).verify(
                    signature, payload.encode("utf-8")
                )
            except (ValueError, InvalidSignature) as exc:
                raise _invalid(
                    "插件开发者 Ed25519 签名无效",
                    code="desktop_plugin.invalid_signature",
                ) from exc
            manifest_sha256 = next(
                digest for filename, _, digest in files if filename == _MANIFEST_PATH
            )
            return VerifiedPluginPackage(
                manifest=manifest,
                manifest_sha256=manifest_sha256,
                signature_base64=signature_base64,
                expanded_size_bytes=expanded_size,
            )
    except zipfile.BadZipFile as exc:
        raise _invalid("插件包不是有效的受限 ZIP 文件") from exc
