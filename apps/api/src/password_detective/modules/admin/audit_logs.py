from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.db.audit import write_audit_log
from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.user import User
from password_detective.modules.admin.audit_schemas import (
    AdminAuditLogEntry,
    AdminAuditLogListResponse,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal

EXPORT_LIMIT = 5000
_SENSITIVE_DETAIL_MARKERS = (
    "password",
    "secret",
    "token",
    "cookie",
    "ciphertext",
    "credential",
    "email",
    "webhook",
    "payload",
    "digest",
)


@dataclass(frozen=True, slots=True)
class AdminAuditLogFilters:
    action: str | None = None
    result: str | None = None
    target_type: str | None = None
    actor_id: str | None = None
    request_id: str | None = None
    query: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


def _validate_filters(filters: AdminAuditLogFilters) -> None:
    if (
        filters.created_from is not None
        and filters.created_to is not None
        and filters.created_from > filters.created_to
    ):
        raise AppError(
            "admin.audit.invalid_time_range",
            "审计开始时间不能晚于结束时间",
            status_code=422,
        )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _conditions(filters: AdminAuditLogFilters) -> list[ColumnElement[bool]]:
    _validate_filters(filters)
    conditions: list[ColumnElement[bool]] = []
    if filters.action:
        conditions.append(AuditLog.action == filters.action.strip())
    if filters.result:
        conditions.append(AuditLog.result == filters.result.strip())
    if filters.target_type:
        conditions.append(AuditLog.target_type == filters.target_type.strip())
    if filters.actor_id:
        conditions.append(AuditLog.actor_id == filters.actor_id.strip())
    if filters.request_id:
        conditions.append(AuditLog.request_id == filters.request_id.strip())
    if filters.created_from is not None:
        conditions.append(AuditLog.created_at >= filters.created_from)
    if filters.created_to is not None:
        conditions.append(AuditLog.created_at <= filters.created_to)
    query = filters.query.strip() if filters.query else ""
    if query:
        pattern = f"%{_escape_like(query)}%"
        conditions.append(
            or_(
                AuditLog.id.ilike(pattern, escape="\\"),
                AuditLog.action.ilike(pattern, escape="\\"),
                AuditLog.target_type.ilike(pattern, escape="\\"),
                AuditLog.target_id.ilike(pattern, escape="\\"),
                AuditLog.request_id.ilike(pattern, escape="\\"),
                User.username.ilike(pattern, escape="\\"),
            )
        )
    return conditions


def _safe_detail_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return "[truncated]"
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value if len(value) <= 256 else f"{value[:256]}…"
    if isinstance(value, list):
        return [_safe_detail_value(item, depth=depth + 1) for item in value[:20]]
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for raw_key, nested in list(value.items())[:64]:
            key = str(raw_key)
            lowered = key.lower()
            if any(marker in lowered for marker in _SENSITIVE_DETAIL_MARKERS):
                safe[key] = "[redacted]"
            else:
                safe[key] = _safe_detail_value(nested, depth=depth + 1)
        return safe
    return str(value)[:256]


def _entry(log: AuditLog, actor: User | None) -> AdminAuditLogEntry:
    details = _safe_detail_value(log.details)
    assert isinstance(details, dict)
    return AdminAuditLogEntry(
        id=log.id,
        actor_id=log.actor_id,
        actor_username=actor.username if actor is not None else None,
        actor_role=actor.role if actor is not None else None,
        action=log.action,
        target_type=log.target_type,
        target_id=log.target_id,
        result=log.result,
        ip_prefix=log.ip_prefix,
        request_id=log.request_id,
        details=details,
        created_at=log.created_at,
    )


def list_admin_audit_logs(
    db: Session,
    *,
    filters: AdminAuditLogFilters,
    page: int,
    page_size: int,
) -> AdminAuditLogListResponse:
    conditions = _conditions(filters)
    total = int(
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .outerjoin(User, User.id == AuditLog.actor_id)
            .where(*conditions)
        )
        or 0
    )
    rows = db.execute(
        select(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AdminAuditLogListResponse(
        items=[_entry(log, actor) for log, actor in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_admin_audit_log(db: Session, audit_id: str) -> AdminAuditLogEntry:
    row = db.execute(
        select(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(AuditLog.id == audit_id)
    ).one_or_none()
    if row is None:
        raise AppError("admin.audit_log_not_found", "未找到审计事件", status_code=404)
    log, actor = row
    return _entry(log, actor)


def _csv_safe(value: str | None) -> str:
    if value is None:
        return ""
    if value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def export_admin_audit_logs(
    db: Session,
    *,
    filters: AdminAuditLogFilters,
    principal: Principal,
    context: ClientContext,
) -> tuple[bytes, int]:
    conditions = _conditions(filters)
    total = int(
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .outerjoin(User, User.id == AuditLog.actor_id)
            .where(*conditions)
        )
        or 0
    )
    if total > EXPORT_LIMIT:
        raise AppError(
            "admin.audit_export_too_large",
            "审计导出超过单次上限，请缩小筛选范围",
            status_code=422,
            details={"total": total, "max_rows": EXPORT_LIMIT},
        )
    rows = db.execute(
        select(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    ).all()
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "created_at",
            "actor_id",
            "actor_username",
            "actor_role",
            "action",
            "target_type",
            "target_id",
            "result",
            "ip_prefix",
            "request_id",
            "details_json",
        ]
    )
    for log, actor in rows:
        entry = _entry(log, actor)
        writer.writerow(
            [
                _csv_safe(entry.id),
                entry.created_at.isoformat(),
                _csv_safe(entry.actor_id),
                _csv_safe(entry.actor_username),
                entry.actor_role.value if entry.actor_role is not None else "",
                _csv_safe(entry.action),
                _csv_safe(entry.target_type),
                _csv_safe(entry.target_id),
                _csv_safe(entry.result),
                _csv_safe(entry.ip_prefix),
                _csv_safe(entry.request_id),
                json.dumps(entry.details, ensure_ascii=False, separators=(",", ":")),
            ]
        )
    write_audit_log(
        db,
        action="admin.audit.export",
        target_type="audit_log",
        result="success",
        actor_id=principal.user.id,
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "exported_rows": total,
            "filter_count": sum(
                value not in (None, "")
                for value in (
                    filters.action,
                    filters.result,
                    filters.target_type,
                    filters.actor_id,
                    filters.request_id,
                    filters.query,
                    filters.created_from,
                    filters.created_to,
                )
            ),
        },
    )
    db.commit()
    return ("\ufeff" + buffer.getvalue()).encode("utf-8"), total
