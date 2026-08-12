from __future__ import annotations

import json

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.community import (
    CommunityGroup,
    CommunityGroupGovernanceEvent,
    CommunityGroupMembership,
    CommunityGroupMembershipStatus,
    CommunityGroupRole,
    CommunityGroupStatus,
    CommunityGroupVisibility,
    CommunityNotificationKind,
    CommunityNotificationSource,
    CommunityPost,
)
from password_detective.db.models.user import User, UserRole
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.community.activity_service import record_group_joined
from password_detective.modules.community.notification_service import create_notification
from password_detective.modules.community.schemas import (
    CommunityGroupCreateRequest,
    CommunityGroupDetail,
    CommunityGroupListResponse,
    CommunityGroupMember,
    CommunityGroupMemberDecisionRequest,
    CommunityGroupMembershipResponse,
    CommunityGroupSummary,
    CommunityGroupUpdateRequest,
)


def list_groups(db: Session, *, principal: Principal | None) -> CommunityGroupListResponse:
    viewer_id = principal.user.id if principal is not None else None
    conditions = [CommunityGroup.status == CommunityGroupStatus.ACTIVE]
    if viewer_id is None:
        conditions.append(CommunityGroup.visibility != CommunityGroupVisibility.PRIVATE)
    else:
        member_groups = select(CommunityGroupMembership.group_id).where(
            CommunityGroupMembership.user_id == viewer_id,
            CommunityGroupMembership.status == CommunityGroupMembershipStatus.ACTIVE,
        )
        conditions.append(
            or_(
                CommunityGroup.visibility != CommunityGroupVisibility.PRIVATE,
                CommunityGroup.id.in_(member_groups),
            )
        )
    groups = db.scalars(
        select(CommunityGroup)
        .where(*conditions)
        .order_by(CommunityGroup.member_count.desc(), CommunityGroup.created_at.desc())
    ).all()
    memberships = _viewer_memberships(db, viewer_id, [group.id for group in groups])
    return CommunityGroupListResponse(
        items=[_group_summary(group, memberships.get(group.id)) for group in groups]
    )


def get_group(
    db: Session,
    *,
    slug: str,
    principal: Principal | None,
) -> CommunityGroupDetail:
    group = _get_group(db, slug)
    viewer_id = principal.user.id if principal is not None else None
    membership = _get_membership(db, group.id, viewer_id) if viewer_id else None
    _require_group_visible(group, membership, principal)
    return _build_group_detail(db, group, membership, include_member_roster=True)


