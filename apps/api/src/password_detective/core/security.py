from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now

_password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


@dataclass(frozen=True)
class AccessClaims:
    user_id: str
    role: str
    session_family_id: str
    mfa_verified: bool


@dataclass(frozen=True)
class ThirdPartyAccessClaims:
    user_id: str
    app_id: str
    client_id: str
    token_session_id: str
    token_family_id: str
    scopes: tuple[str, ...]


def hash_account_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_account_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_password_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def create_refresh_token() -> str:
    return "rt_" + secrets.token_urlsafe(48)


def create_account_token() -> str:
    return "at_" + secrets.token_urlsafe(32)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_refresh_token(token: str) -> str:
    return hash_opaque_token(token)


def encrypt_secret(secret: str, app_secret_key: str) -> str:
    key = base64.urlsafe_b64encode(
        hashlib.sha256(f"password-detective:totp:{app_secret_key}".encode()).digest()
    )
    return Fernet(key).encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str, app_secret_key: str) -> str:
    key = base64.urlsafe_b64encode(
        hashlib.sha256(f"password-detective:totp:{app_secret_key}".encode()).digest()
    )
    try:
        return Fernet(key).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise AppError("auth.secret_unavailable", "安全凭据无法读取", status_code=500) from exc


def create_access_token(
    *,
    secret_key: str,
    ttl_minutes: int,
    user_id: str,
    role: str,
    session_family_id: str,
    mfa_verified: bool = False,
) -> str:
    now = utc_now()
    payload = {
        "sub": user_id,
        "role": role,
        "sid": session_family_id,
        "mfa": mfa_verified,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def create_third_party_access_token(
    *,
    secret_key: str,
    ttl_minutes: int,
    user_id: str,
    app_id: str,
    client_id: str,
    token_session_id: str,
    token_family_id: str,
    scopes: tuple[str, ...],
) -> str:
    now = utc_now()
    payload = {
        "sub": user_id,
        "app_id": app_id,
        "client_id": client_id,
        "sid": token_session_id,
        "fid": token_family_id,
        "scope": list(scopes),
        "aud": "third-party-desktop",
        "typ": "third_party_access",
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def decode_third_party_access_token(token: str, secret_key: str) -> ThirdPartyAccessClaims:
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=["HS256"],
            audience="third-party-desktop",
            options={
                "require": [
                    "sub",
                    "app_id",
                    "client_id",
                    "sid",
                    "fid",
                    "scope",
                    "aud",
                    "typ",
                    "iat",
                    "exp",
                    "jti",
                ]
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError(
            "third_party_oauth.access_token_expired", "第三方访问令牌已过期", status_code=401
        ) from exc
    except jwt.PyJWTError as exc:
        raise AppError(
            "third_party_oauth.invalid_access_token", "第三方访问令牌无效", status_code=401
        ) from exc
    if payload.get("typ") != "third_party_access" or not isinstance(payload.get("scope"), list):
        raise AppError(
            "third_party_oauth.invalid_access_token", "第三方访问令牌无效", status_code=401
        )
    return ThirdPartyAccessClaims(
        user_id=str(payload["sub"]),
        app_id=str(payload["app_id"]),
        client_id=str(payload["client_id"]),
        token_session_id=str(payload["sid"]),
        token_family_id=str(payload["fid"]),
        scopes=tuple(str(scope) for scope in payload["scope"]),
    )


def decode_access_token(token: str, secret_key: str) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=["HS256"],
            options={"require": ["sub", "role", "sid", "typ", "iat", "exp", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError("auth.access_token_expired", "访问令牌已过期", status_code=401) from exc
    except jwt.PyJWTError as exc:
        raise AppError("auth.invalid_access_token", "访问令牌无效", status_code=401) from exc
    if payload.get("typ") != "access":
        raise AppError("auth.invalid_access_token", "访问令牌无效", status_code=401)
    return AccessClaims(
        user_id=str(payload["sub"]),
        role=str(payload["role"]),
        session_family_id=str(payload["sid"]),
        mfa_verified=bool(payload.get("mfa", False)),
    )
