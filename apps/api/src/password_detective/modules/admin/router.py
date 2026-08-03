from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.browser_session import (
    clear_refresh_cookie,
    enforce_browser_origin,
    require_refresh_cookie,
    set_refresh_cookie,
)
from password_detective.core.config import Settings, get_settings
from password_detective.core.errors import AppError
from password_detective.core.idempotency import (
    abandon_idempotency,
    acquire_idempotency,
    complete_idempotency,
    payload_digest,
    require_idempotency_key,
)
from password_detective.core.rate_limit import rate_limit
from password_detective.core.security import hash_refresh_token
from password_detective.core.time import utc_now
from password_detective.db.dependencies import get_db
from password_detective.db.models.reauthentication_grant import ReauthenticationPurpose
from password_detective.db.models.user import UserRole, UserStatus
from password_detective.db.models.user_session import UserSession
from password_detective.modules.admin.audit_logs import (
    AdminAuditLogFilters,
    export_admin_audit_logs,
    get_admin_audit_log,
    list_admin_audit_logs,
)
from password_detective.modules.admin.audit_schemas import (
    AdminAuditLogEntry,
    AdminAuditLogListResponse,
)
from password_detective.modules.admin.dashboard import get_dashboard_summary
from password_detective.modules.admin.dashboard_schemas import AdminDashboardSummary
from password_detective.modules.admin.user_schemas import (
    AdminReauthenticationRequest,
    AdminReauthenticationResponse,
    AdminUserDetail,
    AdminUserListResponse,
    AdminUserSessionRevocationRequest,
    AdminUserSessionRevocationResponse,
    AdminUserStatusChangeRequest,
    AdminUserStatusChangeResponse,
)
from password_detective.modules.admin.users import (
    AdminUserFilters,
    change_admin_user_status,
    get_admin_user,
    list_admin_users,
    revoke_admin_user_sessions,
)
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import (
    Principal,
    require_admin_mfa,
    require_roles,
)
from password_detective.modules.auth.reauthentication import issue_reauthentication_grant
from password_detective.modules.auth.schemas import (
    BrowserTokenResponse,
    LoginRequest,
    MessageResponse,
    TotpCodeRequest,
    TotpSetupResponse,
)
from password_detective.modules.auth.service import (
    login_user,
    revoke_by_refresh_token,
    revoke_session_family,
    rotate_refresh_token,
)
from password_detective.modules.auth.totp import begin_totp_setup, confirm_totp_setup, disable_totp

router = APIRouter(prefix="/admin", tags=["管理端"])


def require_user_governance_admin(
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> Principal:
    if principal.user.role != UserRole.ADMIN:
        raise AppError("auth.forbidden", "用户治理仅允许管理员访问", status_code=403)
    return principal


@router.post(
    "/auth/login",
    response_model=BrowserTokenResponse,
    dependencies=[Depends(rate_limit("admin.auth.login", limit=10, window_seconds=60))],
)
def admin_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BrowserTokenResponse:
    enforce_browser_origin(request, settings)
    context = get_client_context(request)
    tokens = login_user(db, settings, payload, context)
    if tokens.user.role not in {UserRole.MODERATOR, UserRole.ADMIN}:
        session = db.scalar(
            select(UserSession).where(
                UserSession.refresh_token_hash == hash_refresh_token(tokens.refresh_token)
            )
        )
        if session is not None:
            revoke_session_family(
                db,
                user_id=tokens.user.id,
                family_id=session.family_id,
                reason="admin_role_rejected",
                context=context,
            )
        raise AppError("auth.forbidden", "该账号没有管理端访问权限", status_code=403)
    set_refresh_cookie(response, settings, client="admin", refresh_token=tokens.refresh_token)
    return BrowserTokenResponse.from_token_response(tokens)


@router.post(
    "/auth/refresh",
    response_model=BrowserTokenResponse,
    dependencies=[Depends(rate_limit("admin.auth.refresh", limit=30, window_seconds=60))],
)
def admin_refresh(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BrowserTokenResponse:
    enforce_browser_origin(request, settings)
    refresh_token = require_refresh_cookie(request, client="admin")
    tokens = rotate_refresh_token(db, settings, refresh_token, get_client_context(request))
    set_refresh_cookie(response, settings, client="admin", refresh_token=tokens.refresh_token)
    return BrowserTokenResponse.from_token_response(tokens)


@router.post("/auth/logout", response_model=MessageResponse)
def admin_logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    enforce_browser_origin(request, settings)
    refresh_token = request.cookies.get("pd_admin_refresh")
    if refresh_token:
        revoke_by_refresh_token(
            db,
            refresh_token=refresh_token,
            reason="admin_logout",
            context=get_client_context(request),
        )
    clear_refresh_cookie(response, settings, client="admin")
    return MessageResponse(message="已退出管理端")


@router.get("/access-check")
def access_check(
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> dict[str, str]:
    return {"status": "authorized", "role": principal.user.role.value, "mfa": "verified"}


@router.post(
    "/auth/reauthenticate",
    response_model=AdminReauthenticationResponse,
    dependencies=[Depends(rate_limit("admin.auth.reauthenticate", limit=10, window_seconds=3600))],
)
def admin_reauthenticate(
    payload: AdminReauthenticationRequest,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(require_user_governance_admin)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminReauthenticationResponse:
    response.headers["Cache-Control"] = "no-store"
    issued = issue_reauthentication_grant(
        db,
        settings,
        user=principal.user,
        session_family_id=principal.session_family_id,
        purpose=ReauthenticationPurpose.ADMIN_USER_GOVERNANCE,
        current_password=payload.current_password,
        totp_code=payload.totp_code,
        context=get_client_context(request),
    )
    return AdminReauthenticationResponse.model_validate(issued.model_dump())


@router.get("/dashboard/summary", response_model=AdminDashboardSummary)
def dashboard_summary(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_mfa)],
    window_hours: Annotated[int, Query(ge=1, le=720)] = 24,
) -> AdminDashboardSummary:
    return get_dashboard_summary(db, window_hours=window_hours)


def admin_user_filters(
    status: UserStatus | None = None,
    role: UserRole | None = None,
    query: Annotated[str | None, Query(max_length=128)] = None,
) -> AdminUserFilters:
    return AdminUserFilters(status=status, role=role, query=query)


@router.get("/users", response_model=AdminUserListResponse)
def admin_user_list(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_user_governance_admin)],
    filters: Annotated[AdminUserFilters, Depends(admin_user_filters)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminUserListResponse:
    return list_admin_users(db, filters=filters, page=page, page_size=page_size)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def admin_user_detail(
    user_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_user_governance_admin)],
) -> AdminUserDetail:
    return get_admin_user(db, user_id)


