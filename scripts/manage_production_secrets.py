from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

BUNDLE_SCHEMA = "password-detective-production-secrets-v1"
BACKUP_SCHEMA = "password-detective-encrypted-secret-backup-v1"
KEY_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
REQUIRED_FILES = (
    "app_secret_key",
    "candidate_secret_key_version",
    "candidate_secret_keyring",
    "candidate_secret_dedup_key",
    "direct_message_key_version",
    "direct_message_keyring",
    "mysql_password",
    "mysql_root_password",
    "redis_password",
    "database_url",
    "redis_url",
)
OPTIONAL_FILES = (
    "notification_webhook_secret",
    "notification_smtp_password",
    "desktop_plugin_s3_access_key_id",
    "desktop_plugin_s3_secret_access_key",
)
ALL_FILES = REQUIRED_FILES + OPTIONAL_FILES
MAX_FILE_BYTES = 64 * 1024


class SecretBundleError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _random_secret() -> str:
    return secrets.token_urlsafe(48)


def _write_private_file(path: Path, value: str, *, replace: bool = False) -> None:
    if path.exists() and not replace:
        raise SecretBundleError(f"目标文件已存在，拒绝覆盖: {path.name}")
    parent_existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt" and not parent_existed:
        path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8", newline="\n")
        if os.name != "nt":
            temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_text(path: Path, *, allow_empty: bool = False) -> str:
    if path.is_symlink() or not path.is_file():
        raise SecretBundleError(f"秘密项必须是普通文件且不能是符号链接: {path.name}")
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise SecretBundleError(f"秘密项超过 {MAX_FILE_BYTES} 字节限制: {path.name}")
    try:
        value = path.read_text(encoding="utf-8").rstrip("\r\n")
    except (OSError, UnicodeDecodeError) as exc:
        raise SecretBundleError(f"秘密项无法作为 UTF-8 文件读取: {path.name}") from exc
    if "\x00" in value:
        raise SecretBundleError(f"秘密项包含非法 NUL 字符: {path.name}")
    if not allow_empty and not value:
        raise SecretBundleError(f"秘密项不能为空: {path.name}")
    return value


def _assert_private_permissions(path: Path) -> None:
    if os.name == "nt":
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise SecretBundleError(f"权限过宽: {path.name} 应限制为 600 或更严格")


def build_initial_bundle(candidate_version: str = "v1") -> dict[str, str]:
    if not KEY_VERSION_PATTERN.fullmatch(candidate_version):
        raise SecretBundleError("候选秘密密钥版本格式无效")
    app_secret = _random_secret()
    candidate_secret = _random_secret()
    direct_message_secret = _random_secret()
    dedup_secret = _random_secret()
    mysql_password = _random_secret()
    mysql_root_password = _random_secret()
    redis_password = _random_secret()
    plugin_s3_access_key_id = "pdplugins" + secrets.token_hex(4)
    plugin_s3_secret_access_key = _random_secret()
    return {
        "app_secret_key": app_secret,
        "candidate_secret_key_version": candidate_version,
        "candidate_secret_keyring": json.dumps(
            {candidate_version: candidate_secret}, ensure_ascii=False, separators=(",", ":")
        ),
        "candidate_secret_dedup_key": dedup_secret,
        "direct_message_key_version": candidate_version,
        "direct_message_keyring": json.dumps(
            {candidate_version: direct_message_secret}, ensure_ascii=False, separators=(",", ":")
        ),
        "mysql_password": mysql_password,
        "mysql_root_password": mysql_root_password,
        "redis_password": redis_password,
        "database_url": (
            "mysql+pymysql://password_detective:"
            f"{quote(mysql_password, safe='')}@mysql:3306/password_detective"
        ),
        "redis_url": f"redis://:{quote(redis_password, safe='')}@redis:6379/0",
        "notification_webhook_secret": "",
        "notification_smtp_password": "",
        "desktop_plugin_s3_access_key_id": plugin_s3_access_key_id,
        "desktop_plugin_s3_secret_access_key": plugin_s3_secret_access_key,
    }


