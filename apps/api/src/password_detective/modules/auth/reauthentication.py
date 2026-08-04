from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.operational_settings import get_operational_setting
from password_detective.core.security import hash_opaque_token, verify_account_password
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.reauthentication_grant import (
    ReauthenticationGrant,
    ReauthenticationPurpose,
)
from password_detective.db.models.user import User
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.schemas import ReauthenticationResponse


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _create_token() -> str:
    return "reauth_" + secrets.token_urlsafe(32)


def issue_reauthentication_grant(
    db: Session,
    settings: Settings,
    *,
    user: User,
    session_family_id: str,
    purpose: ReauthenticationPurpose,
    current_password: str,
    totp_code: str | None,
    context: ClientContext,
) -> ReauthenticationResponse:
    if not verify_account_password(user.account_password_hash, current_password):
        raise AppError("auth.invalid_current_password", "当前密码不正确", status_code=400)

    mfa_verified = False
    if user.totp_enabled:
        from password_detective.modules.auth.totp import verify_user_totp

        mfa_verified = verify_user_totp(user, settings, totp_code)

    now = utc_now()
    db.execute(
        update(ReauthenticationGrant)
        .where(
            ReauthenticationGrant.user_id == user.id,
            ReauthenticationGrant.session_family_id == session_family_id,
            ReauthenticationGrant.purpose == purpose,
            ReauthenticationGrant.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    raw_token = _create_token()
    record = ReauthenticationGrant(
        user_id=user.id,
        session_family_id=session_family_id,
        purpose=purpose,
        token_hash=hash_opaque_token(raw_token),
        mfa_verified=mfa_verified,
        expires_at=now
        + timedelta(
            minutes=get_operational_setting(
                db, "reauthentication_ttl_minutes", settings.reauthentication_ttl_minutes
            )
        ),
    )
    db.add(record)
    db.flush()
    write_audit_log(
        db,
        actor_id=user.id,
        action="auth.reauthentication.issued",
        target_type="reauthentication_grant",
        target_id=record.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"purpose": purpose.value, "mfa_verified": mfa_verified},
    )
    db.commit()
    db.refresh(record)
    return ReauthenticationResponse(
        reauth_token=raw_token,
        purpose=record.purpose,
        expires_at=record.expires_at,
    )


def consume_reauthentication_grant(
    db: Session,
    *,
    raw_token: str,
    user_id: str,
    session_family_id: str,
    expected_purpose: ReauthenticationPurpose,
) -> ReauthenticationGrant:
    record = db.scalar(
        select(ReauthenticationGrant)
        .where(ReauthenticationGrant.token_hash == hash_opaque_token(raw_token))
        .with_for_update()
    )
    now = utc_now()
    if (
        record is None
        or record.user_id != user_id
        or record.session_family_id != session_family_id
        or record.purpose != expected_purpose
        or record.consumed_at is not None
        or _aware(record.expires_at) <= now
    ):
        raise AppError(
            "auth.invalid_reauthentication_token",
            "再认证凭据无效、已使用或已过期",
            status_code=401,
        )
    record.consumed_at = now
    return record


def revoke_reauthentication_grants(db: Session, *, user_id: str) -> int:
    result = db.execute(
        update(ReauthenticationGrant)
        .where(
            ReauthenticationGrant.user_id == user_id,
            ReauthenticationGrant.consumed_at.is_(None),
        )
        .values(consumed_at=utc_now())
    )
    return result.rowcount or 0