@router.patch(
    "/users/{user_id}/status",
    response_model=AdminUserStatusChangeResponse,
    dependencies=[Depends(rate_limit("admin.users.status", limit=30, window_seconds=60))],
)
def admin_user_status_change(
    user_id: str,
    payload: AdminUserStatusChangeRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_user_governance_admin)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AdminUserStatusChangeResponse:
    request_hash = payload_digest(
        {
            "user_id": user_id,
            "expected_status": payload.expected_status.value,
            "status": payload.status.value,
            "reason_code": payload.reason_code.value,
        }
    )
    lease = acquire_idempotency(
        db,
        scope="admin.users.status",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    if lease.cached_response is not None:
        response.status_code = lease.cached_status or status.HTTP_200_OK
        return AdminUserStatusChangeResponse.model_validate(lease.cached_response)
    try:
        result = change_admin_user_status(
            db,
            user_id=user_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_200_OK,
            response_body=result.model_dump(mode="json"),
        )
        return result
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@router.post(
    "/users/{user_id}/sessions/revoke",
    response_model=AdminUserSessionRevocationResponse,
    dependencies=[Depends(rate_limit("admin.users.sessions.revoke", limit=30, window_seconds=60))],
)
def admin_user_sessions_revoke(
    user_id: str,
    payload: AdminUserSessionRevocationRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_user_governance_admin)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AdminUserSessionRevocationResponse:
    request_hash = payload_digest(
        {
            "user_id": user_id,
            "expected_active_session_count": payload.expected_active_session_count,
            "reason_code": payload.reason_code.value,
        }
    )
    lease = acquire_idempotency(
        db,
        scope="admin.users.sessions.revoke",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    if lease.cached_response is not None:
        response.status_code = lease.cached_status or status.HTTP_200_OK
        return AdminUserSessionRevocationResponse.model_validate(lease.cached_response)
    try:
        result = revoke_admin_user_sessions(
            db,
            user_id=user_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_200_OK,
            response_body=result.model_dump(mode="json"),
        )
        return result
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


def audit_log_filters(
    action: Annotated[str | None, Query(max_length=100)] = None,
    result: Annotated[str | None, Query(max_length=32)] = None,
    target_type: Annotated[str | None, Query(max_length=64)] = None,
    actor_id: Annotated[str | None, Query(max_length=36)] = None,
    request_id: Annotated[str | None, Query(max_length=128)] = None,
    query: Annotated[str | None, Query(max_length=128)] = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AdminAuditLogFilters:
    return AdminAuditLogFilters(
        action=action,
        result=result,
        target_type=target_type,
        actor_id=actor_id,
        request_id=request_id,
        query=query,
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/audit-logs", response_model=AdminAuditLogListResponse)
def audit_log_list(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_mfa)],
    filters: Annotated[AdminAuditLogFilters, Depends(audit_log_filters)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminAuditLogListResponse:
    return list_admin_audit_logs(db, filters=filters, page=page, page_size=page_size)


@router.get(
    "/audit-logs/export",
    dependencies=[Depends(rate_limit("admin.audit.export", limit=10, window_seconds=60))],
)
def audit_log_export(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    filters: Annotated[AdminAuditLogFilters, Depends(audit_log_filters)],
) -> Response:
    content, row_count = export_admin_audit_logs(
        db,
        filters=filters,
        principal=principal,
        context=get_client_context(request),
    )
    filename = f"audit-logs-{utc_now().strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Exported-Rows": str(row_count),
        },
    )


@router.get("/audit-logs/{audit_id}", response_model=AdminAuditLogEntry)
def audit_log_detail(
    audit_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_mfa)],
) -> AdminAuditLogEntry:
    return get_admin_audit_log(db, audit_id)


@router.post("/totp/setup", response_model=TotpSetupResponse)
def setup_totp(
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN)),
    ],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TotpSetupResponse:
    return begin_totp_setup(
        db,
        settings,
        user=principal.user,
        context=get_client_context(request),
    )


@router.post("/totp/confirm", response_model=MessageResponse)
def confirm_totp(
    payload: TotpCodeRequest,
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN)),
    ],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    confirm_totp_setup(
        db,
        settings,
        user=principal.user,
        session_family_id=principal.session_family_id,
        code=payload.code,
        context=get_client_context(request),
    )
    return MessageResponse(message="TOTP 已启用，请重新登录以进入管理端")


@router.post("/totp/disable", response_model=MessageResponse)
def remove_totp(
    payload: TotpCodeRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    disable_totp(
        db,
        settings,
        user=principal.user,
        code=payload.code,
        context=get_client_context(request),
    )
    return MessageResponse(message="TOTP 已停用")