def create_group(
    db: Session,
    *,
    payload: CommunityGroupCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> CommunityGroupDetail:
    _require_verified(principal)
    existing = db.scalar(select(CommunityGroup.id).where(CommunityGroup.slug == payload.slug))
    if existing is not None:
        raise AppError("community.group_slug_exists", "群组标识已被使用", status_code=409)
    group = CommunityGroup(
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
        visibility=payload.visibility,
        owner_id=principal.user.id,
        status=CommunityGroupStatus.ACTIVE,
        member_count=1,
    )
    db.add(group)
    db.flush()
    membership = CommunityGroupMembership(
        group_id=group.id,
        user_id=principal.user.id,
        role=CommunityGroupRole.OWNER,
        status=CommunityGroupMembershipStatus.ACTIVE,
        decided_by_id=principal.user.id,
        decided_at=utc_now(),
    )
    db.add(membership)
    _event(
        db, group, principal.user.id, "group_created", principal.user.id, None, _group_state(group)
    )
    _audit(
        db,
        context,
        principal,
        "community.group.create",
        group,
        {"visibility": group.visibility.value},
    )
    db.commit()
    return get_group(db, slug=group.slug, principal=principal)


def update_group(
    db: Session,
    *,
    slug: str,
    payload: CommunityGroupUpdateRequest,
    principal: Principal,
    context: ClientContext,
) -> CommunityGroupDetail:
    group = _get_group(db, slug, include_inactive=True)
    membership = _get_membership(db, group.id, principal.user.id)
    if not (_is_owner(membership) or principal.user.role in {UserRole.MODERATOR, UserRole.ADMIN}):
        raise AppError(
            "community.group_owner_required", "只有群主或全站治理人员可以修改群组", status_code=403
        )
    before = _group_state(group)
    group.name = payload.name
    group.description = payload.description
    group.visibility = payload.visibility
    group.status = payload.status
    _event(db, group, principal.user.id, "group_updated", None, before, _group_state(group))
    _audit(
        db,
        context,
        principal,
        "community.group.update",
        group,
        {"before": before, "after": _group_state(group)},
    )
    db.commit()
    return _build_group_detail(
        db,
        group,
        membership,
        include_member_roster=_is_active(membership),
    )


def join_group(db: Session, *, slug: str, principal: Principal) -> CommunityGroupMembershipResponse:
    _require_verified(principal)
    group = _get_group(db, slug)
    if group.visibility == CommunityGroupVisibility.PRIVATE:
        raise AppError(
            "community.group_invitation_required",
            "私密群组仅可由群组治理人员邀请加入",
            status_code=403,
        )
    membership = _get_membership(db, group.id, principal.user.id)
    target_status = (
        CommunityGroupMembershipStatus.ACTIVE
        if group.visibility == CommunityGroupVisibility.PUBLIC
        else CommunityGroupMembershipStatus.PENDING
    )
    if membership is None:
        membership = CommunityGroupMembership(
            group_id=group.id,
            user_id=principal.user.id,
            role=CommunityGroupRole.MEMBER,
            status=target_status,
            decided_at=utc_now()
            if target_status == CommunityGroupMembershipStatus.ACTIVE
            else None,
        )
        db.add(membership)
    elif membership.status == target_status:
        return CommunityGroupMembershipResponse(
            group=_group_summary(group, membership),
            message="已是群组成员"
            if target_status == CommunityGroupMembershipStatus.ACTIVE
            else "加入申请已提交",
        )
    else:
        membership.role = CommunityGroupRole.MEMBER
        membership.status = target_status
        membership.decided_by_id = None
        membership.decided_at = (
            utc_now() if target_status == CommunityGroupMembershipStatus.ACTIVE else None
        )
    db.flush()
    if target_status == CommunityGroupMembershipStatus.PENDING:
        _notify_group_application(db, group, membership, principal.user)
    _event(
        db,
        group,
        principal.user.id,
        "group_joined"
        if target_status == CommunityGroupMembershipStatus.ACTIVE
        else "group_join_requested",
        principal.user.id,
        None,
        {"status": target_status.value},
    )
    _recount_members(db, group)
    if target_status == CommunityGroupMembershipStatus.ACTIVE:
        record_group_joined(db, membership, group)
    db.commit()
    return CommunityGroupMembershipResponse(
        group=_group_summary(group, membership),
        message="已加入群组"
        if target_status == CommunityGroupMembershipStatus.ACTIVE
        else "加入申请已提交",
    )


def leave_group(
    db: Session, *, slug: str, principal: Principal
) -> CommunityGroupMembershipResponse:
    group = _get_group(db, slug, include_inactive=True)
    membership = _get_membership(db, group.id, principal.user.id)
    if membership is None or membership.status not in {
        CommunityGroupMembershipStatus.ACTIVE,
        CommunityGroupMembershipStatus.PENDING,
    }:
        return CommunityGroupMembershipResponse(
            group=_group_summary(group, membership), message="当前未加入该群组"
        )
    if membership.role == CommunityGroupRole.OWNER:
        raise AppError(
            "community.group_owner_transfer_required",
            "群主退出前必须先转让群主身份",
            status_code=409,
        )
    before = _membership_state(membership)
    membership.status = CommunityGroupMembershipStatus.REMOVED
    membership.decided_at = utc_now()
    membership.decided_by_id = principal.user.id
    _event(
        db,
        group,
        principal.user.id,
        "group_left",
        principal.user.id,
        before,
        _membership_state(membership),
    )
    _recount_members(db, group)
    db.commit()
    return CommunityGroupMembershipResponse(
        group=_group_summary(group, membership), message="已退出群组"
    )


def decide_member(
    db: Session,
    *,
    slug: str,
    username: str,
    payload: CommunityGroupMemberDecisionRequest,
    principal: Principal,
    context: ClientContext,
) -> CommunityGroupMembershipResponse:
    group = _get_group(db, slug, include_inactive=True)
    actor_membership = _require_group_governor(db, group, principal)
    target = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if target is None:
        raise AppError("community.group_member_not_found", "目标用户不存在", status_code=404)
    membership = _get_membership(db, group.id, target.id)
    before = _membership_state(membership)
    if payload.decision == "invite":
        if actor_membership.role != CommunityGroupRole.OWNER:
            raise AppError(
                "community.group_owner_required", "只有群主可以邀请成员", status_code=403
            )
        if membership is None:
            membership = CommunityGroupMembership(group_id=group.id, user_id=target.id)
            db.add(membership)
        membership.status = CommunityGroupMembershipStatus.ACTIVE
        membership.role = (
            payload.role if payload.role != CommunityGroupRole.OWNER else CommunityGroupRole.MEMBER
        )
    else:
        if membership is None:
            raise AppError(
                "community.group_membership_not_found", "成员或申请记录不存在", status_code=404
            )
        if (
            payload.decision in {"approve", "reject"}
            and membership.status != CommunityGroupMembershipStatus.PENDING
        ):
            return CommunityGroupMembershipResponse(
                group=_group_summary(group, actor_membership), message="该申请已处理"
            )
        if payload.decision == "approve":
            membership.status = CommunityGroupMembershipStatus.ACTIVE
            membership.role = CommunityGroupRole.MEMBER
        elif payload.decision == "reject":
            membership.status = CommunityGroupMembershipStatus.REJECTED
        else:
            if membership.role == CommunityGroupRole.OWNER:
                raise AppError(
                    "community.group_owner_transfer_required",
                    "不能移除当前群主，请先转让群主身份",
                    status_code=409,
                )
            if (
                actor_membership.role == CommunityGroupRole.MODERATOR
                and membership.role != CommunityGroupRole.MEMBER
            ):
                raise AppError(
                    "community.group_owner_required", "版主不能移除群主或其他版主", status_code=403
                )
            membership.status = CommunityGroupMembershipStatus.REMOVED
    membership.decided_by_id = principal.user.id
    membership.decided_at = utc_now()
    db.flush()
    _notify_group_decision(
        db,
        group,
        membership,
        actor_id=principal.user.id,
        decision=payload.decision,
    )
    _event(
        db,
        group,
        principal.user.id,
        f"member_{payload.decision}",
        target.id,
        before,
        _membership_state(membership),
    )
    _recount_members(db, group)
    became_active = membership.status == CommunityGroupMembershipStatus.ACTIVE and (
        before is None or before.get("status") != CommunityGroupMembershipStatus.ACTIVE.value
    )
    if became_active:
        record_group_joined(db, membership, group)
    _audit(
        db,
        context,
        principal,
        f"community.group.member.{payload.decision}",
        group,
        {"subject_user_id": target.id, "before": before, "after": _membership_state(membership)},
    )
    db.commit()
    return CommunityGroupMembershipResponse(
        group=_group_summary(group, actor_membership), message="群组成员状态已更新"
    )


def change_member_role(
    db: Session,
    *,
    slug: str,
    username: str,
    role: CommunityGroupRole,
    principal: Principal,
    context: ClientContext,
) -> CommunityGroupMembershipResponse:
    group = _get_group(db, slug, include_inactive=True)
    actor = _get_membership(db, group.id, principal.user.id)
    if not _is_owner(actor):
        raise AppError(
            "community.group_owner_required", "只有群主可以调整成员角色", status_code=403
        )
    target = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    membership = _get_membership(db, group.id, target.id) if target is not None else None
    if target is None or not _is_active(membership):
        raise AppError("community.group_member_not_found", "目标成员不存在", status_code=404)
    before = _membership_state(membership)
    if role == CommunityGroupRole.OWNER:
        actor.role = CommunityGroupRole.MODERATOR
        membership.role = CommunityGroupRole.OWNER
        group.owner_id = target.id
    else:
        if membership.role == CommunityGroupRole.OWNER:
            raise AppError(
                "community.group_owner_transfer_required",
                "请先将群主身份转让给其他成员",
                status_code=409,
            )
        membership.role = role
    db.flush()
    _notify_group_role_change(
        db,
        group,
        membership,
        actor_id=principal.user.id,
    )
    _event(
        db,
        group,
        principal.user.id,
        "member_role_changed",
        target.id,
        before,
        _membership_state(membership),
    )
    _audit(
        db,
        context,
        principal,
        "community.group.member.role",
        group,
        {"subject_user_id": target.id, "before": before, "after": _membership_state(membership)},
    )
    db.commit()
    return CommunityGroupMembershipResponse(
        group=_group_summary(group, _get_membership(db, group.id, principal.user.id)),
        message="成员角色已更新",
    )


def _notify_group_application(
    db: Session,
    group: CommunityGroup,
    membership: CommunityGroupMembership,
    applicant: User,
) -> None:
    governor_ids = db.scalars(
        select(CommunityGroupMembership.user_id).where(
            CommunityGroupMembership.group_id == group.id,
            CommunityGroupMembership.status == CommunityGroupMembershipStatus.ACTIVE,
            CommunityGroupMembership.role.in_(
                [CommunityGroupRole.OWNER, CommunityGroupRole.MODERATOR]
            ),
        )
    ).all()
    for recipient_id in governor_ids:
        create_notification(
            db,
            recipient_id=recipient_id,
            actor_id=applicant.id,
            kind=CommunityNotificationKind.GROUP_APPLICATION,
            source_type=CommunityNotificationSource.GROUP,
            source_id=membership.id,
            post_id=None,
            comment_id=None,
            preview=f"{applicant.username} 申请加入群组「{group.name}」",
            refresh_existing=True,
        )


def _notify_group_decision(
    db: Session,
    group: CommunityGroup,
    membership: CommunityGroupMembership,
    *,
    actor_id: str,
    decision: str,
) -> None:
    messages = {
        "approve": f"你加入群组「{group.name}」的申请已通过",
        "reject": f"你加入群组「{group.name}」的申请已拒绝",
        "invite": f"你已被邀请加入群组「{group.name}」",
        "remove": f"你已被移出群组「{group.name}」",
    }
    create_notification(
        db,
        recipient_id=membership.user_id,
        actor_id=actor_id,
        kind=CommunityNotificationKind.GROUP_DECISION,
        source_type=CommunityNotificationSource.GROUP,
        source_id=membership.id,
        post_id=None,
        comment_id=None,
        preview=messages[decision],
        refresh_existing=True,
    )


def _notify_group_role_change(
    db: Session,
    group: CommunityGroup,
    membership: CommunityGroupMembership,
    *,
    actor_id: str,
) -> None:
    role_names = {
        CommunityGroupRole.OWNER: "群主",
        CommunityGroupRole.MODERATOR: "版主",
        CommunityGroupRole.MEMBER: "成员",
    }
    create_notification(
        db,
        recipient_id=membership.user_id,
        actor_id=actor_id,
        kind=CommunityNotificationKind.GROUP_ROLE_CHANGE,
        source_type=CommunityNotificationSource.GROUP,
        source_id=membership.id,
        post_id=None,
        comment_id=None,
        preview=f"你在群组「{group.name}」中的角色已更新为{role_names[membership.role]}",
        refresh_existing=True,
    )


def visible_group_model(db: Session, *, slug: str, principal: Principal | None) -> CommunityGroup:
    group = _get_group(db, slug)
    viewer_id = principal.user.id if principal is not None else None
    membership = _get_membership(db, group.id, viewer_id)
    _require_group_visible(group, membership, principal)
    return group


def can_user_view_post(db: Session, post: CommunityPost | None, user_id: str) -> bool:
    if post is None:
        return False
    if post.group_id is None:
        return True
    group = db.get(CommunityGroup, post.group_id)
    if group is None or group.status != CommunityGroupStatus.ACTIVE:
        return False
    if group.visibility != CommunityGroupVisibility.PRIVATE:
        return True
    return _is_active(_get_membership(db, group.id, user_id))


def post_visibility_condition(viewer_id: str | None):
    visible_groups = select(CommunityGroup.id).where(
        CommunityGroup.status == CommunityGroupStatus.ACTIVE,
        CommunityGroup.visibility != CommunityGroupVisibility.PRIVATE,
    )
    if viewer_id is not None:
        memberships = select(CommunityGroupMembership.group_id).where(
            CommunityGroupMembership.user_id == viewer_id,
            CommunityGroupMembership.status == CommunityGroupMembershipStatus.ACTIVE,
        )
        visible_groups = select(CommunityGroup.id).where(
            CommunityGroup.status == CommunityGroupStatus.ACTIVE,
            or_(
                CommunityGroup.visibility != CommunityGroupVisibility.PRIVATE,
                CommunityGroup.id.in_(memberships),
            ),
        )
    return or_(CommunityPost.group_id.is_(None), CommunityPost.group_id.in_(visible_groups))


def require_post_visible(db: Session, post: CommunityPost, principal: Principal | None) -> None:
    if post.group_id is None:
        return
    group = db.get(CommunityGroup, post.group_id)
    membership = (
        _get_membership(db, group.id, principal.user.id)
        if group is not None and principal is not None
        else None
    )
    if group is None or group.status != CommunityGroupStatus.ACTIVE:
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
    if group.visibility == CommunityGroupVisibility.PRIVATE and not _is_active(membership):
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)


