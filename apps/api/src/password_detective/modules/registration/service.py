from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.registration_invite import (
    RegistrationInvite,
    RegistrationInviteUse,
)
from password_detective.db.models.system_setting import SystemSetting
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.registration.schemas import (
    RegistrationInviteCreatedResponse,
    RegistrationInviteCreateRequest,
    RegistrationInviteListResponse,
    RegistrationInviteResponse,
    RegistrationInviteStatus,
    RegistrationPolicyResponse,
    RegistrationPolicyUpdate,
)

REGISTRATION_POLICY_KEY = "registration_policy"
_INVALID_INVITE_MESSAGE = "邀请码无效或已不可用"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def get_registration_policy(db: Session) -> RegistrationPolicyResponse:
    record = db.get(SystemSetting, REGISTRATION_POLICY_KEY)
    raw_value = record.value_json.get("value") if record else None
    try:
        return RegistrationPolicyResponse.model_validate(raw_value or {"mode": "open"})
    except (TypeError, ValueError):
        return RegistrationPolicyResponse()


def save_registration_policy(
    db: Session,
    *,
    payload: RegistrationPolicyUpdate,
    principal: Principal,
    context: ClientContext,
) -> RegistrationPolicyResponse:
    previous = get_registration_policy(db)
    record = db.get(SystemSetting, REGISTRATION_POLICY_KEY)
    if record is None:
        db.add(
            SystemSetting(
                key=REGISTRATION_POLICY_KEY,
                value_json={"value": payload.model_dump(mode="json")},
            )
        )
    else:
        record.value_json = {"value": payload.model_dump(mode="json")}
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.registration.policy_saved",
        target_type="registration_policy",
        target_id=REGISTRATION_POLICY_KEY,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"previous_mode": previous.mode, "current_mode": payload.mode},
    )
    db.commit()
    return RegistrationPolicyResponse(mode=payload.mode)


def _invite_status(invite: RegistrationInvite, now: datetime) -> RegistrationInviteStatus:
    if invite.revoked_at is not None:
        return "revoked"
    if invite.expires_at is not None and _aware(invite.expires_at) <= now:
        return "expired"
    if invite.use_count >= invite.max_uses:
        return "exhausted"
    return "active"


def _invite_response(invite: RegistrationInvite) -> RegistrationInviteResponse:
    return RegistrationInviteResponse(
        id=invite.id,
        label=invite.label,
        max_uses=invite.max_uses,
        use_count=invite.use_count,
        remaining_uses=max(0, invite.max_uses - invite.use_count),
        status=_invite_status(invite, utc_now()),
        expires_at=invite.expires_at,
        revoked_at=invite.revoked_at,
        created_at=invite.created_at,
    )


def create_registration_invite(
    db: Session,
    *,
    payload: RegistrationInviteCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> RegistrationInviteCreatedResponse:
    now = utc_now()
    if payload.expires_at is not None and _aware(payload.expires_at) <= now:
        raise AppError(
            "admin.registration_invite_expiry_invalid",
            "邀请码有效期必须晚于当前时间",
            status_code=422,
        )
    code = f"PD-{secrets.token_urlsafe(24)}"
    invite = RegistrationInvite(
        code_hash=_code_hash(code),
        label=payload.label,
        max_uses=payload.max_uses,
        expires_at=payload.expires_at,
        created_by=principal.user.id,
    )
    db.add(invite)
    db.flush()
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.registration_invite.created",
        target_type="registration_invite",
        target_id=invite.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"max_uses": invite.max_uses, "has_expiry": invite.expires_at is not None},
    )
    db.commit()
    db.refresh(invite)
    response = _invite_response(invite)
    return RegistrationInviteCreatedResponse(**response.model_dump(), code=code)


def list_registration_invites(db: Session) -> RegistrationInviteListResponse:
    items = list(
        db.scalars(
            select(RegistrationInvite).order_by(
                RegistrationInvite.created_at.desc(), RegistrationInvite.id.desc()
            )
        )
    )
    return RegistrationInviteListResponse(
        items=[_invite_response(item) for item in items],
        total=len(items),
    )


def revoke_registration_invite(
    db: Session,
    *,
    invite_id: str,
    principal: Principal,
    context: ClientContext,
) -> RegistrationInviteResponse:
    invite = db.scalar(
        select(RegistrationInvite)
        .where(RegistrationInvite.id == invite_id)
        .with_for_update()
    )
    if invite is None:
        raise AppError("admin.registration_invite_not_found", "邀请码不存在", status_code=404)
    if invite.revoked_at is None:
        invite.revoked_at = utc_now()
        write_audit_log(
            db,
            actor_id=principal.user.id,
            action="admin.registration_invite.revoked",
            target_type="registration_invite",
            target_id=invite.id,
            result="success",
            ip_prefix=context.ip_prefix,
            request_id=context.request_id,
        )
        db.commit()
        db.refresh(invite)
    return _invite_response(invite)


def _reject_invite(
    db: Session,
    *,
    invite_id: str | None,
    context: ClientContext,
    reason: str,
) -> None:
    write_audit_log(
        db,
        actor_id=None,
        action="auth.registration_invite.consume",
        target_type="registration_invite",
        target_id=invite_id,
        result="blocked",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"reason": reason},
    )
    db.commit()
    raise AppError(
        "auth.registration_invite_invalid",
        _INVALID_INVITE_MESSAGE,
        status_code=403,
    )


def resolve_registration_invite(
    db: Session,
    *,
    invite_code: str | None,
    context: ClientContext,
) -> RegistrationInvite | None:
    if get_registration_policy(db).mode == "open":
        return None
    if not invite_code or not invite_code.strip():
        _reject_invite(db, invite_id=None, context=context, reason="missing")
    invite = db.scalar(
        select(RegistrationInvite).where(
            RegistrationInvite.code_hash == _code_hash(invite_code or "")
        )
    )
    if invite is None:
        _reject_invite(db, invite_id=None, context=context, reason="unknown")
    status = _invite_status(invite, utc_now())
    if status != "active":
        _reject_invite(db, invite_id=invite.id, context=context, reason=status)
    return invite


def consume_registration_invite(
    db: Session,
    *,
    invite: RegistrationInvite | None,
    user_id: str,
    context: ClientContext,
) -> None:
    if invite is None:
        return
    now = utc_now()
    claimed = db.execute(
        update(RegistrationInvite)
        .where(
            RegistrationInvite.id == invite.id,
            RegistrationInvite.revoked_at.is_(None),
            RegistrationInvite.use_count < RegistrationInvite.max_uses,
            or_(RegistrationInvite.expires_at.is_(None), RegistrationInvite.expires_at > now),
        )
        .values(use_count=RegistrationInvite.use_count + 1)
    )
    if claimed.rowcount != 1:
        db.rollback()
        _reject_invite(db, invite_id=invite.id, context=context, reason="concurrent_unavailable")
    db.add(RegistrationInviteUse(invite_id=invite.id, user_id=user_id))
    write_audit_log(
        db,
        actor_id=user_id,
        action="auth.registration_invite.consume",
        target_type="registration_invite",
        target_id=invite.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
    )
