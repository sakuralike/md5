import logging

import pytest

from password_detective.core.candidate_secrets import CandidateSecretVault
from password_detective.core.errors import AppError
from password_detective.core.logging import SensitiveDataFilter, redact_mapping
from password_detective.core.security import (
    create_access_token,
    decode_access_token,
    hash_account_password,
    hash_refresh_token,
    verify_account_password,
)


def test_password_hashing_and_token_claims():
    password = "SyntheticPass123!"
    password_hash = hash_account_password(password)
    assert password not in password_hash
    assert verify_account_password(password_hash, password)
    assert not verify_account_password(password_hash, "WrongSynthetic123!")

    token = create_access_token(
        secret_key="synthetic-secret-key-for-tests-only",
        ttl_minutes=15,
        user_id="user-id",
        role="user",
        session_family_id="family-id",
    )
    claims = decode_access_token(token, "synthetic-secret-key-for-tests-only")
    assert claims.user_id == "user-id"
    assert claims.session_family_id == "family-id"


def test_refresh_hash_is_deterministic_without_exposing_token():
    token = "rt_synthetic-token-value"
    digest = hash_refresh_token(token)
    assert digest == hash_refresh_token(token)
    assert token not in digest
    assert len(digest) == 64


def test_candidate_secret_vault_encrypts_and_uses_stable_keyed_dedup_tag():
    vault = CandidateSecretVault("synthetic-master-key-for-tests", key_version="v7")
    first = vault.encrypt("Unicode-合成密码-🔐")
    second = vault.encrypt("Unicode-合成密码-🔐")
    assert first.ciphertext != second.ciphertext
    assert first.nonce != second.nonce
    assert first.dedup_tag == second.dedup_tag
    assert "Unicode-合成密码" not in first.ciphertext
    assert (
        vault.decrypt(
            ciphertext=first.ciphertext,
            nonce=first.nonce,
            key_version=first.key_version,
        )
        == "Unicode-合成密码-🔐"
    )


def test_sensitive_log_fields_are_recursively_redacted():
    payload = redact_mapping(
        {
            "event": "submission",
            "password": "Synthetic-secret",
            "nested": {"access_token": "token", "safe": "visible"},
        }
    )
    assert payload == {
        "event": "submission",
        "password": "[REDACTED]",
        "nested": {"access_token": "[REDACTED]", "safe": "visible"},
    }
    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1, {"archive_password": "secret"}, (), None
    )
    assert SensitiveDataFilter().filter(record) is True
    assert record.msg == {"archive_password": "[REDACTED]"}


def test_candidate_secret_vault_reads_fallback_key_and_preserves_dedup_tag() -> None:
    legacy = CandidateSecretVault("legacy-key", key_version="v1", dedup_secret="stable-dedup")
    encrypted = legacy.encrypt("synthetic-password")
    current = CandidateSecretVault(
        "current-key",
        key_version="v2",
        decryption_secrets={"v1": "legacy-key"},
        dedup_secret="stable-dedup",
    )

    assert current.decrypt(
        ciphertext=encrypted.ciphertext,
        nonce=encrypted.nonce,
        key_version=encrypted.key_version,
    ) == "synthetic-password"
    assert current.dedup_tag("synthetic-password") == encrypted.dedup_tag
    assert current.encrypt("synthetic-password").key_version == "v2"


def test_candidate_secret_vault_rejects_unknown_key_version() -> None:
    vault = CandidateSecretVault("current-key", key_version="v2")

    with pytest.raises(AppError) as exc_info:
        vault.decrypt(ciphertext="bad", nonce="bad", key_version="v1")

    assert exc_info.value.code == "archive.secret_unavailable"
