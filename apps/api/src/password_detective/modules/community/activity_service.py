from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityActivityEvent,
    CommunityActivityFeed,
    CommunityActivityKind,
    CommunityActivityPreference,
    CommunityActivitySource,
    CommunityComment,
    CommunityContentStatus,
    CommunityGroup,
    CommunityGroupMembership,
    CommunityGroupMembershipStatus,
    CommunityGroupStatus,
    CommunityGroupVisibility,
    CommunityPost,
    CommunityUserBlock,
    CommunityUserFollow,
    CommunityUserMute,
)
from password_detective.db.models.user import User, UserStatus
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.community.schemas import (
    CommunityActivityItem,
    CommunityActivityListResponse,
    CommunityActivityPreferenceResponse,
    CommunityActivityPreferenceUpdateRequest,
    CommunityAuthor,
)


def record_post_published(db: Session, post: CommunityPost) -> None:
    group = db.get(CommunityGroup, post.group_id) if post.group_id else None
    db.add(
        CommunityActivityEvent(
            actor_id=post.author_id,
            kind=CommunityActivityKind.POST_PUBLISHED,
            source_type=CommunityActivitySource.POST,
            source_id=post.id,
            post_id=post.id,
            group_id=post.group_id,
            preview=_preview(post.title),
            is_public=group is None or group.visibility != CommunityGroupVisibility.PRIVATE,
        )
    )


def record_comment_published(
    db: Session, comment: CommunityComment, post: CommunityPost
) -> None:
    group = db.get(CommunityGroup, post.group_id) if post.group_id else None
    db.add(
        CommunityActivityEvent(
            actor_id=comment.author_id,
            kind=CommunityActivityKind.COMMENT_PUBLISHED,
            source_type=CommunityActivitySource.COMMENT,
            source_id=comment.id,
            post_id=post.id,
            comment_id=comment.id,
            group_id=post.group_id,
            preview=_preview(comment.content),
            is_public=group is None or group.visibility != CommunityGroupVisibility.PRIVATE,
        )
    )


def record_group_joined(
    db: Session, membership: CommunityGroupMembership, group: CommunityGroup
) -> None:
    preference = db.get(CommunityActivityPreference, membership.user_id)
    if preference is not None and not preference.share_group_joins:
        return
    db.add(
        CommunityActivityEvent(
            actor_id=membership.user_id,
            kind=CommunityActivityKind.GROUP_JOINED,
            source_type=CommunityActivitySource.GROUP_MEMBERSHIP,
            source_id=membership.id,
            group_id=group.id,
            preview=_preview(group.name),
            is_public=group.visibility == CommunityGroupVisibility.PUBLIC,
        )
    )


def record_user_followed(db: Session, follow: CommunityUserFollow) -> None:
    preference = db.get(CommunityActivityPreference, follow.follower_id)
    if preference is not None and not preference.share_follows:
        return
    db.add(
        CommunityActivityEvent(
            actor_id=follow.follower_id,
            kind=CommunityActivityKind.USER_FOLLOWED,
            source_type=CommunityActivitySource.USER_FOLLOW,
            source_id=follow.id,
            target_user_id=follow.followed_id,
            preview="关注了社区用户",
            is_public=True,
        )
    )


def get_activity_preferences(
    db: Session, *, principal: Principal
) -> CommunityActivityPreferenceResponse:
    preference = db.get(CommunityActivityPreference, principal.user.id)
    return CommunityActivityPreferenceResponse(
        share_group_joins=preference.share_group_joins if preference is not None else True,
        share_follows=preference.share_follows if preference is not None else True,
    )


def update_activity_preferences(
    db: Session,
    *,
    payload: CommunityActivityPreferenceUpdateRequest,
    principal: Principal,
) -> CommunityActivityPreferenceResponse:
    preference = db.get(CommunityActivityPreference, principal.user.id)
    if preference is None:
        preference = CommunityActivityPreference(user_id=principal.user.id)
        db.add(preference)
    preference.share_group_joins = payload.share_group_joins
    preference.share_follows = payload.share_follows
    db.commit()
    return get_activity_preferences(db, principal=principal)


def list_activity(
    db: Session,
    *,
    feed: CommunityActivityFeed,
    principal: Principal | None,
    cursor: str | None,
    limit: int,
) -> CommunityActivityListResponse:
    viewer_id = principal.user.id if principal is not None else None
    if feed != CommunityActivityFeed.LATEST and viewer_id is None:
        raise AppError(
            "community.authentication_required", "该动态流需要登录后访问", status_code=401
        )

    conditions = []
    if feed == CommunityActivityFeed.LATEST:
        conditions.append(CommunityActivityEvent.is_public.is_(True))
    elif feed == CommunityActivityFeed.FOLLOWING:
        followed_ids = select(CommunityUserFollow.followed_id).where(
            CommunityUserFollow.follower_id == viewer_id
        )
        conditions.extend(
            [
                CommunityActivityEvent.is_public.is_(True),
                CommunityActivityEvent.actor_id.in_(followed_ids),
            ]
        )
    else:
        group_ids = select(CommunityGroupMembership.group_id).where(
            CommunityGroupMembership.user_id == viewer_id,
            CommunityGroupMembership.status == CommunityGroupMembershipStatus.ACTIVE,
        )
        conditions.append(CommunityActivityEvent.group_id.in_(group_ids))
    if cursor is not None:
        cursor_created_at, cursor_id = _decode_cursor(cursor)
        conditions.append(
            or_(
                CommunityActivityEvent.created_at < cursor_created_at,
                (CommunityActivityEvent.created_at == cursor_created_at)
                & (CommunityActivityEvent.id < cursor_id),
            )
        )

    hidden = _hidden_actor_ids(db, viewer_id)
    candidates = db.scalars(
        select(CommunityActivityEvent)
        .where(*conditions)
        .order_by(CommunityActivityEvent.created_at.desc(), CommunityActivityEvent.id.desc())
        .limit(max((limit + 1) * 8, 80))
    ).all()
    visible = [
        event
        for event in candidates
        if event.actor_id not in hidden and _visible(db, event, viewer_id)
    ]
    has_more = len(visible) > limit
    items = visible[:limit]
    next_cursor = _encode_cursor(items[-1].created_at, items[-1].id) if has_more and items else None
    return build_activity_response(
        db, feed=feed, events=items, next_cursor=next_cursor, has_more=has_more
    )


