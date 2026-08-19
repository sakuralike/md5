from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.community import (
    CommunityContentStatus,
    CommunityGroupMembership,
    CommunityGroupMembershipStatus,
    CommunityGroupRole,
    CommunityPost,
)
from password_detective.db.models.user import UserRole
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.community.schemas import (
    CommunityPostDetail,
    CommunityPostSeoUpdateRequest,
)
from password_detective.modules.community.service import _require_version, get_post


def update_post_seo(
    db: Session,
    *,
    post_id: str,
    payload: CommunityPostSeoUpdateRequest,
    principal: Principal,
    context: ClientContext,
) -> CommunityPostDetail:
    post = db.scalar(
        select(CommunityPost).where(
            CommunityPost.id == post_id,
            CommunityPost.status == CommunityContentStatus.PUBLISHED,
        )
    )
    if post is None:
        raise AppError("community.post_not_found", "社区主题不存在", status_code=404)
    _require_post_seo_editor(db, post, principal)
    _require_version(post.seo_version, payload.expected_seo_version)

    fields = payload.model_fields_set
    if "seo_title" in fields:
        post.seo_title = payload.seo_title
    if "seo_description" in fields:
        post.seo_description = payload.seo_description
    if "seo_keywords" in fields:
        post.seo_keywords = payload.seo_keywords
    if "seo_canonical_path" in fields:
        post.seo_canonical_path = payload.seo_canonical_path
    if "og_image_url" in fields:
        post.og_image_url = payload.og_image_url
    post.seo_version += 1
    post.updated_at = utc_now()
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.post.seo.update",
        target_type="community_post",
        target_id=post.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "updated_fields": sorted(fields - {"expected_seo_version"}),
            "previous_seo_version": payload.expected_seo_version,
            "current_seo_version": post.seo_version,
        },
    )
    db.commit()
    return get_post(db, post.id, principal=principal)


def _require_post_seo_editor(db: Session, post: CommunityPost, principal: Principal) -> None:
    if post.author_id == principal.user.id:
        return
    if principal.user.role in {UserRole.MODERATOR, UserRole.ADMIN}:
        return
    if post.group_id is not None:
        membership = db.scalar(
            select(CommunityGroupMembership).where(
                CommunityGroupMembership.group_id == post.group_id,
                CommunityGroupMembership.user_id == principal.user.id,
                CommunityGroupMembership.status == CommunityGroupMembershipStatus.ACTIVE,
            )
        )
        if membership is not None and membership.role in {
            CommunityGroupRole.OWNER,
            CommunityGroupRole.MODERATOR,
        }:
            return
    raise AppError("community.post_seo_forbidden", "没有修改该主题 SEO 设置的权限", status_code=403)
