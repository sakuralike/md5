from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from password_detective.core.errors import AppError


@dataclass(frozen=True)
class EncryptedCandidateSecret:
    ciphertext: str
    nonce: str
    key_version: str
    dedup_tag: str


class CandidateSecretVault:
    """Encrypt archive passwords and derive a separate keyed deduplication tag."""

    def __init__(self, master_secret: str, *, key_version: str = "v1") -> None:
        if not master_secret:
            raise ValueError("candidate secret master key is required")
        if not key_version or len(key_version) > 32:
            raise ValueError("candidate secret key version is invalid")
        self._master_secret = master_secret.encode("utf-8")
        self.key_version = key_version

    def encrypt(self, secret: str) -> EncryptedCandidateSecret:
        raw = _validate_secret(secret)
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._encryption_key()).encrypt(
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
        except (binascii.Error, InvalidTag, ValueError, UnicodeDecodeError) as exc:
            raise AppError(
                "archive.secret_unavailable",
                "候选密码暂时无法读取",
                status_code=500,
            ) from exc

    def dedup_tag(self, secret: str) -> str:
        raw = _validate_secret(secret)
        return hmac.new(self._dedup_key(), raw, hashlib.sha256).hexdigest()

    def _encryption_key(self, key_version: str | None = None) -> bytes:
        version = (key_version or self.key_version).encode("utf-8")
        return hmac.new(
            self._master_secret,
            b"password-detective:candidate-encryption:" + version,
            hashlib.sha256,
        ).digest()

    def _dedup_key(self) -> bytes:
        return hmac.new(
            self._master_secret,
            b"password-detective:candidate-dedup:v1",
            hashlib.sha256,
        ).digest()


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
