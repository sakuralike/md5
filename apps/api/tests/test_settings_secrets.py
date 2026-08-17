from __future__ import annotations

import pytest

from password_detective.core.errors import AppError
from password_detective.core.settings_secrets import SettingsSecretVault


def test_settings_secret_vault_round_trips_with_a_fresh_nonce() -> None:
    vault = SettingsSecretVault(
        "synthetic-settings-master-secret",
        key_version="v1",
    )

    first = vault.encrypt("synthetic-smtp-app-password")
    second = vault.encrypt("synthetic-smtp-app-password")

    assert first.nonce != second.nonce
    assert first.key_version == "v1"
    assert vault.decrypt(first) == "synthetic-smtp-app-password"
    assert vault.decrypt(second) == "synthetic-smtp-app-password"


def test_settings_secret_vault_rejects_tampering_without_exposing_secret() -> None:
    vault = SettingsSecretVault("synthetic-settings-master-secret", key_version="v1")
    encrypted = vault.encrypt("synthetic-smtp-app-password")
    tampered = encrypted.__class__(
        ciphertext=encrypted.ciphertext[:-2] + "xx",
        nonce=encrypted.nonce,
        key_version=encrypted.key_version,
    )

    with pytest.raises(AppError) as error:
        vault.decrypt(tampered)

    assert error.value.code == "admin.email_delivery_secret_unavailable"
    assert "synthetic-smtp-app-password" not in str(error.value)


def test_settings_secret_vault_binds_ciphertext_to_key_version() -> None:
    vault = SettingsSecretVault(
        "synthetic-settings-master-secret",
        key_version="v2",
        decryption_secrets={"v1": "synthetic-legacy-master-secret"},
    )
    encrypted = vault.encrypt("synthetic-smtp-app-password")
    wrong_version = encrypted.__class__(
        ciphertext=encrypted.ciphertext,
        nonce=encrypted.nonce,
        key_version="v1",
    )

    with pytest.raises(AppError, match="暂时无法读取"):
        vault.decrypt(wrong_version)
