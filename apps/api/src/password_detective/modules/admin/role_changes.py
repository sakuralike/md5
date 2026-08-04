from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.reauthentication_grant import ReauthenticationPurpose
from password_detective.db.models.role_change_request import (
    RoleChangeRequest,
    RoleChangeRequestStatus,
)
from password_detective.db.models.user import User, UserRole, UserStatus
from password_detective.db.models.user_session import UserSession
from password_detective.modules.admin.role_change_schemas import (
    RoleChangeCreateRequest,
    RoleChangeMutationResponse,
    RoleChangeRequestListResponse,
    RoleChangeRequestResponse,
    RoleChangeReviewRequest,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.auth.reauthentication import consume_reauthentication_grant

_ALLOWED_TRANSITIONS = {
    (UserRole.USER, UserRole.TRUSTED_CONTRIBUTOR),
    (UserRole.TRUSTED_CONTRIBUTOR, UserRole.USER),
    (UserRole.TRUSTED_CONTRIBUTOR, UserRole.MODERATOR),
    (UserRole.MODERATOR, UserRole.TRUSTED_CONTRIBUTOR),
    (UserRole.MODERATOR, UserRole.USER),
}


def _response(record: RoleChangeRequest) -> RoleChangeRequestResponse:
    return RoleChangeRequestResponse.model_validate(record, from_attributes=True)


def _consume_governance_grant(db: Session, token: str, principal: Principal) -> None:
    grant = consume_reauthentication_grant(
        db,
        raw_token=token,
        user_id=principal.user.id,
        session_family_id=principal.session_family_id,
        expected_purpose=ReauthenticationPurpose.ADMIN_USER_GOVERNANCE,
    )
    if not grant.mfa_verified:
        raise AppError(
            "auth.mfa_reauthentication_required",
            "角色治理需要完成 TOTP 再认证",
            status_code=403,
        )


def list_role_change_requests(
    db: Session,
    *,
    status: RoleChangeRequestStatus | None,
    page: int,
    page_size: int,
) -> RoleChangeRequestListResponse:
    filters = [RoleChangeRequest.status == status] if status else []
    total = db.scalar(select(func.count(RoleChangeRequest.id)).where(*filters)) or 0
    records = db.scalars(
        select(RoleChangeRequest)
        .where(*filters)
        .order_by(RoleChangeRequest.created_at.desc(), RoleChangeRequest.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return RoleChangeRequestListResponse(
        items=[_response(record) for record in records],
        page=page,
        page_size=page_size,
        total=total,
    )


def create_role_change_request(
    db: Session,
    *,
    user_id: str,
    payload: RoleChangeCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> RoleChangeMutationResponse:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise AppError("admin.user_not_found", "用户不存在", status_code=404)
    if user.id == principal.user.id or user.role in {UserRole.ADMIN, UserRole.SERVICE}:
        raise AppError(
            "admin.role_change_target_protected", "该账号不允许变更角色", status_code=403
        )
    if user.status != UserStatus.ACTIVE:
        raise AppError(
            "admin.role_change_target_inactive", "仅正常账号可以变更角色", status_code=409
        )
    if user.role != payload.expected_role:
        raise AppError(
            "admin.role_change_conflict",
            "目标账号角色已发生变化",
            status_code=409,
            details={"current_role": user.role.value},
        )
    if (payload.expected_role, payload.requested_role) not in _ALLOWED_TRANSITIONS:
        raise AppError(
            "admin.role_change_transition_forbidden", "不允许该角色转换", status_code=400
        )
    pending = db.scalar(
        select(RoleChangeRequest.id).where(
            RoleChangeRequest.target_user_id == user.id,
            RoleChangeRequest.status == RoleChangeRequestStatus.PENDING,
        )
    )
    if pending:
        raise AppError(
            "admin.role_change_pending_exists", "该账号已有待复核角色变更", status_code=409
        )

    _consume_governance_grant(db, payload.reauth_token, principal)
    record = RoleChangeRequest(
        target_user_id=user.id,
        expected_role=payload.expected_role,
        requested_role=payload.requested_role,
        requested_by=principal.user.id,
        reason_code=payload.reason_code.value,
    )
    db.add(record)
    db.flush()
    audit = write_audit_log(
        db,
        actor_id=principal.user.id,
        action="admin.role_change.requested",
        target_type="role_change_request",
        target_id=record.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "target_user_id": user.id,
            "expected_role": payload.expected_role.value,
            "requested_role": payload.requested_role.value,
            "reason_code": payload.reason_code.value,
        },
    )
    db.flush()
    return RoleChangeMutationResponse(
        request=_response(record),
        revoked_session_count=0,
        audit_id=audit.id,
        request_id=context.request_id,
    )


def review_role_change_request(
    db: Session,
    *,
    request_id: str,
    approve: bool,
    payload: RoleChangeReviewRequest,
    principal: Principal,
    context: ClientContext,
) -> RoleChangeMutationResponse:
    record = db.scalar(
        select(RoleChangeRequest).where(RoleChangeRequest.id == request_id).with_for_update()
    )
    if record is None:
        raise AppError("admin.role_change_request_not_found", "角色变更请求不存在", status_code=404)
    if record.status != payload.expected_status or record.status != RoleChangeRequestStatus.PENDING:
        raise AppError(
            "admin.role_change_review_conflict", "角色变更请求状态已变化", status_code=409
        )
    if record.requested_by == principal.user.id:
        raise AppError(
            "admin.role_change_self_approval_forbidden",
            "申请人与复核人必须是不同管理员",
            status_code=403,
        )

    user = db.scalar(select(User).where(User.id == record.target_user_id).with_for_update())
    if user is None:
        raise AppError("admin.user_not_found", "用户不存在", status_code=404)
    if approve and user.role != record.expected_role:
        raise AppError(
            "admin.role_change_conflict",
            "目标账号角色已发生变化",
            status_code=409,
            details={"current_role": user.role.value},
        )

    _consume_governance_grant(db, payload.reauth_token, principal)
    now = utc_now()
    revoked_session_count = 0
    action = "admin.role_change.rejected"
    if approve:
        user.role = record.requested_role
        result = db.execute(
            update(UserSession)
            .where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
            .values(revoked_at=now, revoked_reason="admin_role_changed")
        )
        revoked_session_count = result.rowcount or 0
        record.status = RoleChangeRequestStatus.APPROVED
        action = "admin.role_change.approved"
    else:
        record.status = RoleChangeRequestStatus.REJECTED
    record.reviewed_by = principal.user.id
    record.review_reason_code = payload.reason_code.value
    record.reviewed_at = now
    audit = write_audit_log(
        db,
        actor_id=principal.user.id,
        action=action,
        target_type="role_change_request",
        target_id=record.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "target_user_id": user.id,
            "expected_role": record.expected_role.value,
            "requested_role": record.requested_role.value,
            "review_reason_code": payload.reason_code.value,
            "revoked_session_count": revoked_session_count,
        },
    )
    db.flush()
    return RoleChangeMutationResponse(
        request=_response(record),
        revoked_session_count=revoked_session_count,
        audit_id=audit.id,
        request_id=context.request_id,
    )