def initialize_bundle(directory: Path, candidate_version: str = "v1") -> dict[str, object]:
    if directory.exists() and not directory.is_dir():
        raise SecretBundleError("秘密目录路径已存在但不是目录")
    existing = [name for name in ALL_FILES if (directory / name).exists()]
    if existing:
        raise SecretBundleError("秘密目录已包含受管文件，拒绝覆盖")
    directory.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        directory.chmod(0o700)
    values = build_initial_bundle(candidate_version)
    for name in ALL_FILES:
        _write_private_file(directory / name, values[name])
    verify_bundle(directory)
    return {
        "schema": BUNDLE_SCHEMA,
        "status": "initialized",
        "directory": str(directory.resolve()),
        "candidate_secret_key_version": candidate_version,
        "direct_message_key_version": candidate_version,
        "managed_file_count": len(ALL_FILES),
    }


def verify_bundle(directory: Path) -> dict[str, object]:
    if directory.is_symlink() or not directory.is_dir():
        raise SecretBundleError("秘密目录不存在、不是目录或为符号链接")
    _assert_private_permissions(directory)
    values: dict[str, str] = {}
    for name in ALL_FILES:
        path = directory / name
        if not path.exists():
            if name in OPTIONAL_FILES:
                continue
            raise SecretBundleError(f"缺少必需秘密项: {name}")
        _assert_private_permissions(path)
        values[name] = _read_text(path, allow_empty=name in OPTIONAL_FILES)

    version = values["candidate_secret_key_version"]
    if not KEY_VERSION_PATTERN.fullmatch(version):
        raise SecretBundleError("candidate_secret_key_version 格式无效")
    try:
        keyring = json.loads(values["candidate_secret_keyring"])
    except json.JSONDecodeError as exc:
        raise SecretBundleError("candidate_secret_keyring 不是有效 JSON") from exc
    if not isinstance(keyring, dict) or not keyring or len(keyring) > 8:
        raise SecretBundleError("candidate_secret_keyring 必须包含 1 到 8 个版本")
    if version not in keyring:
        raise SecretBundleError("当前候选秘密密钥版本不在密钥环中")
    for key, value in keyring.items():
        if not isinstance(key, str) or not KEY_VERSION_PATTERN.fullmatch(key):
            raise SecretBundleError("candidate_secret_keyring 包含无效版本")
        if not isinstance(value, str) or len(value) < 32:
            raise SecretBundleError("candidate_secret_keyring 的每个密钥至少需要 32 个字符")

    direct_message_version = values["direct_message_key_version"]
    if not KEY_VERSION_PATTERN.fullmatch(direct_message_version):
        raise SecretBundleError("direct_message_key_version 格式无效")
    try:
        direct_message_keyring = json.loads(values["direct_message_keyring"])
    except json.JSONDecodeError as exc:
        raise SecretBundleError("direct_message_keyring 不是有效 JSON") from exc
    if not isinstance(direct_message_keyring, dict) or not direct_message_keyring or len(direct_message_keyring) > 8:
        raise SecretBundleError("direct_message_keyring 必须包含 1 到 8 个版本")
    if direct_message_version not in direct_message_keyring:
        raise SecretBundleError("当前私信密钥版本不在密钥环中")
    for key, value in direct_message_keyring.items():
        if not isinstance(key, str) or not KEY_VERSION_PATTERN.fullmatch(key):
            raise SecretBundleError("direct_message_keyring 包含无效版本")
        if not isinstance(value, str) or len(value) < 32:
            raise SecretBundleError("direct_message_keyring 的每个密钥至少需要 32 个字符")
    if set(direct_message_keyring.values()) & set(keyring.values()):
        raise SecretBundleError("私信密钥环必须独立于候选秘密密钥环")
    if values["app_secret_key"] in direct_message_keyring.values():
        raise SecretBundleError("私信密钥不得复用应用主秘密")

    for name in ("app_secret_key", "candidate_secret_dedup_key", "mysql_password", "mysql_root_password", "redis_password"):
        if len(values[name]) < 32:
            raise SecretBundleError(f"秘密项长度不足: {name}")
    forbidden_markers = ("change_me", "replace-with", "password_detective_local", "root_local")
    for name, value in values.items():
        if any(marker in value.lower() for marker in forbidden_markers):
            raise SecretBundleError(f"秘密项仍包含开发占位值: {name}")
    if quote(values["mysql_password"], safe="") not in values["database_url"]:
        raise SecretBundleError("database_url 与 mysql_password 不一致")
    if quote(values["redis_password"], safe="") not in values["redis_url"]:
        raise SecretBundleError("redis_url 与 redis_password 不一致")

    return {
        "schema": BUNDLE_SCHEMA,
        "status": "valid",
        "directory": str(directory.resolve()),
        "candidate_secret_key_version": version,
        "candidate_secret_key_versions": sorted(keyring),
        "direct_message_key_version": direct_message_version,
        "direct_message_key_versions": sorted(direct_message_keyring),
        "managed_file_count": len(values),
    }


