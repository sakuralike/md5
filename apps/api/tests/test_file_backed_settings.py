from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from password_detective.core.config import Settings


def _write(path: Path, value: str) -> Path:
    path.write_text(value, encoding="utf-8")
    return path


def test_settings_load_supported_values_from_secret_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_secret = _write(tmp_path / "app_secret_key", "a" * 48 + "\n")
    keyring = _write(tmp_path / "candidate_secret_keyring", '{"v1":"' + "b" * 48 + '"}\n')
    dedup = _write(tmp_path / "candidate_secret_dedup_key", "c" * 48 + "\r\n")

    monkeypatch.setenv("APP_SECRET_KEY_FILE", str(app_secret))
    monkeypatch.setenv("CANDIDATE_SECRET_KEYRING_FILE", str(keyring))
    monkeypatch.setenv("CANDIDATE_SECRET_DEDUP_KEY_FILE", str(dedup))

    settings = Settings(app_env="production", browser_cookie_secure=True)

    assert settings.app_secret_key == "a" * 48
    assert settings.candidate_secret_key_map == {"v1": "b" * 48}
    assert settings.candidate_secret_dedup_key.get_secret_value() == "c" * 48


def test_direct_secret_and_file_reference_are_mutually_exclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_path = _write(tmp_path / "app_secret_key", "f" * 48)
    monkeypatch.setenv("APP_SECRET_KEY", "d" * 48)
    monkeypatch.setenv("APP_SECRET_KEY_FILE", str(secret_path))

    with pytest.raises(ValidationError, match="不能同时配置"):
        Settings()


def test_missing_secret_file_fails_without_echoing_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "do-not-disclose-secret-name"
    monkeypatch.setenv("APP_SECRET_KEY_FILE", str(missing))

    with pytest.raises(ValidationError) as error:
        Settings()

    message = str(error.value)
    assert "秘密文件不可读取" in message
    assert str(missing) not in message


def test_secret_file_size_limit_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    oversized = _write(tmp_path / "candidate_secret_keyring", "x" * (64 * 1024 + 1))
    monkeypatch.setenv("CANDIDATE_SECRET_KEYRING_FILE", str(oversized))

    with pytest.raises(ValidationError, match="超过允许的大小限制"):
        Settings()
