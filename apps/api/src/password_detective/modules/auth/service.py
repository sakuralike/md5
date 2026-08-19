from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.ids import new_id
from password_detective.core.notifications import NotificationGateway
from password_detective.core.security import (
    create_access_token,
    create_refresh_token,
    hash_account_password,
    hash_refresh_token,
    needs_password_rehash,
    verify_account_password,
)
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.account_action_token import AccountTokenKind
from password_detective.db.models.reauthentication_grant import ReauthenticationPurpose
from password_detective.db.models.system_setting import SystemSetting
from password_detective.db.models.user import User, UserStatus
from password_detective.db.models.user_session import UserSession
from password_detective.modules.auth.account_tokens import issue_account_token
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.reauthentication import (
    consume_reauthentication_grant,
    revoke_reauthentication_grants,
)
from password_detective.modules.auth.schemas import (
    LoginRequest,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    TokenResponse,
)
from password_detective.modules.auth.totp import verify_user_totp
from password_detective.modules.reputation.levels import (
    DAILY_ACTIVITY_GROWTH,
    record_growth_event,
)

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _session_limit_settings(db: Session) -> tuple[int, str]:
    limit_record = db.get(SystemSetting, "max_active_sessions")
    policy_record = db.get(SystemSetting, "session_overflow_policy")
    raw_limit = limit_record.value_json.get("value") if limit_record else 0
    raw_policy = policy_record.value_json.get("value") if policy_record else "deny_new"
    limit = raw_limit if isinstance(raw_limit, int) and not isinstance(raw_limit, bool) else 0
    if not 0 <= limit <= 100:
        limit = 0
    policy = raw_policy if raw_policy in {"deny_new", "revoke_oldest"} else "deny_new"
    return limit, policy


def _enforce_session_limit(
    db: Session,
    *,
    user: User,
    now: datetime,
    context: ClientContext,
) -> None:
    limit, policy = _session_limit_settings(db)
    if limit == 0:
        return

    active_family_ids = (
        select(UserSession.family_id)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .distinct()
        .subquery()
    )
    first_created_at = func.min(UserSession.created_at)
    active_families = db.execute(
        select(UserSession.family_id, first_created_at.label("first_created_at"))
        .join(active_family_ids, active_family_ids.c.family_id == UserSession.family_id)
        .where(UserSession.user_id == user.id)
        .group_by(UserSession.family_id)
        .order_by(first_created_at.asc(), UserSession.family_id.asc())
    ).all()
    if len(active_families) < limit:
        return

    if policy == "deny_new":
        write_audit_log(
            db,
            actor_id=user.id,
            action="auth.session_limit",
            target_type="user",
            target_id=user.id,
            result="blocked",
            ip_prefix=context.ip_prefix,
            request_id=context.request_id,
            details={
                "policy": policy,
                "limit": limit,
                "active_session_count": len(active_families),
            },
        )
        db.commit()
        raise AppError(
            "auth.session_limit_reached",
            "当前账号已达到同时登录设备数上限",
            status_code=409,
            details={"limit": limit},
        )

    revoke_count = len(active_families) - limit + 1
    oldest_family_ids = [row.family_id for row in active_families[:revoke_count]]
    db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.family_id.in_(oldest_family_ids),
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=now, revoked_reason="session_limit_revoke_oldest")
    )
    write_audit_log(
        db,
        actor_id=user.id,
        action="auth.session_limit",
        target_type="user",
        target_id=user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "policy": policy,
            "limit": limit,
            "active_session_count": len(active_families),
            "revoked_session_count": revoke_count,
        },
    )


def _issue_token_response(
    *, settings: Settings, user: User, session: UserSession, refresh_token: str
) -> TokenResponse:
    mfa_verified = session.mfa_verified_at is not None
    access_token = create_access_token(
        secret_key=settings.app_secret_key,
        ttl_minutes=settings.access_token_ttl_minutes,
        user_id=user.id,
        role=user.role.value,
        session_family_id=session.family_id,
        mfa_verified=mfa_verified,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_ttl_minutes * 60,
        mfa_verified=mfa_verified,
        user=user,
    )


