from __future__ import annotations

import pytest
from pydantic import ValidationError

from password_detective.core.candidate_secrets import CandidateSecretVault
from password_detective.core.config import Settings
from password_detective.core.direct_message_crypto import (
    DirectMessageVault,
    build_direct_message_vault,
)
from password_detective.core.errors import AppError


def _settings(tmp_path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "app_secret_key": "synthetic-app-secret-key-for-tests",
        "database_url": f"sqlite:///{(tmp_path / 'direct-message-crypto.db').as_posix()}",
        "desktop_update_storage_path": str(tmp_path / "desktop-updates"),
        "direct_message_key_version": "v2",
        "direct_message_keyring": (
            '{"v1":"synthetic-direct-message-legacy-key",'
            '"v2":"synthetic-direct-message-current-key"}'
        ),
    }
    values.update(overrides)
    return Settings(**values)


def test_direct_message_vault_round_trips_only_in_its_own_crypto_domain() -> None:
    vault = DirectMessageVault(
        "synthetic-direct-message-current-key",
        key_version="v2",
        decryption_secrets={"v1": "synthetic-direct-message-legacy-key"},
    )

    encrypted = vault.encrypt("仅用于私信加密域的合成正文")

    assert encrypted.key_version == "v2"
    assert vault.decrypt(
        ciphertext=encrypted.ciphertext,
        nonce=encrypted.nonce,
        key_version=encrypted.key_version,
    ) == "仅用于私信加密域的合成正文"

    candidate_vault = CandidateSecretVault(
        "synthetic-direct-message-current-key", key_version="v2"
    )
    with pytest.raises(AppError, match="候选密码暂时无法读取"):
        candidate_vault.decrypt(
            ciphertext=encrypted.ciphertext,
            nonce=encrypted.nonce,
            key_version=encrypted.key_version,
        )


def test_direct_message_vault_rejects_empty_or_oversized_plaintext() -> None:
    vault = DirectMessageVault("synthetic-direct-message-current-key")

    with pytest.raises(AppError) as empty:
        vault.encrypt("")
    assert empty.value.code == "community.direct_message_empty"
    assert empty.value.status_code == 422

    with pytest.raises(AppError) as oversized:
        vault.encrypt("界" * 1_334)
    assert oversized.value.code == "community.direct_message_too_long"
    assert oversized.value.status_code == 422


def test_direct_message_vault_hides_decrypt_failures() -> None:
    vault = DirectMessageVault("synthetic-direct-message-current-key")
    encrypted = vault.encrypt("合成正文")

    with pytest.raises(AppError) as unavailable:
        vault.decrypt(
            ciphertext=encrypted.ciphertext[:-2] + "AA",
            nonce=encrypted.nonce,
            key_version=encrypted.key_version,
        )

    assert unavailable.value.code == "community.direct_message_unavailable"
    assert unavailable.value.status_code == 500


def test_direct_message_keyring_is_independent_and_builds_vault(tmp_path) -> None:
    settings = _settings(tmp_path)

    assert settings.direct_message_key_map == {
        "v1": "synthetic-direct-message-legacy-key",
        "v2": "synthetic-direct-message-current-key",
    }
    assert "synthetic-direct-message-current-key" not in repr(settings)

    vault = build_direct_message_vault(settings)
    assert vault.key_version == "v2"
    assert vault.available_key_versions == ("v1", "v2")


def test_direct_message_keyring_rejects_duplicate_versions(tmp_path) -> None:
    with pytest.raises(ValidationError, match="无重复键"):
        _settings(
            tmp_path,
            direct_message_keyring='{"v2":"first","v2":"second"}',
        )


def test_direct_message_keyring_rejects_missing_active_version(tmp_path) -> None:
    with pytest.raises(ValidationError, match="必须包含当前密钥版本"):
        _settings(
            tmp_path,
            direct_message_keyring='{"v1":"synthetic-direct-message-legacy-key"}',
        )


def test_production_direct_message_keyring_requires_long_secrets(tmp_path) -> None:
    with pytest.raises(ValidationError, match="至少需要 32 个字符"):
        _settings(
            tmp_path,
            app_env="production",
            app_secret_key="a" * 32,
            browser_cookie_secure=True,
            direct_message_keyring='{"v2":"too-short"}',
        )
