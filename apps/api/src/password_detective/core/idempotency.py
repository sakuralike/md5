from __future__ import annotations

import re

from fastapi import Header

from password_detective.core.errors import AppError

_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")


def require_idempotency_key(idempotency_key: str | None = Header(default=None)) -> str:
    if not idempotency_key or not _PATTERN.fullmatch(idempotency_key):
        raise AppError(
            "request.invalid_idempotency_key",
            "该操作需要 16 至 128 字符的有效 Idempotency-Key",
            status_code=400,
        )
    return idempotency_key