def build_activity_response(
    db: Session,
    *,
    feed: CommunityActivityFeed,
    events: list[CommunityActivityEvent],
    next_cursor: str | None,
    has_more: bool,
) -> CommunityActivityListResponse:
    user_ids = {event.actor_id for event in events} | {
        event.target_user_id for event in events if event.target_user_id is not None
    }
    users = {
        user.id: user
        for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()
    }
    post_ids = {event.post_id for event in events if event.post_id is not None}
    posts = {
        post.id: post
        for post in db.scalars(
            select(CommunityPost).where(CommunityPost.id.in_(post_ids))
        ).all()
    }
    group_ids = {event.group_id for event in events if event.group_id is not None}
    groups = {
        group.id: group
        for group in db.scalars(
            select(CommunityGroup).where(CommunityGroup.id.in_(group_ids))
        ).all()
    }
    items: list[CommunityActivityItem] = []
    for event in events:
        actor = users[event.actor_id]
        post = posts.get(event.post_id)
        group = groups.get(event.group_id)
        target = users.get(event.target_user_id)
        items.append(
            CommunityActivityItem(
                id=event.id,
                kind=event.kind,
                source_type=event.source_type,
                source_id=event.source_id,
                actor=CommunityAuthor(user_id=actor.id, username=actor.username, role=actor.role),
                preview=event.preview,
                post_id=event.post_id,
                post_title=post.title if post is not None else None,
                comment_id=event.comment_id,
                group_slug=group.slug if group is not None else None,
                group_name=group.name if group is not None else None,
                target_username=target.username if target is not None else None,
                created_at=event.created_at,
            )
        )
    return CommunityActivityListResponse(
        feed=feed, items=items, next_cursor=next_cursor, has_more=has_more
    )


def _visible(db: Session, event: CommunityActivityEvent, viewer_id: str | None) -> bool:
    actor = db.get(User, event.actor_id)
    if actor is None or actor.status != UserStatus.ACTIVE:
        return False
    if event.post_id is not None:
        post = db.get(CommunityPost, event.post_id)
        if post is None or post.status != CommunityContentStatus.PUBLISHED:
            return False
        if event.comment_id is not None:
            comment = db.get(CommunityComment, event.comment_id)
            if comment is None or comment.status != CommunityContentStatus.PUBLISHED:
                return False
        if post.group_id is not None:
            group = db.get(CommunityGroup, post.group_id)
            if group is None or group.status != CommunityGroupStatus.ACTIVE:
                return False
            if group.visibility == CommunityGroupVisibility.PRIVATE:
                if viewer_id is None:
                    return False
                membership = db.scalar(
                    select(CommunityGroupMembership.id).where(
                        CommunityGroupMembership.group_id == group.id,
                        CommunityGroupMembership.user_id == viewer_id,
                        CommunityGroupMembership.status == CommunityGroupMembershipStatus.ACTIVE,
                    )
                )
                if membership is None:
                    return False
    if event.group_id is not None and event.post_id is None:
        group = db.get(CommunityGroup, event.group_id)
        if group is None or group.status != CommunityGroupStatus.ACTIVE:
            return False
    if event.target_user_id is not None:
        target = db.get(User, event.target_user_id)
        if target is None or target.status != UserStatus.ACTIVE:
            return False
    return True


def _hidden_actor_ids(db: Session, viewer_id: str | None) -> set[str]:
    if viewer_id is None:
        return set()
    muted = set(
        db.scalars(
            select(CommunityUserMute.muted_user_id).where(
                CommunityUserMute.user_id == viewer_id,
                or_(
                    CommunityUserMute.expires_at.is_(None),
                    CommunityUserMute.expires_at > utc_now(),
                ),
            )
        ).all()
    )
    blocks = db.execute(
        select(CommunityUserBlock.blocker_id, CommunityUserBlock.blocked_id).where(
            or_(
                CommunityUserBlock.blocker_id == viewer_id,
                CommunityUserBlock.blocked_id == viewer_id,
            )
        )
    ).all()
    return muted | {
        blocked_id if blocker_id == viewer_id else blocker_id for blocker_id, blocked_id in blocks
    }


def _preview(value: str) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= 180 else f"{compact[:177]}..."


def _encode_cursor(created_at: datetime, record_id: str) -> str:
    payload = {"created_at": created_at.isoformat(), "id": record_id}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        record_id = str(payload["id"])
        if not record_id:
            raise ValueError
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return created_at, record_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError("community.invalid_cursor", "分页游标无效", status_code=422) from exc
