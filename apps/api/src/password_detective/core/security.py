from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now

_password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


@dataclass(frozen=True)
class AccessClaims:
    user_id: str
    role: str
    session_family_id: str


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


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    *,
    secret_key: str,
    ttl_minutes: int,
    user_id: str,
    role: str,
    session_family_id: str,
) -> str:
    now = utc_now()
    payload = {
        "sub": user_id,
        "role": role,
        "sid": session_family_id,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


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
    )
