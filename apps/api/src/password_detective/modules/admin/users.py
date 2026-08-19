from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.security import hash_account_password
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.privacy_request import (
    PrivacyDeletionRequest,
    PrivacyDeletionStatus,
    PrivacyExport,
    PrivacyExportStatus,
)
from password_detective.db.models.reauthentication_grant import ReauthenticationPurpose
from password_detective.db.models.reputation_event import ReputationEvent
from password_detective.db.models.submission import Submission
from password_detective.db.models.trust_case import TrustCase
from password_detective.db.models.user import User, UserRole, UserStatus
from password_detective.db.models.user_session import UserSession
from password_detective.modules.admin.user_schemas import (
    AdminUserCreateRequest,
    AdminUserDetail,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserProfileUpdateRequest,
    AdminUserProfileUpdateResponse,
    AdminUserSessionRevocationRequest,
    AdminUserSessionRevocationResponse,
    AdminUserStatusChangeRequest,
    AdminUserStatusChangeResponse,
    AdminUserStatusReasonCode,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.auth.reauthentication import consume_reauthentication_grant
from password_detective.modules.reputation.levels import get_user_level_profile


@dataclass(frozen=True, slots=True)
class AdminUserFilters:
    status: UserStatus | None = None
    role: UserRole | None = None
    query: str | None = None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _conditions(filters: AdminUserFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.status is not None:
        conditions.append(User.status == filters.status)
    if filters.role is not None:
        conditions.append(User.role == filters.role)
    query = filters.query.strip() if filters.query else ""
    if query:
        pattern = f"%{_escape_like(query)}%"
        conditions.append(
            or_(
                User.id.ilike(pattern, escape="\\"),
                User.username.ilike(pattern, escape="\\"),
                User.email.ilike(pattern, escape="\\"),
            )
        )
    return conditions


def _mask_email(email: str) -> str:
    local, separator, domain = email.partition("@")
    if not separator:
        return "***"
    domain_name, dot, suffix = domain.partition(".")
    masked_local = f"{local[:1]}***" if local else "***"
    masked_domain = f"{domain_name[:1]}***" if domain_name else "***"
    if dot:
        return f"{masked_local}@{masked_domain}{dot}{suffix}"
    return f"{masked_local}@{masked_domain}"


def _list_item(
    user: User,
    *,
    active_session_count: int = 0,
    last_active_at: datetime | None = None,
) -> AdminUserListItem:
    return AdminUserListItem(
        id=user.id,
        uid=user.id,
        username=user.username,
        masked_email=_mask_email(user.email),
        email_verified=user.email_verified,
        status=user.status,
        role=user.role,
        reputation_score=user.reputation_score,
        totp_enabled=user.totp_enabled,
        active_session_count=active_session_count,
        last_active_at=last_active_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def create_admin_user(
    db: Session,
    *,
    payload: AdminUserCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> AdminUserListItem:
    username = payload.username.strip().lower()
    email = str(payload.email).strip().lower()
    existing = db.scalar(select(User.id).where(or_(User.username == username, User.email == email)))
    if existing:
        raise AppError("admin.user_conflict", "用户名或邮箱已被使用", status_code=409)

    now = utc_now()
    user = User(
        username=username,
        email=email,
        email_verified_at=now if payload.email_verified else None,
        account_password_hash=hash_account_password(payload.password),
        role=payload.role,
        status=payload.status,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("admin.user_conflict", "用户名或邮箱已被使用", status_code=409) from exc
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.user.created",
        target_type="user",
        target_id=user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "role": user.role.value,
            "status": user.status.value,
            "email_verified": user.email_verified,
        },
    )
    db.commit()
    db.refresh(user)
    return _list_item(user)


def list_admin_users(
    db: Session,
    *,
    filters: AdminUserFilters,
    page: int,
    page_size: int,
) -> AdminUserListResponse:
    conditions = _conditions(filters)
    total = db.scalar(select(func.count()).select_from(User).where(*conditions)) or 0
    users = list(
        db.scalars(
            select(User)
            .where(*conditions)
            .order_by(User.created_at.desc(), User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    if not users:
        return AdminUserListResponse(items=[], page=page, page_size=page_size, total=total)

    now = utc_now()
    session_rows = db.execute(
        select(
            UserSession.user_id,
            func.sum(
                case(
                    (
                        and_(
                            UserSession.revoked_at.is_(None),
                            UserSession.expires_at > now,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("active_session_count"),
            func.max(UserSession.last_used_at).label("last_active_at"),
        )
        .where(UserSession.user_id.in_([user.id for user in users]))
        .group_by(UserSession.user_id)
    ).all()
    sessions_by_user = {
        user_id: (int(active_session_count or 0), last_active_at)
        for user_id, active_session_count, last_active_at in session_rows
    }
    return AdminUserListResponse(
        items=[
            _list_item(
                user,
                active_session_count=sessions_by_user.get(user.id, (0, None))[0],
                last_active_at=sessions_by_user.get(user.id, (0, None))[1],
            )
            for user in users
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


def _count(db: Session, model, *conditions: ColumnElement[bool]) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


def get_admin_user(db: Session, user_id: str) -> AdminUserDetail:
    user = db.get(User, user_id)
    if user is None:
        raise AppError("admin.user_not_found", "用户不存在", status_code=404)

    now = utc_now()
    active_session_count = _count(
        db,
        UserSession,
        UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > now,
    )
    total_session_count = _count(db, UserSession, UserSession.user_id == user.id)
    last_active_at = db.scalar(
        select(func.max(UserSession.last_used_at)).where(UserSession.user_id == user.id)
    )
    points_balance = int(
        db.scalar(
            select(func.coalesce(func.sum(PointsLedger.amount), 0)).where(
                PointsLedger.user_id == user.id,
                PointsLedger.status == PointsLedgerStatus.POSTED,
            )
        )
        or 0
    )
    base = _list_item(
        user,
        active_session_count=active_session_count,
        last_active_at=last_active_at,
    )
    return AdminUserDetail(
        **base.model_dump(),
        level=get_user_level_profile(db, user_id=user.id),
        total_session_count=total_session_count,
        submission_count=_count(db, Submission, Submission.user_id == user.id),
        trust_case_count=_count(db, TrustCase, TrustCase.reporter_id == user.id),
        points_balance=points_balance,
        reputation_event_count=_count(
            db,
            ReputationEvent,
            ReputationEvent.user_id == user.id,
        ),
        pending_privacy_export_count=_count(
            db,
            PrivacyExport,
            PrivacyExport.user_id == user.id,
            PrivacyExport.status.in_(
                [PrivacyExportStatus.PENDING, PrivacyExportStatus.PROCESSING]
            ),
        ),
        pending_deletion_request_count=_count(
            db,
            PrivacyDeletionRequest,
            PrivacyDeletionRequest.user_id == user.id,
            PrivacyDeletionRequest.status.in_(
                [PrivacyDeletionStatus.PENDING, PrivacyDeletionStatus.PROCESSING]
            ),
        ),
    )

_PROTECTED_GOVERNANCE_ROLES = {UserRole.ADMIN, UserRole.SERVICE}
_DISABLE_REASON_CODES = {
    AdminUserStatusReasonCode.SECURITY_RISK,
    AdminUserStatusReasonCode.ABUSE_CONFIRMED,
    AdminUserStatusReasonCode.POLICY_VIOLATION,
    AdminUserStatusReasonCode.MANUAL_REVIEW,
}
_ENABLE_REASON_CODES = {
    AdminUserStatusReasonCode.APPEAL_APPROVED,
    AdminUserStatusReasonCode.MANUAL_REVIEW,
}


def _locked_governance_target(db: Session, *, user_id: str, actor_id: str) -> User:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise AppError("admin.user_not_found", "用户不存在", status_code=404)
    if user.id == actor_id:
        raise AppError(
            "admin.user_self_governance_forbidden",
            "不能对当前管理员账号执行该治理操作",
            status_code=403,
        )
    if user.role in _PROTECTED_GOVERNANCE_ROLES:
        raise AppError(
            "admin.user_protected_role",
            "管理员和服务账号暂不允许通过该入口变更",
            status_code=403,
        )
    return user


def _consume_admin_governance_grant(
    db: Session,
    *,
    payload_token: str,
    principal: Principal,
) -> None:
    grant = consume_reauthentication_grant(
        db,
        raw_token=payload_token,
        user_id=principal.user.id,
        session_family_id=principal.session_family_id,
        expected_purpose=ReauthenticationPurpose.ADMIN_USER_GOVERNANCE,
    )
    if principal.user.totp_enabled and not grant.mfa_verified:
        raise AppError(
            "auth.mfa_reauthentication_required",
            "该管理员已启用 TOTP，危险操作需要完成验证码再认证",
            status_code=403,
        )


def _validate_status_reason(payload: AdminUserStatusChangeRequest) -> None:
    allowed = (
        _DISABLE_REASON_CODES
        if payload.status == UserStatus.DISABLED
        else _ENABLE_REASON_CODES
    )
    if payload.reason_code not in allowed:
        raise AppError(
            "admin.user_invalid_status_reason",
            "原因码与目标账号状态不匹配",
            status_code=400,
        )


def update_admin_user_profile(
    db: Session,
    *,
    user_id: str,
    payload: AdminUserProfileUpdateRequest,
    principal: Principal,
    context: ClientContext,
) -> AdminUserProfileUpdateResponse:
    user = _locked_governance_target(db, user_id=user_id, actor_id=principal.user.id)
    if _aware(user.updated_at) != _aware(payload.expected_updated_at):
        raise AppError(
            "admin.user_profile_conflict",
            "用户资料已发生变化，请刷新后重试",
            status_code=409,
            details={"current_updated_at": user.updated_at.isoformat()},
        )

    normalized_email = str(payload.email).strip().lower() if payload.email is not None else None
    email_changed = normalized_email is not None and normalized_email != user.email
    if email_changed:
        existing = db.scalar(
            select(User.id).where(User.email == normalized_email, User.id != user.id)
        )
        if existing:
            raise AppError("admin.user_conflict", "邮箱已被其他账号使用", status_code=409)

    next_verified = payload.email_verified
    if email_changed and next_verified is None:
        next_verified = False
    verification_changed = (
        next_verified is not None and next_verified != user.email_verified
    )
    if not email_changed and not verification_changed:
        raise AppError(
            "admin.user_profile_unchanged",
            "提交的用户资料没有变化",
            status_code=409,
        )

    _consume_admin_governance_grant(
        db,
        payload_token=payload.reauth_token,
        principal=principal,
    )
    changed_fields: list[str] = []
    if email_changed and normalized_email is not None:
        user.email = normalized_email
        changed_fields.append("email")
    if next_verified is not None:
        user.email_verified_at = utc_now() if next_verified else None
        changed_fields.append("email_verified")
    db.flush()
    audit = write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.user.profile_updated",
        target_type="user",
        target_id=user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "changed_fields": changed_fields,
            "reason_code": payload.reason_code.value,
        },
    )
    db.flush()
    return AdminUserProfileUpdateResponse(
        user_id=user.id,
        masked_email=_mask_email(user.email),
        email_verified=user.email_verified,
        updated_at=user.updated_at,
        audit_id=audit.id,
        request_id=context.request_id,
    )


def change_admin_user_status(
    db: Session,
    *,
    user_id: str,
    payload: AdminUserStatusChangeRequest,
    principal: Principal,
    context: ClientContext,
) -> AdminUserStatusChangeResponse:
    _validate_status_reason(payload)
    user = _locked_governance_target(db, user_id=user_id, actor_id=principal.user.id)
    if user.status != payload.expected_status:
        raise AppError(
            "admin.user_status_conflict",
            "账号状态已发生变化，请刷新后重试",
            status_code=409,
            details={"current_status": user.status.value},
        )
    if user.status == payload.status:
        raise AppError(
            "admin.user_status_unchanged",
            "账号已经处于目标状态",
            status_code=409,
        )

    _consume_admin_governance_grant(
        db,
        payload_token=payload.reauth_token,
        principal=principal,
    )
    previous_status = user.status
    user.status = payload.status
    revoked_session_count = 0
    if payload.status == UserStatus.DISABLED:
        now = utc_now()
        result = db.execute(
            update(UserSession)
            .where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
            .values(revoked_at=now, revoked_reason="admin_user_disabled")
        )
        revoked_session_count = result.rowcount or 0

    audit = write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.user.status_changed",
        target_type="user",
        target_id=user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "previous_status": previous_status.value,
            "current_status": payload.status.value,
            "reason_code": payload.reason_code.value,
            "revoked_session_count": revoked_session_count,
        },
    )
    db.flush()
    return AdminUserStatusChangeResponse(
        user_id=user.id,
        previous_status=previous_status,
        current_status=payload.status,
        revoked_session_count=revoked_session_count,
        audit_id=audit.id,
        request_id=context.request_id,
    )


def revoke_admin_user_sessions(
    db: Session,
    *,
    user_id: str,
    payload: AdminUserSessionRevocationRequest,
    principal: Principal,
    context: ClientContext,
) -> AdminUserSessionRevocationResponse:
    user = _locked_governance_target(db, user_id=user_id, actor_id=principal.user.id)
    now = utc_now()
    active_session_count = _count(
        db,
        UserSession,
        UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > now,
    )
    if active_session_count != payload.expected_active_session_count:
        raise AppError(
            "admin.user_session_conflict",
            "活跃会话数量已发生变化，请刷新后重试",
            status_code=409,
            details={"active_session_count": active_session_count},
        )
    if active_session_count == 0:
        raise AppError(
            "admin.user_no_active_sessions",
            "该账号当前没有可撤销的活跃会话",
            status_code=409,
        )

    _consume_admin_governance_grant(
        db,
        payload_token=payload.reauth_token,
        principal=principal,
    )
    result = db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .values(
            revoked_at=now,
            revoked_reason=f"admin_{payload.reason_code.value}",
        )
    )
    revoked_session_count = result.rowcount or 0
    audit = write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.user.sessions_revoked",
        target_type="user",
        target_id=user.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "reason_code": payload.reason_code.value,
            "revoked_session_count": revoked_session_count,
        },
    )
    db.flush()
    return AdminUserSessionRevocationResponse(
        user_id=user.id,
        revoked_session_count=revoked_session_count,
        audit_id=audit.id,
        request_id=context.request_id,
    )