def require_group_post_access(
    db: Session, group_slug: str | None, principal: Principal
) -> CommunityGroup | None:
    if group_slug is None:
        return None
    group = _get_group(db, group_slug)
    membership = _get_membership(db, group.id, principal.user.id)
    if not _is_active(membership):
        raise AppError(
            "community.group_membership_required", "只有群组成员可以在群组内发帖", status_code=403
        )
    return group


def group_slug_for_post(db: Session, group_id: str | None) -> str | None:
    if group_id is None:
        return None
    group = db.get(CommunityGroup, group_id)
    return group.slug if group is not None else None


def increment_group_post_count(db: Session, group_id: str | None, amount: int) -> None:
    if group_id is None:
        return
    group = db.get(CommunityGroup, group_id)
    if group is not None:
        group.post_count = max(0, group.post_count + amount)


def _build_group_detail(
    db: Session,
    group: CommunityGroup,
    membership: CommunityGroupMembership | None,
    *,
    include_member_roster: bool,
) -> CommunityGroupDetail:
    members: list[CommunityGroupMember] = []
    is_governor = _is_active(membership) and membership.role in {
        CommunityGroupRole.OWNER,
        CommunityGroupRole.MODERATOR,
    }
    can_view_roster = include_member_roster and (
        group.visibility != CommunityGroupVisibility.PRIVATE or _is_active(membership)
    )
    if can_view_roster:
        member_conditions = [CommunityGroupMembership.group_id == group.id]
        if not is_governor:
            member_conditions.append(
                CommunityGroupMembership.status == CommunityGroupMembershipStatus.ACTIVE
            )
        rows = db.execute(
            select(CommunityGroupMembership, User)
            .join(User, User.id == CommunityGroupMembership.user_id)
            .where(*member_conditions)
            .order_by(CommunityGroupMembership.role.asc(), User.username.asc())
        ).all()
        members = [
            CommunityGroupMember(username=user.username, role=item.role, status=item.status)
            for item, user in rows
        ]
    owner = db.get(User, group.owner_id)
    if owner is None:
        raise AppError("community.group_owner_missing", "群组所有者不存在", status_code=500)
    return CommunityGroupDetail(
        **_group_summary(group, membership).model_dump(),
        owner_username=owner.username,
        members=members,
    )


