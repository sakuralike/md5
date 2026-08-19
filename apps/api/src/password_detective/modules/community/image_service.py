from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.community import CommunityContentStatus, CommunityPost
from password_detective.db.models.community_image import (
    CommunityImageStatus,
    CommunityPostImage,
)
from password_detective.db.models.system_setting import SystemSetting
from password_detective.db.models.user import User
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.community.admin_schemas import (
    AdminCommunityPostImageListResponse,
    AdminCommunityPostImageSummary,
)
from password_detective.modules.community.group_service import require_post_visible
from password_detective.modules.community.image_assets import (
    StoredCommunityPostImage,
    resolve_community_post_image,
)
from password_detective.modules.community.schemas import (
    CommunityImageUploadConfig,
    CommunityPostImageResponse,
)

COMMUNITY_IMAGE_UPLOAD_SETTING_KEY = "community_image_upload"


def get_community_image_upload_config(db: Session) -> CommunityImageUploadConfig:
    record = db.get(SystemSetting, COMMUNITY_IMAGE_UPLOAD_SETTING_KEY)
    raw_value = record.value_json.get("value") if record else None
    try:
        return CommunityImageUploadConfig.model_validate(raw_value or {})
    except (TypeError, ValueError):
        return CommunityImageUploadConfig()


def save_community_image_upload_config(
    db: Session,
    *,
    payload: CommunityImageUploadConfig,
    principal: Principal,
    context: ClientContext,
) -> CommunityImageUploadConfig:
    previous = get_community_image_upload_config(db)
    record = db.get(SystemSetting, COMMUNITY_IMAGE_UPLOAD_SETTING_KEY)
    value_json = {"value": payload.model_dump(mode="json")}
    if record is None:
        db.add(SystemSetting(key=COMMUNITY_IMAGE_UPLOAD_SETTING_KEY, value_json=value_json))
    else:
        record.value_json = value_json
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.image_upload_config.update",
        target_type="community_image_upload_config",
        target_id=COMMUNITY_IMAGE_UPLOAD_SETTING_KEY,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "previous": previous.model_dump(mode="json"),
            "current": payload.model_dump(mode="json"),
        },
    )
    db.commit()
    return payload


def create_community_post_image(
    db: Session,
    *,
    stored: StoredCommunityPostImage,
    principal: Principal,
    context: ClientContext,
) -> CommunityPostImageResponse:
    if not principal.user.email_verified:
        raise AppError(
            "community.email_verification_required",
            "完成邮箱验证后才能上传主题图片",
            status_code=403,
        )
    image = CommunityPostImage(
        owner_id=principal.user.id,
        sha256=stored.sha256,
        asset_name=stored.asset_name,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        width=stored.width,
        height=stored.height,
    )
    db.add(image)
    db.flush()
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="community.post_image.upload",
        target_type="community_post_image",
        target_id=image.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "content_type": image.content_type,
            "size_bytes": image.size_bytes,
            "width": image.width,
            "height": image.height,
        },
    )
    db.commit()
    db.refresh(image)
    return _image_response(image)


def attach_community_post_images(
    db: Session,
    *,
    attachment_ids: list[str],
    post: CommunityPost,
    principal: Principal,
) -> None:
    if not attachment_ids:
        return
    if post.group_id is not None:
        raise AppError(
            "community.group_image_attachments_unsupported",
            "群组主题暂不支持图片附件",
            status_code=422,
        )
    config = get_community_image_upload_config(db)
    if len(attachment_ids) > config.max_per_post:
        raise AppError(
            "community.image_attachment_limit",
            "主题图片数量超过配置限制",
            status_code=422,
            details={"max_per_post": config.max_per_post},
        )
    images = list(
        db.scalars(
            select(CommunityPostImage)
            .where(
                CommunityPostImage.id.in_(attachment_ids),
                CommunityPostImage.owner_id == principal.user.id,
                CommunityPostImage.status == CommunityImageStatus.UPLOADED,
                CommunityPostImage.post_id.is_(None),
            )
            .with_for_update()
        )
    )
    if len(images) != len(attachment_ids):
        raise AppError(
            "community.image_attachment_invalid",
            "主题图片不存在、已被使用或不属于当前账号",
            status_code=422,
        )
    now = utc_now()
    for image in images:
        image.post_id = post.id
        image.status = CommunityImageStatus.ATTACHED
        image.attached_at = now


