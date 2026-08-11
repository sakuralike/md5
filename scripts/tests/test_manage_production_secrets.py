from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from manage_production_secrets import (
    SecretBundleError,
    create_encrypted_backup,
    initialize_bundle,
    restore_encrypted_backup,
    rotate_candidate_key,
    verify_bundle,
)


def _passphrase_file(tmp_path: Path, value: str = "synthetic-backup-passphrase-2026") -> Path:
    path = tmp_path / "offline-backup-passphrase"
    path.write_text(value, encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
    return path


def test_initialize_and_verify_production_secret_bundle(tmp_path: Path) -> None:
    directory = tmp_path / "secrets"

    initialized = initialize_bundle(directory)
    verified = verify_bundle(directory)

    assert initialized["status"] == "initialized"
    assert verified["status"] == "valid"
    assert verified["candidate_secret_key_version"] == "v1"
    assert verified["candidate_secret_key_versions"] == ["v1"]
    assert "password_detective_local" not in (directory / "database_url").read_text(
        encoding="utf-8"
    )
    if os.name != "nt":
        assert directory.stat().st_mode & 0o077 == 0
        assert all((directory / name).stat().st_mode & 0o077 == 0 for name in os.listdir(directory))


def test_encrypted_backup_does_not_expose_plaintext_and_restores(tmp_path: Path) -> None:
    directory = tmp_path / "secrets"
    initialize_bundle(directory)
    passphrase = _passphrase_file(tmp_path)
    backup = tmp_path / "backup.pdsb"
    app_secret = (directory / "app_secret_key").read_text(encoding="utf-8")

    report = create_encrypted_backup(directory, backup, passphrase)
    restored = tmp_path / "restored"
    restore_report = restore_encrypted_backup(backup, restored, passphrase)

    assert report["status"] == "created"
    assert restore_report["status"] == "restored"
    assert app_secret not in backup.read_text(encoding="utf-8")
    for source in directory.iterdir():
        assert (restored / source.name).read_bytes() == source.read_bytes()


def test_wrong_backup_passphrase_fails_integrity_check(tmp_path: Path) -> None:
    directory = tmp_path / "secrets"
    initialize_bundle(directory)
    passphrase = _passphrase_file(tmp_path)
    backup = tmp_path / "backup.pdsb"
    create_encrypted_backup(directory, backup, passphrase)
    wrong_passphrase = _passphrase_file(tmp_path, "different-synthetic-passphrase-2026")

    with pytest.raises(SecretBundleError, match="口令错误或备份完整性校验失败"):
        restore_encrypted_backup(backup, tmp_path / "restored", wrong_passphrase)


def test_candidate_rotation_keeps_old_key_and_creates_prechange_backup(tmp_path: Path) -> None:
    directory = tmp_path / "secrets"
    initialize_bundle(directory)
    passphrase = _passphrase_file(tmp_path)
    backup = tmp_path / "before-v2.pdsb"
    old_keyring = json.loads((directory / "candidate_secret_keyring").read_text(encoding="utf-8"))

    report = rotate_candidate_key(directory, "v2", backup, passphrase)
    new_keyring = json.loads((directory / "candidate_secret_keyring").read_text(encoding="utf-8"))
    restored = tmp_path / "restored-v1"
    restore_encrypted_backup(backup, restored, passphrase)

    assert report["status"] == "candidate-key-staged"
    assert report["previous_version"] == "v1"
    assert report["active_version"] == "v2"
    assert new_keyring["v1"] == old_keyring["v1"]
    assert len(new_keyring["v2"]) >= 32
    assert (restored / "candidate_secret_key_version").read_text(encoding="utf-8") == "v1"


def test_existing_bundle_is_never_overwritten_by_init(tmp_path: Path) -> None:
    directory = tmp_path / "secrets"
    initialize_bundle(directory)

    with pytest.raises(SecretBundleError, match="拒绝覆盖"):
        initialize_bundle(directory)