def register_user(
    db: Session,
    settings: Settings,
    notifications: NotificationGateway,
    payload: RegisterRequest,
    context: ClientContext,
) -> User:
    username = payload.username.strip().lower()
    email = str(payload.email).strip().lower()
    existing = db.scalar(select(User.id).where(or_(User.username == username, User.email == email)))
    if existing:
        raise AppError("auth.account_conflict", "用户名或邮箱已被使用", status_code=409)

    user = User(
        username=username,
        email=email,
        account_password_hash=hash_account_password(payload.password),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("auth.account_conflict", "用户名或邮箱已被使用", status_code=409) from exc
    write_audit_log(
        db,
        actor_id=user.id,
        action="auth.register",
        target_type="user",
        target_id=user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
    )
    db.commit()
    db.refresh(user)
    issue_account_token(
        db,
        settings,
        notifications,
        user=user,
        kind=AccountTokenKind.EMAIL_VERIFICATION,
        context=context,
    )
    db.refresh(user)
    return user


def login_user(
    db: Session,
    settings: Settings,
    payload: LoginRequest,
    context: ClientContext,
) -> TokenResponse:
    login = payload.login.strip().lower()
    user = db.scalar(
        select(User).where(or_(User.username == login, User.email == login)).with_for_update()
    )
    now = utc_now()

    if user is None:
        raise AppError("auth.invalid_credentials", "用户名、邮箱或密码不正确", status_code=401)
    if user.status == UserStatus.DISABLED:
        raise AppError("auth.account_unavailable", "账号当前不可用", status_code=403)
    if user.locked_until and _aware(user.locked_until) > now:
        raise AppError("auth.temporarily_locked", "登录尝试过多，请稍后重试", status_code=423)

    if not verify_account_password(user.account_password_hash, payload.password):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.status = UserStatus.LOCKED
        write_audit_log(
            db,
            actor_id=user.id,
            action="auth.login",
            target_type="user",
            target_id=user.id,
            result="failure",
            ip_prefix=context.ip_prefix,
            request_id=context.request_id,
            details={"reason": "invalid_credentials"},
        )
        db.commit()
        raise AppError("auth.invalid_credentials", "用户名、邮箱或密码不正确", status_code=401)

    mfa_verified = False
    if user.totp_enabled_at is not None:
        mfa_verified = verify_user_totp(user, settings, payload.totp_code)

    if user.status == UserStatus.LOCKED:
        user.status = UserStatus.ACTIVE
    user.failed_login_count = 0
    user.locked_until = None
    if needs_password_rehash(user.account_password_hash):
        user.account_password_hash = hash_account_password(payload.password)

    _enforce_session_limit(db, user=user, now=now, context=context)
    refresh_token = create_refresh_token()
    session = UserSession(
        user_id=user.id,
        family_id=new_id(),
        refresh_token_hash=hash_refresh_token(refresh_token),
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=context.user_agent,
        ip_prefix=context.ip_prefix,
        mfa_verified_at=now if mfa_verified else None,
    )
    db.add(session)
    record_growth_event(
        db,
        user_id=user.id,
        amount=DAILY_ACTIVITY_GROWTH,
        event_type="activity.login_day",
        reference_id=now.date().isoformat(),
        reason_code="growth.daily_activity",
    )
    write_audit_log(
        db,
        actor_id=user.id,
        action="auth.login",
        target_type="session",
        target_id=session.family_id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"mfa_verified": mfa_verified},
    )
    db.commit()
    db.refresh(user)
    db.refresh(session)
    return _issue_token_response(
        settings=settings, user=user, session=session, refresh_token=refresh_token
    )


