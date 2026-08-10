from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from password_detective.core.errors import AppError

if TYPE_CHECKING:
    from password_detective.core.config import Settings

_KEY_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,32}$")


@dataclass(frozen=True)
class EncryptedCandidateSecret:
    ciphertext: str
    nonce: str
    key_version: str
    dedup_tag: str


class CandidateSecretVault:
    """Encrypt candidate secrets with an active key and versioned read fallbacks."""

    def __init__(
        self,
        master_secret: str,
        *,
        key_version: str = "v1",
        decryption_secrets: Mapping[str, str] | None = None,
        dedup_secret: str | None = None,
    ) -> None:
        _validate_key_version(key_version)
        secrets = dict(decryption_secrets or {})
        secrets[key_version] = master_secret
        if not master_secret or any(not secret for secret in secrets.values()):
            raise ValueError("candidate secret master keys are required")
        for version in secrets:
            _validate_key_version(version)
        self._master_secrets = {
            version: secret.encode("utf-8") for version, secret in secrets.items()
        }
        self._dedup_secret = (dedup_secret or master_secret).encode("utf-8")
        self.key_version = key_version

    @property
    def available_key_versions(self) -> tuple[str, ...]:
        return tuple(sorted(self._master_secrets))

    def encrypt(self, secret: str) -> EncryptedCandidateSecret:
        raw = _validate_secret(secret)
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._encryption_key(self.key_version)).encrypt(
            nonce,
            raw,
            self.key_version.encode("utf-8"),
        )
        return EncryptedCandidateSecret(
            ciphertext=_b64encode(ciphertext),
            nonce=_b64encode(nonce),
            key_version=self.key_version,
            dedup_tag=self.dedup_tag(secret),
        )

    def decrypt(self, *, ciphertext: str, nonce: str, key_version: str) -> str:
        try:
            plaintext = AESGCM(self._encryption_key(key_version)).decrypt(
                _b64decode(nonce),
                _b64decode(ciphertext),
                key_version.encode("utf-8"),
            )
            return plaintext.decode("utf-8")
        except (binascii.Error, InvalidTag, KeyError, ValueError, UnicodeDecodeError) as exc:
            raise AppError(
                "archive.secret_unavailable",
                "候选密码暂时无法读取",
                status_code=500,
            ) from exc

    def dedup_tag(self, secret: str) -> str:
        raw = _validate_secret(secret)
        return hmac.new(self._dedup_key(), raw, hashlib.sha256).hexdigest()

    def _encryption_key(self, key_version: str) -> bytes:
        _validate_key_version(key_version)
        master_secret = self._master_secrets[key_version]
        return hmac.new(
            master_secret,
            b"password-detective:candidate-encryption:" + key_version.encode("utf-8"),
            hashlib.sha256,
        ).digest()

    def _dedup_key(self) -> bytes:
        return hmac.new(
            self._dedup_secret,
            b"password-detective:candidate-dedup:v1",
            hashlib.sha256,
        ).digest()


def build_candidate_secret_vault(settings: Settings) -> CandidateSecretVault:
    keyring = settings.candidate_secret_key_map
    active_secret = keyring.get(settings.candidate_secret_key_version, settings.app_secret_key)
    dedup_secret = settings.candidate_secret_dedup_key.get_secret_value() or settings.app_secret_key
    return CandidateSecretVault(
        active_secret,
        key_version=settings.candidate_secret_key_version,
        decryption_secrets=keyring,
        dedup_secret=dedup_secret,
    )


def _validate_key_version(key_version: str) -> None:
    if not _KEY_VERSION_PATTERN.fullmatch(key_version):
        raise ValueError("candidate secret key version is invalid")


def _validate_secret(secret: str) -> bytes:
    if not secret:
        raise AppError("archive.empty_secret", "解压密码不能为空", status_code=422)
    raw = secret.encode("utf-8")
    if len(raw) > 1024:
        raise AppError("archive.secret_too_long", "解压密码长度超过安全限制", status_code=422)
    return raw


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))
