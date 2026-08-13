from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.browser_session import (
    clear_refresh_cookie,
    enforce_browser_origin,
    require_refresh_cookie,
    set_refresh_cookie,
)
from password_detective.core.config import Settings, get_settings
from password_detective.core.idempotency import (
    abandon_idempotency,
    acquire_idempotency,
    complete_idempotency,
    payload_digest,
    private_owner_key,
    require_idempotency_key,
)
from password_detective.core.notifications import NotificationGateway
from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.db.models.account_action_token import AccountTokenKind
from password_detective.db.models.user_session import UserSession
from password_detective.modules.auth.account_tokens import (
    issue_account_token,
    request_password_reset,
    reset_password,
    verify_email_token,
)
from password_detective.modules.auth.context import get_client_context, get_notification_gateway
from password_detective.modules.auth.dependencies import Principal, get_current_principal
from password_detective.modules.auth.reauthentication import issue_reauthentication_grant
from password_detective.modules.auth.schemas import (
    BrowserTokenResponse,
    EmailTokenRequest,
    LoginRequest,
    MessageResponse,
    PasswordChangeRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    ProfileUpdateRequest,
    ReauthenticationRequest,
    ReauthenticationResponse,
    RefreshRequest,
    RegisterRequest,
    SessionResponse,
    TokenResponse,
    TotpCodeRequest,
    TotpDisableRequest,
    TotpSetupResponse,
    UserResponse,
)
from password_detective.modules.auth.service import (
    change_password,
    login_user,
    register_user,
    revoke_all_sessions,
    revoke_by_refresh_token,
    revoke_session_family,
    rotate_refresh_token,
    update_profile,
)
from password_detective.modules.auth.totp import (
    begin_totp_setup,
    confirm_totp_setup,
    disable_totp,
)

router = APIRouter(tags=["认证与账号"])


@router.post(
    "/web/auth/login",
    response_model=BrowserTokenResponse,
    dependencies=[
        Depends(
            rate_limit(
                "web.auth.login",
                limit=get_settings().web_login_rate_limit,
                window_seconds=60,
            )
        )
    ],
)
def web_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BrowserTokenResponse:
    enforce_browser_origin(request, settings)
    tokens = login_user(db, settings, payload, get_client_context(request))
    set_refresh_cookie(response, settings, client="web", refresh_token=tokens.refresh_token)
    return BrowserTokenResponse.from_token_response(tokens)


@router.post(
    "/web/auth/refresh",
    response_model=BrowserTokenResponse,
    dependencies=[Depends(rate_limit("web.auth.refresh", limit=30, window_seconds=60))],
)
def web_refresh(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BrowserTokenResponse:
    enforce_browser_origin(request, settings)
    refresh_token = require_refresh_cookie(request, client="web")
    tokens = rotate_refresh_token(db, settings, refresh_token, get_client_context(request))
    set_refresh_cookie(response, settings, client="web", refresh_token=tokens.refresh_token)
    return BrowserTokenResponse.from_token_response(tokens)


@router.post("/web/auth/logout", response_model=MessageResponse)
def web_logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    enforce_browser_origin(request, settings)
    refresh_token = request.cookies.get("pd_web_refresh")
    if refresh_token:
        revoke_by_refresh_token(
            db,
            refresh_token=refresh_token,
            reason="web_logout",
            context=get_client_context(request),
        )
    clear_refresh_cookie(response, settings, client="web")
    return MessageResponse(message="已退出当前会话")


@router.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("auth.register", limit=10, window_seconds=3600))],
)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    notifications: Annotated[NotificationGateway, Depends(get_notification_gateway)],
) -> UserResponse:
    return register_user(db, settings, notifications, payload, get_client_context(request))


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("auth.login", limit=10, window_seconds=60))],
)
def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    return login_user(db, settings, payload, get_client_context(request))


@router.post(
    "/auth/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("auth.refresh", limit=30, window_seconds=60))],
)
def refresh(
    payload: RefreshRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    return rotate_refresh_token(db, settings, payload.refresh_token, get_client_context(request))


@router.post(
    "/auth/email/verify",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("auth.email_verify", limit=20, window_seconds=3600))],
)
def verify_email(
    payload: EmailTokenRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    verify_email_token(db, payload.token, get_client_context(request))
    return MessageResponse(message="邮箱验证成功")


@router.post(
    "/auth/email/resend",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("auth.email_resend", limit=5, window_seconds=3600))],
)
def resend_email_verification(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    notifications: Annotated[NotificationGateway, Depends(get_notification_gateway)],
) -> MessageResponse:
    if principal.user.email_verified:
        return MessageResponse(message="邮箱已完成验证")
    issue_account_token(
        db,
        settings,
        notifications,
        user=principal.user,
        kind=AccountTokenKind.EMAIL_VERIFICATION,
        context=get_client_context(request),
    )
    return MessageResponse(message="验证邮件已重新发送")


@router.post(
    "/auth/password/forgot",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("auth.password_forgot", limit=5, window_seconds=3600))],
)
def forgot_password(
    payload: PasswordForgotRequest,
    request: Request,
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    notifications: Annotated[NotificationGateway, Depends(get_notification_gateway)],
) -> MessageResponse:
    email = str(payload.email).strip().lower()
    context = get_client_context(request)
    lease = acquire_idempotency(
        db,
        scope="auth.password_forgot",
        owner_key=private_owner_key(context.ip_prefix or "unknown"),
        idempotency_key=idempotency_key,
        request_hash=payload_digest({"email": email}),
    )
    if lease.cached_response is not None:
        return MessageResponse.model_validate(lease.cached_response)
    response = MessageResponse(message="如果邮箱已注册，我们将发送密码重置说明")
    try:
        request_password_reset(
            db,
            settings,
            notifications,
            email=email,
            context=context,
        )
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_200_OK,
            response_body=response.model_dump(mode="json"),
        )
    except Exception:
        abandon_idempotency(db, lease)
        raise
    return response