def list_post_images(db: Session, post: CommunityPost) -> list[CommunityPostImageResponse]:
    if post.deleted_by_author_at is not None:
        return []
    images = db.scalars(
        select(CommunityPostImage)
        .where(
            CommunityPostImage.post_id == post.id,
            CommunityPostImage.status == CommunityImageStatus.ATTACHED,
        )
        .order_by(CommunityPostImage.created_at, CommunityPostImage.id)
    ).all()
    return [_image_response(image) for image in images]


def resolve_authorized_post_image(
    db: Session,
    settings: Settings,
    *,
    image_id: str,
    principal: Principal | None,
) -> tuple[Path, str]:
    image = db.get(CommunityPostImage, image_id)
    if image is None or image.status == CommunityImageStatus.REMOVED:
        raise AppError("community.image_not_found", "主题图片不存在", status_code=404)
    if image.status == CommunityImageStatus.UPLOADED:
        if principal is None or image.owner_id != principal.user.id:
            raise AppError("community.image_not_found", "主题图片不存在", status_code=404)
    else:
        post = db.get(CommunityPost, image.post_id)
        if (
            post is None
            or post.status != CommunityContentStatus.PUBLISHED
            or post.deleted_by_author_at is not None
        ):
            raise AppError("community.image_not_found", "主题图片不存在", status_code=404)
        require_post_visible(db, post, principal)
    return resolve_community_post_image(settings, image.asset_name)


def remove_community_post_image(
    db: Session,
    *,
    image_id: str,
    principal: Principal,
    context: ClientContext,
) -> CommunityPostImageResponse:
    image = db.scalar(
        select(CommunityPostImage)
        .where(CommunityPostImage.id == image_id)
        .with_for_update()
    )
    if image is None:
        raise AppError("community.image_not_found", "主题图片不存在", status_code=404)
    if image.status != CommunityImageStatus.REMOVED:
        image.status = CommunityImageStatus.REMOVED
        image.removed_at = utc_now()
        write_audit_log(
            db,
            actor_id=principal.user.id,
            action="community.post_image.remove",
            target_type="community_post_image",
            target_id=image.id,
            result="success",
            ip_prefix=context.ip_prefix,
            request_id=context.request_id,
            details={"post_id": image.post_id},
        )
        db.commit()
        db.refresh(image)
    return _image_response(image)


def list_admin_community_post_images(
    db: Session,
    *,
    status: CommunityImageStatus | None,
    page: int,
    page_size: int,
) -> AdminCommunityPostImageListResponse:
    filters = []
    if status is not None:
        filters.append(CommunityPostImage.status == status)
    total = db.scalar(select(func.count(CommunityPostImage.id)).where(*filters)) or 0
    rows = db.execute(
        select(CommunityPostImage, User.username, CommunityPost.title)
        .join(User, User.id == CommunityPostImage.owner_id)
        .outerjoin(CommunityPost, CommunityPost.id == CommunityPostImage.post_id)
        .where(*filters)
        .order_by(CommunityPostImage.created_at.desc(), CommunityPostImage.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AdminCommunityPostImageListResponse(
        items=[
            AdminCommunityPostImageSummary(
                id=image.id,
                owner_username=username,
                post_id=image.post_id,
                post_title=post_title,
                status=image.status,
                content_type=image.content_type,
                size_bytes=image.size_bytes,
                width=image.width,
                height=image.height,
                created_at=image.created_at,
                attached_at=image.attached_at,
                removed_at=image.removed_at,
            )
            for image, username, post_title in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


def _image_response(image: CommunityPostImage) -> CommunityPostImageResponse:
    return CommunityPostImageResponse(
        id=image.id,
        url=f"/api/v1/community/images/{image.id}/content",
        content_type=image.content_type,
        size_bytes=image.size_bytes,
        width=image.width,
        height=image.height,
    )