def _get_group(db: Session, slug: str, *, include_inactive: bool = False) -> CommunityGroup:
    conditions = [CommunityGroup.slug == slug]
    if not include_inactive:
        conditions.append(CommunityGroup.status == CommunityGroupStatus.ACTIVE)
    group = db.scalar(select(CommunityGroup).where(*conditions))
    if group is None:
        raise AppError("community.group_not_found", "社区群组不存在", status_code=404)
    return group


def _get_membership(
    db: Session, group_id: str, user_id: str | None
) -> CommunityGroupMembership | None:
    if user_id is None:
        return None
    return db.scalar(
        select(CommunityGroupMembership).where(
            CommunityGroupMembership.group_id == group_id,
            CommunityGroupMembership.user_id == user_id,
        )
    )


def _viewer_memberships(
    db: Session, user_id: str | None, group_ids: list[str]
) -> dict[str, CommunityGroupMembership]:
    if user_id is None or not group_ids:
        return {}
    rows = db.scalars(
        select(CommunityGroupMembership).where(
            CommunityGroupMembership.user_id == user_id,
            CommunityGroupMembership.group_id.in_(group_ids),
        )
    ).all()
    return {item.group_id: item for item in rows}


def _require_group_visible(
    group: CommunityGroup, membership: CommunityGroupMembership | None, principal: Principal | None
) -> None:
    privileged = principal is not None and principal.user.role in {
        UserRole.MODERATOR,
        UserRole.ADMIN,
    }
    if group.status != CommunityGroupStatus.ACTIVE and not (_is_active(membership) or privileged):
        raise AppError("community.group_not_found", "社区群组不存在", status_code=404)
    if group.visibility == CommunityGroupVisibility.PRIVATE and not _is_active(membership):
        raise AppError("community.group_not_found", "社区群组不存在", status_code=404)


