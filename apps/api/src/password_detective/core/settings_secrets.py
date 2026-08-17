from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from password_detective.core.errors import AppError

_KEY_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
_PURPOSE = b"password-detective:smtp-email-delivery:v1"


@dataclass(frozen=True)
class EncryptedSettingsSecret:
    ciphertext: str
    nonce: str
    key_version: str


class SettingsSecretVault:
    """Encrypt persisted system-setting secrets with versioned AES-GCM keys."""

    def __init__(
        self,
        master_secret: str,
        *,
        key_version: str,
        decryption_secrets: Mapping[str, str] | None = None,
    ) -> None:
        _validate_key_version(key_version)
        secrets = dict(decryption_secrets or {})
        secrets[key_version] = master_secret
        if not master_secret or any(not value for value in secrets.values()):
            raise ValueError("settings secret master keys are required")
        for version in secrets:
            _validate_key_version(version)
        self._master_secrets = {
            version: value.encode("utf-8") for version, value in secrets.items()
        }
        self.key_version = key_version

    def encrypt(self, secret: str) -> EncryptedSettingsSecret:
        raw = _validate_secret(secret)
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._encryption_key(self.key_version)).encrypt(
            nonce,
            raw,
            _associated_data(self.key_version),
        )
        return EncryptedSettingsSecret(
            ciphertext=_b64encode(ciphertext),
            nonce=_b64encode(nonce),
            key_version=self.key_version,
        )

    def decrypt(self, encrypted: EncryptedSettingsSecret) -> str:
        try:
            plaintext = AESGCM(self._encryption_key(encrypted.key_version)).decrypt(
                _b64decode(encrypted.nonce),
                _b64decode(encrypted.ciphertext),
                _associated_data(encrypted.key_version),
            )
            return plaintext.decode("utf-8")
        except (binascii.Error, InvalidTag, KeyError, UnicodeDecodeError, ValueError) as exc:
            raise AppError(
                "admin.email_delivery_secret_unavailable",
                "SMTP 授权码暂时无法读取",
                status_code=500,
            ) from exc

    def _encryption_key(self, key_version: str) -> bytes:
        _validate_key_version(key_version)
        return hmac.new(
            self._master_secrets[key_version],
            b"password-detective:settings-encryption:" + key_version.encode("utf-8"),
            hashlib.sha256,
        ).digest()


class SettingsSecretConfig(Protocol):
    candidate_secret_key_version: str
    candidate_secret_key_map: Mapping[str, str]
    app_secret_key: str


def build_settings_secret_vault(settings: SettingsSecretConfig) -> SettingsSecretVault:
    key_version = str(settings.candidate_secret_key_version)
    keyring = settings.candidate_secret_key_map
    app_secret = str(settings.app_secret_key)
    active_secret = keyring.get(key_version, app_secret)
    return SettingsSecretVault(
        active_secret,
        key_version=key_version,
        decryption_secrets=keyring,
    )


def _associated_data(key_version: str) -> bytes:
    return _PURPOSE + b":" + key_version.encode("utf-8")


def _validate_key_version(key_version: str) -> None:
    if not _KEY_VERSION_PATTERN.fullmatch(key_version):
        raise ValueError("settings secret key version is invalid")


def _validate_secret(secret: str) -> bytes:
    if not secret:
        raise AppError(
            "admin.email_delivery_password_required",
            "SMTP 授权码不能为空",
            status_code=422,
        )
    raw = secret.encode("utf-8")
    if len(raw) > 1024:
        raise AppError(
            "admin.email_delivery_password_too_long",
            "SMTP 授权码长度超过安全限制",
            status_code=422,
        )
    return raw


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))
