from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import Header
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.models.idempotency_record import IdempotencyRecord, IdempotencyStatus

_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")


@dataclass(frozen=True)
class IdempotencyLease:
    record_id: str
    cached_response: dict[str, Any] | None = None
    cached_status: int | None = None


def require_idempotency_key(idempotency_key: str | None = Header(default=None)) -> str:
    if not idempotency_key or not _PATTERN.fullmatch(idempotency_key):
        raise AppError(
            "request.invalid_idempotency_key",
            "该操作需要 16 至 128 字符的有效 Idempotency-Key",
            status_code=400,
        )
    return idempotency_key


def payload_digest(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def private_owner_key(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def acquire_idempotency(
    db: Session,
    *,
    scope: str,
    owner_key: str,
    idempotency_key: str,
    request_hash: str,
    ttl_hours: int = 24,
) -> IdempotencyLease:
    key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    record = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.owner_key == owner_key,
            IdempotencyRecord.key_hash == key_hash,
        )
    )
    if record is not None:
        return _existing_lease(record, request_hash)

    record = IdempotencyRecord(
        scope=scope,
        owner_key=owner_key,
        key_hash=key_hash,
        request_hash=request_hash,
        expires_at=utc_now() + timedelta(hours=ttl_hours),
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.owner_key == owner_key,
                IdempotencyRecord.key_hash == key_hash,
            )
        )
        if concurrent is None:
            raise
        return _existing_lease(concurrent, request_hash)
    db.refresh(record)
    return IdempotencyLease(record_id=record.id)


def complete_idempotency(
    db: Session,
    lease: IdempotencyLease,
    *,
    response_status: int,
    response_body: dict[str, Any],
) -> None:
    record = db.get(IdempotencyRecord, lease.record_id)
    if record is None:
        raise RuntimeError("幂等记录不存在")
    record.status = IdempotencyStatus.COMPLETED
    record.response_status = response_status
    record.response_body = response_body
    record.completed_at = utc_now()
    db.commit()


def abandon_idempotency(db: Session, lease: IdempotencyLease) -> None:
    record = db.get(IdempotencyRecord, lease.record_id)
    if record is not None and record.status == IdempotencyStatus.IN_PROGRESS:
        db.delete(record)
        db.commit()


def _existing_lease(record: IdempotencyRecord, request_hash: str) -> IdempotencyLease:
    if record.request_hash != request_hash:
        raise AppError(
            "request.idempotency_conflict",
            "相同 Idempotency-Key 不能用于不同请求",
            status_code=409,
        )
    if record.status == IdempotencyStatus.COMPLETED and record.response_body is not None:
        return IdempotencyLease(
            record_id=record.id,
            cached_response=record.response_body,
            cached_status=record.response_status,
        )
    raise AppError(
        "request.idempotency_in_progress",
        "相同请求正在处理中，请稍后重试",
        status_code=409,
    )