def _require_group_governor(
    db: Session, group: CommunityGroup, principal: Principal
) -> CommunityGroupMembership:
    membership = _get_membership(db, group.id, principal.user.id)
    if (
        membership is None
        or membership.status != CommunityGroupMembershipStatus.ACTIVE
        or membership.role not in {CommunityGroupRole.OWNER, CommunityGroupRole.MODERATOR}
    ):
        raise AppError(
            "community.group_governor_required", "只有群主或群组版主可以执行该操作", status_code=403
        )
    return membership


def _require_verified(principal: Principal) -> None:
    if not principal.user.email_verified:
        raise AppError(
            "community.email_verification_required", "发布社区内容前必须先验证邮箱", status_code=403
        )


def _is_active(membership: CommunityGroupMembership | None) -> bool:
    return membership is not None and membership.status == CommunityGroupMembershipStatus.ACTIVE


def _is_owner(membership: CommunityGroupMembership | None) -> bool:
    return _is_active(membership) and membership.role == CommunityGroupRole.OWNER


def _recount_members(db: Session, group: CommunityGroup) -> None:
    db.flush()
    group.member_count = (
        db.scalar(
            select(func.count(CommunityGroupMembership.id)).where(
                CommunityGroupMembership.group_id == group.id,
                CommunityGroupMembership.status == CommunityGroupMembershipStatus.ACTIVE,
            )
        )
        or 0
    )