@router.post(
    "/auth/password/reset",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("auth.password_reset", limit=10, window_seconds=3600))],
)
def password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    reset_password(
        db,
        token=payload.token,
        new_password=payload.new_password,
        context=get_client_context(request),
    )
    return MessageResponse(message="密码已重置，请重新登录")


@router.post("/auth/logout", response_model=MessageResponse)
def logout(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    revoke_session_family(
        db,
        user_id=principal.user.id,
        family_id=principal.session_family_id,
        reason="logout",
        context=get_client_context(request),
    )
    return MessageResponse(message="已退出当前会话")


@router.post("/auth/logout-all", response_model=MessageResponse)
def logout_all(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    revoke_all_sessions(db, user_id=principal.user.id, context=get_client_context(request))
    return MessageResponse(message="已退出全部会话")


@router.get("/me/profile", response_model=UserResponse)
def profile(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> UserResponse:
    return principal.user


@router.patch(
    "/me/profile",
    response_model=UserResponse,
    dependencies=[Depends(rate_limit("me.profile.update", limit=20, window_seconds=3600))],
)
def update_my_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    db: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    lease = acquire_idempotency(
        db,
        scope="me.profile.update",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest(payload.model_dump(mode="json")),
    )
    if lease.cached_response is not None:
        return UserResponse.model_validate(lease.cached_response)
    try:
        user = update_profile(
            db,
            user=principal.user,
            payload=payload,
            context=get_client_context(request),
        )
        response = UserResponse.model_validate(user)
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_200_OK,
            response_body=response.model_dump(mode="json"),
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@router.post(
    "/me/security/reauthenticate",
    response_model=ReauthenticationResponse,
    dependencies=[Depends(rate_limit("me.reauthenticate", limit=10, window_seconds=3600))],
)
def reauthenticate_my_session(
    payload: ReauthenticationRequest,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReauthenticationResponse:
    response.headers["Cache-Control"] = "no-store"
    return issue_reauthentication_grant(
        db,
        settings,
        user=principal.user,
        session_family_id=principal.session_family_id,
        purpose=payload.purpose,
        current_password=payload.current_password,
        totp_code=payload.totp_code,
        context=get_client_context(request),
    )


@router.post(
    "/me/security/password/change",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("me.password.change", limit=10, window_seconds=3600))],
)
def change_my_password(
    payload: PasswordChangeRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    lease = acquire_idempotency(
        db,
        scope="me.password.change",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest(payload.model_dump(mode="json")),
    )
    if lease.cached_response is not None:
        return MessageResponse.model_validate(lease.cached_response)
    response = MessageResponse(message="密码已修改，其他登录会话已撤销")
    try:
        change_password(
            db,
            user=principal.user,
            session_family_id=principal.session_family_id,
            payload=payload,
            context=get_client_context(request),
        )
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_200_OK,
            response_body=response.model_dump(mode="json"),
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@router.post(
    "/me/security/totp/setup",
    response_model=TotpSetupResponse,
    dependencies=[Depends(rate_limit("me.totp.setup", limit=5, window_seconds=3600))],
)
def setup_my_totp(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TotpSetupResponse:
    return begin_totp_setup(
        db,
        settings,
        user=principal.user,
        context=get_client_context(request),
    )


@router.post(
    "/me/security/totp/confirm",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("me.totp.confirm", limit=10, window_seconds=3600))],
)
def confirm_my_totp(
    payload: TotpCodeRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    lease = acquire_idempotency(
        db,
        scope="me.totp.confirm",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest(payload.model_dump(mode="json")),
    )
    if lease.cached_response is not None:
        return MessageResponse.model_validate(lease.cached_response)
    response = MessageResponse(message="TOTP 已启用")
    try:
        confirm_totp_setup(
            db,
            settings,
            user=principal.user,
            session_family_id=principal.session_family_id,
            code=payload.code,
            context=get_client_context(request),
        )
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_200_OK,
            response_body=response.model_dump(mode="json"),
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@router.delete(
    "/me/security/totp",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("me.totp.disable", limit=10, window_seconds=3600))],
)
def disable_my_totp(
    payload: TotpDisableRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    lease = acquire_idempotency(
        db,
        scope="me.totp.disable",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest(payload.model_dump(mode="json")),
    )
    if lease.cached_response is not None:
        return MessageResponse.model_validate(lease.cached_response)
    response = MessageResponse(message="TOTP 已停用")
    try:
        disable_totp(
            db,
            user=principal.user,
            session_family_id=principal.session_family_id,
            reauth_token=payload.reauth_token,
            context=get_client_context(request),
        )
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_200_OK,
            response_body=response.model_dump(mode="json"),
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@router.get("/me/security/sessions", response_model=list[SessionResponse])
def sessions(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SessionResponse]:
    rows = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == principal.user.id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.last_used_at.desc())
    ).all()
    return [
        SessionResponse(
            id=row.family_id,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            expires_at=row.expires_at,
            user_agent=row.user_agent,
            ip_prefix=row.ip_prefix,
            current=row.family_id == principal.session_family_id,
            mfa_verified=row.mfa_verified_at is not None,
        )
        for row in rows
    ]


@router.delete("/me/security/sessions/{family_id}", response_model=MessageResponse)
def revoke_session(
    family_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    revoke_session_family(
        db,
        user_id=principal.user.id,
        family_id=family_id,
        reason="user_revoked",
        context=get_client_context(request),
    )
    return MessageResponse(message="会话已撤销")
