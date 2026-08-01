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