def _group_summary(
    group: CommunityGroup, membership: CommunityGroupMembership | None
) -> CommunityGroupSummary:
    return CommunityGroupSummary(
        slug=group.slug,
        name=group.name,
        description=group.description,
        visibility=group.visibility,
        status=group.status,
        member_count=group.member_count,
        post_count=group.post_count,
        viewer_role=membership.role if membership else None,
        viewer_membership_status=membership.status if membership else None,
    )


def _group_state(group: CommunityGroup) -> dict[str, object]:
    return {"name": group.name, "visibility": group.visibility.value, "status": group.status.value}


def _membership_state(membership: CommunityGroupMembership | None) -> dict[str, object] | None:
    return (
        None
        if membership is None
        else {"role": membership.role.value, "status": membership.status.value}
    )


def _event(
    db: Session,
    group: CommunityGroup,
    actor_id: str,
    action: str,
    subject_user_id: str | None,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> None:
    db.add(
        CommunityGroupGovernanceEvent(
            group_id=group.id,
            actor_id=actor_id,
            subject_user_id=subject_user_id,
            action=action,
            before_state=json.dumps(before, ensure_ascii=False) if before is not None else None,
            after_state=json.dumps(after, ensure_ascii=False) if after is not None else None,
        )
    )


def _audit(
    db: Session,
    context: ClientContext,
    principal: Principal,
    action: str,
    group: CommunityGroup,
    details: dict[str, object],
) -> None:
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action=action,
        target_type="community_group",
        target_id=group.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details=details,
    )