def _read_passphrase(path: Path) -> bytes:
    _assert_private_permissions(path)
    value = _read_text(path)
    if len(value) < 16:
        raise SecretBundleError("备份口令至少需要 16 个字符")
    return value.encode("utf-8")


def _derive_fernet_key(passphrase: bytes, salt: bytes) -> bytes:
    derived = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase)
    return base64.urlsafe_b64encode(derived)


def create_encrypted_backup(directory: Path, output: Path, passphrase_file: Path) -> dict[str, object]:
    verification = verify_bundle(directory)
    passphrase = _read_passphrase(passphrase_file)
    files = {
        name: _read_text(directory / name, allow_empty=name in OPTIONAL_FILES)
        for name in ALL_FILES
        if (directory / name).exists()
    }
    payload = json.dumps(
        {
            "schema": BUNDLE_SCHEMA,
            "created_at": utc_now(),
            "files": files,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    salt = os.urandom(16)
    token = Fernet(_derive_fernet_key(passphrase, salt)).encrypt(payload).decode("ascii")
    envelope = json.dumps(
        {
            "schema": BACKUP_SCHEMA,
            "kdf": {"name": "scrypt", "n": 2**15, "r": 8, "p": 1},
            "salt": base64.b64encode(salt).decode("ascii"),
            "ciphertext": token,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    _write_private_file(output, envelope)
    return {
        "schema": BACKUP_SCHEMA,
        "status": "created",
        "output": str(output.resolve()),
        "candidate_secret_key_version": verification["candidate_secret_key_version"],
        "encrypted_file_count": len(files),
    }


def _decrypt_backup(input_path: Path, passphrase_file: Path) -> dict[str, str]:
    try:
        envelope = json.loads(_read_text(input_path))
        if envelope.get("schema") != BACKUP_SCHEMA:
            raise SecretBundleError("备份格式版本不受支持")
        salt = base64.b64decode(envelope["salt"], validate=True)
        token = envelope["ciphertext"].encode("ascii")
    except (KeyError, TypeError, ValueError, UnicodeEncodeError, json.JSONDecodeError) as exc:
        raise SecretBundleError("加密备份文件格式无效") from exc
    try:
        plaintext = Fernet(
            _derive_fernet_key(_read_passphrase(passphrase_file), salt)
        ).decrypt(token)
    except InvalidToken as exc:
        raise SecretBundleError("备份口令错误或备份完整性校验失败") from exc
    try:
        payload = json.loads(plaintext)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SecretBundleError("备份解密后的内容无效") from exc
    if payload.get("schema") != BUNDLE_SCHEMA or not isinstance(payload.get("files"), dict):
        raise SecretBundleError("备份内容格式版本不受支持")
    files = payload["files"]
    if any(name not in ALL_FILES or not isinstance(value, str) for name, value in files.items()):
        raise SecretBundleError("备份包含未知或非法秘密项")
    if any(name not in files for name in REQUIRED_FILES):
        raise SecretBundleError("备份缺少必需秘密项")
    return files


def restore_encrypted_backup(
    input_path: Path, directory: Path, passphrase_file: Path, *, replace: bool = False
) -> dict[str, object]:
    files = _decrypt_backup(input_path, passphrase_file)
    directory.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        directory.chmod(0o700)
    existing = [name for name in files if (directory / name).exists()]
    if existing and not replace:
        raise SecretBundleError("恢复目录已包含受管文件，拒绝覆盖")
    for name, value in files.items():
        _write_private_file(directory / name, value, replace=replace)
    verification = verify_bundle(directory)
    return {
        "schema": BUNDLE_SCHEMA,
        "status": "restored",
        "directory": str(directory.resolve()),
        "candidate_secret_key_version": verification["candidate_secret_key_version"],
        "restored_file_count": len(files),
    }


def rotate_candidate_key(
    directory: Path,
    new_version: str,
    backup_output: Path,
    passphrase_file: Path,
) -> dict[str, object]:
    verification = verify_bundle(directory)
    if not KEY_VERSION_PATTERN.fullmatch(new_version):
        raise SecretBundleError("新密钥版本格式无效")
    keyring_path = directory / "candidate_secret_keyring"
    version_path = directory / "candidate_secret_key_version"
    keyring = json.loads(_read_text(keyring_path))
    if new_version in keyring:
        raise SecretBundleError("新密钥版本已存在")
    if len(keyring) >= 8:
        raise SecretBundleError("密钥环已达到 8 个版本上限")
    backup = create_encrypted_backup(directory, backup_output, passphrase_file)
    previous_version = str(verification["candidate_secret_key_version"])
    keyring[new_version] = _random_secret()
    _write_private_file(
        keyring_path,
        json.dumps(keyring, ensure_ascii=False, separators=(",", ":")),
        replace=True,
    )
    _write_private_file(version_path, new_version, replace=True)
    verify_bundle(directory)
    return {
        "schema": BUNDLE_SCHEMA,
        "status": "candidate-key-staged",
        "previous_version": previous_version,
        "active_version": new_version,
        "retained_versions": sorted(keyring),
        "encrypted_backup": backup["output"],
        "next_action": "restart services, run candidate secret rotation dry-run, then execute rotation",
    }


def _path(value: str) -> Path:
    return Path(value).expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="密码侦探社生产秘密文件管理工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize = subparsers.add_parser("init", help="生成新的生产秘密目录")
    initialize.add_argument("--directory", type=_path, required=True)
    initialize.add_argument("--candidate-version", default="v1")

    verify = subparsers.add_parser("verify", help="检查秘密完整性和权限")
    verify.add_argument("--directory", type=_path, required=True)

    backup = subparsers.add_parser("backup", help="创建口令保护的加密备份")
    backup.add_argument("--directory", type=_path, required=True)
    backup.add_argument("--output", type=_path, required=True)
    backup.add_argument("--passphrase-file", type=_path, required=True)

    restore = subparsers.add_parser("restore", help="恢复加密备份")
    restore.add_argument("--input", type=_path, required=True)
    restore.add_argument("--directory", type=_path, required=True)
    restore.add_argument("--passphrase-file", type=_path, required=True)
    restore.add_argument("--replace", action="store_true")

    rotate = subparsers.add_parser("rotate-candidate", help="备份后新增候选秘密密钥版本")
    rotate.add_argument("--directory", type=_path, required=True)
    rotate.add_argument("--new-version", required=True)
    rotate.add_argument("--backup-output", type=_path, required=True)
    rotate.add_argument("--passphrase-file", type=_path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            report = initialize_bundle(args.directory, args.candidate_version)
        elif args.command == "verify":
            report = verify_bundle(args.directory)
        elif args.command == "backup":
            report = create_encrypted_backup(args.directory, args.output, args.passphrase_file)
        elif args.command == "restore":
            report = restore_encrypted_backup(
                args.input, args.directory, args.passphrase_file, replace=args.replace
            )
        else:
            report = rotate_candidate_key(
                args.directory, args.new_version, args.backup_output, args.passphrase_file
            )
    except SecretBundleError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
