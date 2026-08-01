from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from password_detective.db.models.audit_log import AuditLog


def write_audit_log(
    db: Session,
    *,
    action: str,
    target_type: str,
    result: str,
    actor_id: str | None = None,
    target_id: str | None = None,
    ip_prefix: str | None = None,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        result=result,
        ip_prefix=ip_prefix,
        request_id=request_id,
        details=details or {},
    )
    db.add(entry)
    return entry
