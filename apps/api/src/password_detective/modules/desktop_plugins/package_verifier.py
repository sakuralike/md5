from __future__ import annotations

import base64
import hashlib
import json
import math
import re
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
_PROVENANCE_PATH = "provenance.json"
_MAX_ENTRIES = 2_048
_MAX_MANIFEST_BYTES = 128 * 1024
_MAX_SIGNATURE_BYTES = 256
_MAX_SINGLE_FILE_BYTES = 256 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 100
_SEMVER_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
_COMMAND_SCHEMA_ROOT_FIELDS = {"type", "properties", "required", "additionalProperties"}
_COMMAND_SCHEMA_PROPERTY_FIELDS = {
    "type",
    "title",
    "description",
    "enum",
    "format",
    "default",
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
}
_COMMAND_SCHEMA_TYPES = {"string", "integer", "number", "boolean"}


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
    allowed_fields = required_fields | {"migration"}
    if not required_fields.issubset(manifest) or set(manifest) - allowed_fields:
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

    migration = manifest.get("migration")
    if migration is not None:
        if not isinstance(migration, dict) or set(migration) != {
            "required",
            "from_versions",
            "strategy",
        }:
            raise _invalid("插件迁移声明字段不完整或包含未知字段")
        from_versions = migration["from_versions"]
        if (
            not isinstance(migration["required"], bool)
            or migration["strategy"] != "idempotent"
            or not isinstance(from_versions, list)
            or len(from_versions) > 128
            or any(
                not isinstance(version, str) or _SEMVER_PATTERN.fullmatch(version) is None
                for version in from_versions
            )
            or len(from_versions) != len(
                {version for version in from_versions if isinstance(version, str)}
            )
            or migration["required"]
            and not from_versions
        ):
            raise _invalid("插件迁移声明无效，必须使用幂等策略和有效来源版本")

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
    source_review_mode: str,
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
            _validate_provenance(
                archive,
                entries=entries,
                files=files,
                source_review_mode=source_review_mode,
            )
            for command in manifest["commands"]:
                schema_info = entries[command["input_schema"]]
                command_schema = _read_json(
                    _read_bounded(archive, schema_info, _MAX_MANIFEST_BYTES),
                    "命令输入 Schema",
                )
                _validate_command_input_schema(
                    command_schema,
                    requested_capabilities=requested_capabilities,
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


def _validate_provenance(
    archive: zipfile.ZipFile,
    *,
    entries: dict[str, zipfile.ZipInfo],
    files: list[tuple[str, int, str]],
    source_review_mode: str,
) -> None:
    provenance_info = entries.get(_PROVENANCE_PATH)
    required = source_review_mode in {"source", "reproducible"}
    if provenance_info is None or provenance_info.is_dir():
        if required:
            raise _invalid("源码审查模式必须提供签名构建溯源 provenance.json")
        return
    provenance = _read_json(
        _read_bounded(archive, provenance_info, _MAX_MANIFEST_BYTES),
        "构建溯源",
    )
    if set(provenance) != {"schema", "source_commit", "source_files", "sbom", "binaries"}:
        raise _invalid("构建溯源字段不完整或包含未知字段")
    commit = provenance.get("source_commit")
    if (
        provenance.get("schema") != "pd.plugin.provenance/v1"
        or not isinstance(commit, str)
        or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit) is None
        or required
        and set(commit) == {"0"}
    ):
        raise _invalid("构建溯源 Schema 或源码提交无效")
    actual = {
        path: {"path": path, "size_bytes": size, "sha256": digest}
        for path, size, digest in files
        if path != _SIGNATURE_PATH
    }
    expected_source = _provenance_records(provenance.get("source_files"), "源码")
    expected_binaries = _provenance_records(provenance.get("binaries"), "二进制")
    expected_sbom = _provenance_record(provenance.get("sbom"), "SBOM")
    actual_source = {path: value for path, value in actual.items() if path.startswith("source/")}
    actual_binaries = {path: value for path, value in actual.items() if path.startswith("bin/")}
    if (
        expected_source != actual_source
        or expected_binaries != actual_binaries
        or expected_sbom != actual.get("sbom.cdx.json")
        or required
        and not actual_source
    ):
        raise _invalid("构建溯源与源码、SBOM 或二进制摘要不一致")


def _provenance_records(value: Any, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise _invalid(f"构建溯源 {label} 必须是数组")
    records = [_provenance_record(item, label) for item in value]
    if len({record["path"] for record in records}) != len(records):
        raise _invalid(f"构建溯源 {label} 包含重复路径")
    return {record["path"]: record for record in records}


def _provenance_record(value: Any, label: str) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value) != {"path", "size_bytes", "sha256"}
        or not isinstance(value.get("path"), str)
        or not isinstance(value.get("size_bytes"), int)
        or value["size_bytes"] < 0
        or not isinstance(value.get("sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is None
    ):
        raise _invalid(f"构建溯源 {label} 记录无效")
    return value


def _is_schema_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and (not isinstance(value, float) or math.isfinite(value))
    )


def _matches_schema_type(value: Any, schema_type: str) -> bool:
    return (
        schema_type == "string"
        and isinstance(value, str)
        or schema_type == "integer"
        and isinstance(value, int)
        and not isinstance(value, bool)
        or schema_type == "number"
        and _is_schema_number(value)
        or schema_type == "boolean"
        and isinstance(value, bool)
    )


