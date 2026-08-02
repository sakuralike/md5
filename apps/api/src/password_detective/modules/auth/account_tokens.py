from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.notifications import NotificationGateway
from password_detective.core.security import (
    create_account_token,
    hash_account_password,
    hash_opaque_token,
)
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.account_action_token import AccountActionToken, AccountTokenKind
from password_detective.db.models.user import User
from password_detective.db.models.user_session import UserSession
from password_detective.modules.auth.context import ClientContext


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def issue_account_token(
    db: Session,
    settings: Settings,
    notifications: NotificationGateway,
    *,
    user: User,
    kind: AccountTokenKind,
    context: ClientContext,
) -> None:
    now = utc_now()
    db.execute(
        update(AccountActionToken)
        .where(
            AccountActionToken.user_id == user.id,
            AccountActionToken.kind == kind,
            AccountActionToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw_token = create_account_token()
    record = AccountActionToken(
        user_id=user.id,
        kind=kind,
        token_hash=hash_opaque_token(raw_token),
        expires_at=now + timedelta(minutes=settings.account_token_ttl_minutes),
    )
    db.add(record)
    write_audit_log(
        db,
        actor_id=user.id,
        action=f"auth.{kind.value}.issued",
        target_type="user",
        target_id=user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
    )
    db.commit()
    notifications.send_account_token(kind=kind.value, recipient=user.email, token=raw_token)


def verify_email_token(db: Session, token: str, context: ClientContext) -> None:
    record = _load_active_token(db, token, AccountTokenKind.EMAIL_VERIFICATION)
    user = db.get(User, record.user_id)
    if user is None:
        raise AppError("auth.invalid_account_token", "验证链接无效或已过期", status_code=400)
    now = utc_now()
    record.used_at = now
    user.email_verified_at = user.email_verified_at or now
    write_audit_log(
        db,
        actor_id=user.id,
        action="auth.email_verified",
        target_type="user",
        target_id=user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
    )
    db.commit()


def request_password_reset(
    db: Session,
    settings: Settings,
    notifications: NotificationGateway,
    *,
    email: str,
    context: ClientContext,
) -> None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        return
    issue_account_token(
        db,
        settings,
        notifications,
        user=user,
        kind=AccountTokenKind.PASSWORD_RESET,
        context=context,
    )


def reset_password(
    db: Session,
    *,
    token: str,
    new_password: str,
    context: ClientContext,
) -> None:
    record = _load_active_token(db, token, AccountTokenKind.PASSWORD_RESET)
    user = db.get(User, record.user_id)
    if user is None:
        raise AppError("auth.invalid_account_token", "重置链接无效或已过期", status_code=400)
    now = utc_now()
    record.used_at = now
    user.account_password_hash = hash_account_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason="password_reset")
    )
    write_audit_log(
        db,
        actor_id=user.id,
        action="auth.password_reset.completed",
        target_type="user",
        target_id=user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
    )
    db.commit()


def _load_active_token(
    db: Session, raw_token: str, expected_kind: AccountTokenKind
) -> AccountActionToken:
    record = db.scalar(
        select(AccountActionToken).where(
            AccountActionToken.token_hash == hash_opaque_token(raw_token),
            AccountActionToken.kind == expected_kind,
        )
    )
    now = utc_now()
    if record is None or record.used_at is not None or _aware(record.expires_at) <= now:
        raise AppError("auth.invalid_account_token", "验证链接无效或已过期", status_code=400)
    return record