def rotate_refresh_token(
    db: Session,
    settings: Settings,
    refresh_token: str,
    context: ClientContext,
) -> TokenResponse:
    token_hash = hash_refresh_token(refresh_token)
    session = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == token_hash))
    if session is None:
        raise AppError("auth.invalid_refresh_token", "刷新令牌无效", status_code=401)

    now = utc_now()
    if session.revoked_at is not None:
        db.execute(
            update(UserSession)
            .where(UserSession.family_id == session.family_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason="refresh_token_reuse")
        )
        write_audit_log(
            db,
            actor_id=session.user_id,
            action="auth.refresh_reuse_detected",
            target_type="session",
            target_id=session.family_id,
            result="blocked",
            ip_prefix=context.ip_prefix,
            request_id=context.request_id,
        )
        db.commit()
        raise AppError(
            "auth.refresh_token_reused",
            "检测到刷新令牌重复使用，相关会话已撤销",
            status_code=401,
        )

    if _aware(session.expires_at) <= now:
        session.revoked_at = now
        session.revoked_reason = "expired"
        db.commit()
        raise AppError("auth.refresh_token_expired", "刷新令牌已过期", status_code=401)

    user = db.get(User, session.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise AppError("auth.account_unavailable", "账号当前不可用", status_code=403)

    claimed = db.execute(
        update(UserSession)
        .where(UserSession.id == session.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason="rotated", last_used_at=now)
    )
    if claimed.rowcount != 1:
        db.execute(
            update(UserSession)
            .where(UserSession.family_id == session.family_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason="refresh_token_reuse")
        )
        write_audit_log(
            db,
            actor_id=session.user_id,
            action="auth.refresh_reuse_detected",
            target_type="session",
            target_id=session.family_id,
            result="blocked",
            ip_prefix=context.ip_prefix,
            request_id=context.request_id,
        )
        db.commit()
        raise AppError(
            "auth.refresh_token_reused",
            "检测到刷新令牌重复使用，相关会话已撤销",
            status_code=401,
        )

    new_token = create_refresh_token()
    next_session = UserSession(
        user_id=user.id,
        family_id=session.family_id,
        refresh_token_hash=hash_refresh_token(new_token),
        rotated_from_id=session.id,
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=context.user_agent or session.user_agent,
        ip_prefix=context.ip_prefix or session.ip_prefix,
        mfa_verified_at=session.mfa_verified_at,
    )
    db.add(next_session)
    write_audit_log(
        db,
        actor_id=user.id,
        action="auth.refresh",
        target_type="session",
        target_id=session.family_id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
    )
    db.commit()
    db.refresh(next_session)
    return _issue_token_response(
        settings=settings, user=user, session=next_session, refresh_token=new_token
    )


def update_profile(
    db: Session,
    *,
    user: User,
    payload: ProfileUpdateRequest,
    context: ClientContext,
) -> User:
    del db, context
    requested_username = payload.username.strip().lower()
    if requested_username != user.username:
        raise AppError(
            "auth.username_immutable",
            "用户名在注册后不可修改；请在社区资料中维护公开展示名",
            status_code=409,
        )
    return user


def change_password(
    db: Session,
    *,
    user: User,
    session_family_id: str,
    payload: PasswordChangeRequest,
    context: ClientContext,
) -> int:
    consume_reauthentication_grant(
        db,
        raw_token=payload.reauth_token,
        user_id=user.id,
        session_family_id=session_family_id,
        expected_purpose=ReauthenticationPurpose.PASSWORD_CHANGE,
    )
    if verify_account_password(user.account_password_hash, payload.new_password):
        raise AppError("auth.password_unchanged", "新密码不能与当前密码相同", status_code=400)
    user.account_password_hash = hash_account_password(payload.new_password)
    now = utc_now()
    result = db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.family_id != session_family_id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=now, revoked_reason="password_changed")
    )
    revoked_rows = result.rowcount or 0
    revoked_reauthentication_grants = revoke_reauthentication_grants(db, user_id=user.id)
    write_audit_log(
        db,
        actor_id=user.id,
        action="auth.password.changed",
        target_type="user",
        target_id=user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "revoked_other_sessions": revoked_rows,
            "revoked_reauthentication_grants": revoked_reauthentication_grants,
        },
    )
    db.commit()
    return revoked_rows


def revoke_session_family(
    db: Session,
    *,
    user_id: str,
    family_id: str,
    reason: str,
    context: ClientContext,
) -> None:
    now = utc_now()
    result = db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.family_id == family_id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=now, revoked_reason=reason)
    )
    if not result.rowcount:
        raise AppError("auth.session_not_found", "会话不存在或已撤销", status_code=404)
    write_audit_log(
        db,
        actor_id=user_id,
        action="auth.session_revoke",
        target_type="session",
        target_id=family_id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"reason": reason},
    )
    db.commit()


def revoke_all_sessions(db: Session, *, user_id: str, context: ClientContext) -> int:
    now = utc_now()
    result = db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason="logout_all")
    )
    write_audit_log(
        db,
        actor_id=user_id,
        action="auth.logout_all",
        target_type="user",
        target_id=user_id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"revoked_rows": result.rowcount or 0},
    )
    db.commit()
    return result.rowcount or 0


def revoke_by_refresh_token(
    db: Session,
    *,
    refresh_token: str,
    reason: str,
    context: ClientContext,
) -> None:
    session = db.scalar(
        select(UserSession).where(
            UserSession.refresh_token_hash == hash_refresh_token(refresh_token)
        )
    )
    if session is None:
        return
    now = utc_now()
    db.execute(
        update(UserSession)
        .where(
            UserSession.family_id == session.family_id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=now, revoked_reason=reason)
    )
    write_audit_log(
        db,
        actor_id=session.user_id,
        action="auth.browser_logout",
        target_type="session",
        target_id=session.family_id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"reason": reason},
    )
    db.commit()