def _validate_command_property_schema(
    name: str,
    schema: dict[str, Any],
    *,
    requested_capabilities: set[str],
) -> None:
    if not 1 <= len(name) <= 128 or set(schema) - _COMMAND_SCHEMA_PROPERTY_FIELDS:
        raise _invalid("插件命令输入 Schema 包含不支持的字段或关键字")
    schema_type = schema.get("type")
    if schema_type not in _COMMAND_SCHEMA_TYPES:
        raise _invalid("插件命令输入 Schema 只支持基础字段类型")

    title = schema.get("title")
    if title is not None and (
        not isinstance(title, str) or not title.strip() or len(title) > 100
    ):
        raise _invalid("插件命令输入 Schema 字段标题无效")
    description = schema.get("description")
    if description is not None and (
        not isinstance(description, str) or len(description) > 500
    ):
        raise _invalid("插件命令输入 Schema 字段说明无效")

    enum_values = schema.get("enum")
    if enum_values is not None and (
            schema_type != "string"
            or not isinstance(enum_values, list)
            or not 1 <= len(enum_values) <= 100
            or any(not isinstance(value, str) for value in enum_values)
            or len({json.dumps(value, sort_keys=True) for value in enum_values})
            != len(enum_values)
    ):
        raise _invalid("插件命令枚举输入无效")

    format_value = schema.get("format")
    if format_value is not None:
        if schema_type != "string" or format_value not in {"file", "theme-background"}:
            raise _invalid("v1 命令输入格式无效")
        required_capability = (
            "ui:theme" if format_value == "theme-background" else "file:read:selected"
        )
        if required_capability not in requested_capabilities:
            raise _invalid(f"使用 {format_value} 输入的插件必须申请 {required_capability} 权限")

    default = schema.get("default", _MISSING)
    if default is not _MISSING and not _matches_schema_type(default, schema_type):
        raise _invalid("插件命令输入 Schema 默认值类型无效")
    if enum_values is not None and default is not _MISSING and default not in enum_values:
        raise _invalid("插件命令输入 Schema 默认值不在枚举范围内")

    string_constraints = {"minLength", "maxLength", "pattern"}
    numeric_constraints = {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    }
    if schema_type != "string" and set(schema) & string_constraints:
        raise _invalid("字符串约束只能用于 string 字段")
    if schema_type not in {"integer", "number"} and set(schema) & numeric_constraints:
        raise _invalid("数值约束只能用于 integer 或 number 字段")

    minimum_length = schema.get("minLength", 0)
    maximum_length = schema.get("maxLength")
    if (
        not isinstance(minimum_length, int)
        or isinstance(minimum_length, bool)
        or minimum_length < 0
        or maximum_length is not None
        and (
            not isinstance(maximum_length, int)
            or isinstance(maximum_length, bool)
            or maximum_length < minimum_length
        )
    ):
        raise _invalid("插件命令输入 Schema 字符串长度约束无效")
    pattern = schema.get("pattern")
    if pattern is not None and (not isinstance(pattern, str) or len(pattern) > 512):
        raise _invalid("插件命令输入 Schema 正则约束无效")

    if (
        "minimum" in schema
        and "exclusiveMinimum" in schema
        or "maximum" in schema
        and "exclusiveMaximum" in schema
    ):
        raise _invalid("插件命令输入 Schema 数值边界不能重复声明")
    numeric_values = [schema[key] for key in numeric_constraints if key in schema]
    if any(not _is_schema_number(value) for value in numeric_values):
        raise _invalid("插件命令输入 Schema 数值约束无效")
    if "multipleOf" in schema and schema["multipleOf"] <= 0:
        raise _invalid("插件命令输入 Schema multipleOf 必须大于零")
    lower = schema.get("exclusiveMinimum", schema.get("minimum"))
    upper = schema.get("exclusiveMaximum", schema.get("maximum"))
    if lower is not None and upper is not None and (
        lower > upper
        or lower == upper
        and ("exclusiveMinimum" in schema or "exclusiveMaximum" in schema)
    ):
        raise _invalid("插件命令输入 Schema 数值范围无效")


_MISSING = object()


def _validate_command_input_schema(
    schema: dict[str, Any], *, requested_capabilities: list[str]
) -> None:
    if set(schema) - _COMMAND_SCHEMA_ROOT_FIELDS or schema.get("type") != "object":
        raise _invalid("插件命令输入 Schema 仅支持根 object 和基础字段")
    properties = schema.get("properties")
    if not isinstance(properties, dict) or len(properties) > 32:
        raise _invalid("插件命令输入 Schema properties 无效")
    required = schema.get("required", [])
    if (
        not isinstance(required, list)
        or any(not isinstance(name, str) or name not in properties for name in required)
        or len(required) != len(set(required))
    ):
        raise _invalid("插件命令输入 Schema required 字段无效")
    additional = schema.get("additionalProperties", True)
    if not isinstance(additional, bool):
        raise _invalid("插件命令输入 Schema additionalProperties 必须是布尔值")
    requested = set(requested_capabilities)
    for name, property_schema in properties.items():
        if not isinstance(property_schema, dict):
            raise _invalid("插件命令输入 Schema 字段定义无效")
        _validate_command_property_schema(
            name,
            property_schema,
            requested_capabilities=requested,
        )
