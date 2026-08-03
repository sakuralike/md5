from __future__ import annotations

import pyotp
from sqlalchemy import update
from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.security import decrypt_secret, encrypt_secret
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.reauthentication_grant import ReauthenticationPurpose
from password_detective.db.models.user import User
from password_detective.db.models.user_session import UserSession
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.reauthentication import (
    consume_reauthentication_grant,
    revoke_reauthentication_grants,
)
from password_detective.modules.auth.schemas import TotpSetupResponse


def begin_totp_setup(
    db: Session,
    settings: Settings,
    *,
    user: User,
    context: ClientContext,
) -> TotpSetupResponse:
    if user.totp_secret_ciphertext:
        raise AppError("auth.totp_already_enabled", "TOTP 已启用", status_code=409)
    secret = pyotp.random_base32()
    user.totp_pending_secret_ciphertext = encrypt_secret(secret, settings.app_secret_key)
    write_audit_log(
        db,
        actor_id=user.id,
        action="auth.totp.setup_started",
        target_type="user",
        target_id=user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
    )
    db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="密码侦探社")
    return TotpSetupResponse(secret=secret, provisioning_uri=uri)


def confirm_totp_setup(
    db: Session,
    settings: Settings,
    *,
    user: User,
    session_family_id: str,
    code: str,
    context: ClientContext,
) -> None:
    ciphertext = user.totp_pending_secret_ciphertext
    if not ciphertext:
        raise AppError("auth.totp_setup_not_started", "请先生成 TOTP 配置", status_code=409)
    secret = decrypt_secret(ciphertext, settings.app_secret_key)
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        raise AppError("auth.invalid_totp_code", "动态验证码不正确", status_code=400)
    now = utc_now()
    user.totp_secret_ciphertext = ciphertext
    user.totp_pending_secret_ciphertext = None
    user.totp_enabled_at = now
    db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.family_id == session_family_id,
            UserSession.revoked_at.is_(None),
        )
        .values(mfa_verified_at=now)
    )
    write_audit_log(
        db,
        actor_id=user.id,
        action="auth.totp.enabled",
        target_type="user",
        target_id=user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
    )
    db.commit()


def disable_totp(
    db: Session,
    *,
    user: User,
    session_family_id: str,
    reauth_token: str,
    context: ClientContext,
) -> None:
    if not user.totp_secret_ciphertext:
        raise AppError("auth.totp_not_enabled", "TOTP 尚未启用", status_code=409)
    consume_reauthentication_grant(
        db,
        raw_token=reauth_token,
        user_id=user.id,
        session_family_id=session_family_id,
        expected_purpose=ReauthenticationPurpose.TOTP_DISABLE,
    )
    user.totp_secret_ciphertext = None
    user.totp_pending_secret_ciphertext = None
    user.totp_enabled_at = None
    revoke_reauthentication_grants(db, user_id=user.id)
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(mfa_verified_at=None)
    )
    write_audit_log(
        db,
        actor_id=user.id,
        action="auth.totp.disabled",
        target_type="user",
        target_id=user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
    )
    db.commit()


def verify_user_totp(user: User, settings: Settings, code: str | None) -> bool:
    if not user.totp_secret_ciphertext:
        return False
    if not code:
        raise AppError("auth.totp_required", "请输入动态验证码", status_code=401)
    secret = decrypt_secret(user.totp_secret_ciphertext, settings.app_secret_key)
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        raise AppError("auth.invalid_totp_code", "动态验证码不正确", status_code=401)
    return True
