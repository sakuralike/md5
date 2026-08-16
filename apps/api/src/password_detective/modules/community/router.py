from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from password_detective.core.idempotency import (
    abandon_idempotency,
    acquire_idempotency,
    complete_idempotency,
    payload_digest,
    require_idempotency_key,
)
from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.db.models.community import (
    CommunityActivityFeed,
    CommunityGroupRole,
    CommunityNotificationKind,
    CommunitySearchSource,
)
from password_detective.modules.auth.context import ClientContext, get_client_context
from password_detective.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    get_optional_principal,
)
from password_detective.modules.community.activity_service import (
    get_activity_preferences,
    list_activity,
    update_activity_preferences,
)
from password_detective.modules.community.group_service import (
    change_member_role,
    create_group,
    decide_member,
    get_group,
    join_group,
    leave_group,
    list_groups,
    update_group,
)
from password_detective.modules.community.notification_stream import (
    latest_delivered_event_id,
    list_delivered_events,
    unread_notification_count,
)
from password_detective.modules.community.schemas import (
    CommunityActivityListResponse,
    CommunityActivityPreferenceResponse,
    CommunityActivityPreferenceUpdateRequest,
    CommunityBoardListResponse,
    CommunityBookmarkListResponse,
    CommunityCommentCreateRequest,
    CommunityCommentLikeResponse,
    CommunityCommentListResponse,
    CommunityCommentUpdateRequest,
    CommunityGroupCreateRequest,
    CommunityGroupDetail,
    CommunityGroupListResponse,
    CommunityGroupMemberDecisionRequest,
    CommunityGroupMembershipResponse,
    CommunityGroupUpdateRequest,
    CommunityHomeResponse,
    CommunityMuteRequest,
    CommunityNotificationListResponse,
    CommunityNotificationPreferencesResponse,
    CommunityNotificationPreferencesUpdateRequest,
    CommunityNotificationReadResponse,
    CommunityOwnProfileResponse,
    CommunityPostCreateRequest,
    CommunityPostDetail,
    CommunityPostInteractionResponse,
    CommunityPostListResponse,
    CommunityPostUpdateRequest,
    CommunityPrivacyUpdateRequest,
    CommunityProfileUpdateRequest,
    CommunityPublicProfileResponse,
    CommunityRelationListResponse,
    CommunityRelationshipMutationResponse,
    CommunityReportCreateRequest,
    CommunityReportResponse,
    CommunitySearchResponse,
)
from password_detective.modules.community.search_service import search_community
from password_detective.modules.community.service import (
    create_comment,
    create_post,
    create_report,
    delete_comment,
    delete_post,
    get_notification_preferences,
    get_own_profile,
    get_post,
    get_public_profile,
    list_boards,
    list_bookmarks,
    list_comments,
    list_home,
    list_notifications,
    list_posts,
    list_relationship_users,
    mark_all_notifications_read,
    mark_notification_read,
    set_block,
    set_comment_like,
    set_follow,
    set_mute,
    set_post_bookmark,
    set_post_like,
    update_comment,
    update_notification_preferences,
    update_post,
    update_privacy_preferences,
    update_public_profile,
)

router = APIRouter(prefix="/community", tags=["community"])


@router.get("/boards", response_model=CommunityBoardListResponse)
def community_boards(
    db: Annotated[Session, Depends(get_db)],
) -> CommunityBoardListResponse:
    return list_boards(db)


@router.get(
    "/search",
    response_model=CommunitySearchResponse,
    dependencies=[Depends(rate_limit("community.search", limit=30, window_seconds=60))],
)
def community_search(
    q: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    types: Annotated[list[CommunitySearchSource] | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=20)] = 20,
) -> CommunitySearchResponse:
    return search_community(
        db,
        query=q,
        source_types=tuple(types or ()),
        page=page,
        page_size=page_size,
        principal=principal,
    )


@router.get("/home", response_model=CommunityHomeResponse)
def community_home(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    board_code: str | None = Query(default=None, min_length=1, max_length=32),
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CommunityHomeResponse:
    return list_home(db, board_code=board_code, page_size=page_size, principal=principal)


@router.get("/posts", response_model=CommunityPostListResponse, response_model_exclude_unset=True)
def community_posts(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    board_code: str | None = Query(default=None, min_length=1, max_length=32),
    group_slug: str | None = Query(default=None, min_length=3, max_length=64),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CommunityPostListResponse:
    return list_posts(
        db,
        board_code=board_code,
        group_slug=group_slug,
        page=page,
        page_size=page_size,
        principal=principal,
    )


@router.get("/me/profile", response_model=CommunityOwnProfileResponse)
def community_my_profile(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> CommunityOwnProfileResponse:
    return get_own_profile(db, principal=principal)


@router.patch(
    "/me/profile",
    response_model=CommunityOwnProfileResponse,
    dependencies=[Depends(rate_limit("community.profile.update", limit=30, window_seconds=3600))],
)
def community_my_profile_update(
    payload: CommunityProfileUpdateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityOwnProfileResponse:
    return _mutate_with_idempotency(
        db,
        scope="community.profile.update",
        idempotency_key=idempotency_key,
        request_payload=payload.model_dump(mode="json"),
        principal=principal,
        response_type=CommunityOwnProfileResponse,
        create=lambda: update_public_profile(
            db, payload=payload, principal=principal, context=get_client_context(request)
        ),
        response_status=status.HTTP_200_OK,
    )


@router.patch(
    "/me/privacy",
    response_model=CommunityOwnProfileResponse,
    dependencies=[Depends(rate_limit("community.privacy.update", limit=30, window_seconds=3600))],
)
def community_my_privacy_update(
    payload: CommunityPrivacyUpdateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityOwnProfileResponse:
    return _mutate_with_idempotency(
        db,
        scope="community.privacy.update",
        idempotency_key=idempotency_key,
        request_payload=payload.model_dump(mode="json"),
        principal=principal,
        response_type=CommunityOwnProfileResponse,
        create=lambda: update_privacy_preferences(
            db, payload=payload, principal=principal, context=get_client_context(request)
        ),
        response_status=status.HTTP_200_OK,
    )


@router.get("/users/{username}", response_model=CommunityPublicProfileResponse)
def community_public_profile(
    username: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
) -> CommunityPublicProfileResponse:
    return get_public_profile(db, username=username, principal=principal)


@router.get("/users/{username}/followers", response_model=CommunityRelationListResponse)
def community_followers(
    username: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CommunityRelationListResponse:
    return list_relationship_users(
        db,
        username=username,
        direction="followers",
        principal=principal,
        cursor=cursor,
        limit=limit,
    )


@router.get("/users/{username}/following", response_model=CommunityRelationListResponse)
def community_following(
    username: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CommunityRelationListResponse:
    return list_relationship_users(
        db,
        username=username,
        direction="following",
        principal=principal,
        cursor=cursor,
        limit=limit,
    )


def _relationship_mutation(
    *,
    username: str,
    operation: str,
    db: Session,
    principal: Principal,
    idempotency_key: str,
    request: Request,
    mute_payload: CommunityMuteRequest | None = None,
) -> CommunityRelationshipMutationResponse:
    action = {
        "follow": lambda: set_follow(
            db,
            username=username,
            followed=True,
            principal=principal,
            context=get_client_context(request),
        ),
        "unfollow": lambda: set_follow(
            db,
            username=username,
            followed=False,
            principal=principal,
            context=get_client_context(request),
        ),
        "block": lambda: set_block(
            db,
            username=username,
            blocked=True,
            principal=principal,
            context=get_client_context(request),
        ),
        "unblock": lambda: set_block(
            db,
            username=username,
            blocked=False,
            principal=principal,
            context=get_client_context(request),
        ),
        "mute": lambda: set_mute(
            db,
            username=username,
            muted=True,
            payload=mute_payload,
            principal=principal,
            context=get_client_context(request),
        ),
        "unmute": lambda: set_mute(
            db,
            username=username,
            muted=False,
            payload=None,
            principal=principal,
            context=get_client_context(request),
        ),
    }[operation]
    payload: dict[str, object] = {"username": username, "operation": operation}
    if mute_payload is not None:
        payload["mute"] = mute_payload.model_dump(mode="json")
    return _mutate_with_idempotency(
        db,
        scope=f"community.relation.{operation}",
        idempotency_key=idempotency_key,
        request_payload=payload,
        principal=principal,
        response_type=CommunityRelationshipMutationResponse,
        create=action,
        response_status=status.HTTP_200_OK,
    )


@router.put(
    "/users/{username}/follow",
    response_model=CommunityRelationshipMutationResponse,
    dependencies=[Depends(rate_limit("community.follow", limit=120, window_seconds=3600))],
)
def community_follow(
    username: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityRelationshipMutationResponse:
    return _relationship_mutation(
        username=username,
        operation="follow",
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
        request=request,
    )


@router.delete(
    "/users/{username}/follow",
    response_model=CommunityRelationshipMutationResponse,
    dependencies=[Depends(rate_limit("community.unfollow", limit=120, window_seconds=3600))],
)
def community_unfollow(
    username: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityRelationshipMutationResponse:
    return _relationship_mutation(
        username=username,
        operation="unfollow",
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
        request=request,
    )


@router.put(
    "/users/{username}/block",
    response_model=CommunityRelationshipMutationResponse,
    dependencies=[Depends(rate_limit("community.block", limit=60, window_seconds=3600))],
)
def community_block(
    username: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityRelationshipMutationResponse:
    return _relationship_mutation(
        username=username,
        operation="block",
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
        request=request,
    )


@router.delete(
    "/users/{username}/block",
    response_model=CommunityRelationshipMutationResponse,
    dependencies=[Depends(rate_limit("community.unblock", limit=60, window_seconds=3600))],
)
def community_unblock(
    username: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityRelationshipMutationResponse:
    return _relationship_mutation(
        username=username,
        operation="unblock",
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
        request=request,
    )


@router.put(
    "/users/{username}/mute",
    response_model=CommunityRelationshipMutationResponse,
    dependencies=[Depends(rate_limit("community.mute", limit=60, window_seconds=3600))],
)
def community_mute(
    username: str,
    payload: CommunityMuteRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityRelationshipMutationResponse:
    return _relationship_mutation(
        username=username,
        operation="mute",
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
        request=request,
        mute_payload=payload,
    )


@router.delete(
    "/users/{username}/mute",
    response_model=CommunityRelationshipMutationResponse,
    dependencies=[Depends(rate_limit("community.unmute", limit=60, window_seconds=3600))],
)
def community_unmute(
    username: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityRelationshipMutationResponse:
    return _relationship_mutation(
        username=username,
        operation="unmute",
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
        request=request,
    )


@router.get("/groups", response_model=CommunityGroupListResponse)
def community_groups(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
) -> CommunityGroupListResponse:
    return list_groups(db, principal=principal)


@router.post("/groups", response_model=CommunityGroupDetail, status_code=201)
def community_group_create(
    payload: CommunityGroupCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityGroupDetail:
    return _mutate_with_idempotency(
        db,
        scope="community.group.create",
        idempotency_key=idempotency_key,
        request_payload=payload.model_dump(mode="json"),
        principal=principal,
        response_type=CommunityGroupDetail,
        create=lambda: create_group(
            db,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        ),
    )


@router.get("/groups/{group_slug}", response_model=CommunityGroupDetail)
def community_group_detail(
    group_slug: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
) -> CommunityGroupDetail:
    return get_group(db, slug=group_slug, principal=principal)


@router.patch("/groups/{group_slug}", response_model=CommunityGroupDetail)
def community_group_update(
    group_slug: str,
    payload: CommunityGroupUpdateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityGroupDetail:
    return _mutate_with_idempotency(
        db,
        scope="community.group.update",
        idempotency_key=idempotency_key,
        request_payload={"group_slug": group_slug, **payload.model_dump(mode="json")},
        principal=principal,
        response_type=CommunityGroupDetail,
        create=lambda: update_group(
            db,
            slug=group_slug,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        ),
        response_status=status.HTTP_200_OK,
    )


@router.post("/groups/{group_slug}/join", response_model=CommunityGroupMembershipResponse)
def community_group_join(
    group_slug: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityGroupMembershipResponse:
    return _mutate_with_idempotency(
        db,
        scope="community.group.join",
        idempotency_key=idempotency_key,
        request_payload={"group_slug": group_slug},
        principal=principal,
        response_type=CommunityGroupMembershipResponse,
        create=lambda: join_group(db, slug=group_slug, principal=principal),
        response_status=status.HTTP_200_OK,
    )


@router.delete("/groups/{group_slug}/membership", response_model=CommunityGroupMembershipResponse)
def community_group_leave(
    group_slug: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityGroupMembershipResponse:
    return _mutate_with_idempotency(
        db,
        scope="community.group.leave",
        idempotency_key=idempotency_key,
        request_payload={"group_slug": group_slug},
        principal=principal,
        response_type=CommunityGroupMembershipResponse,
        create=lambda: leave_group(db, slug=group_slug, principal=principal),
        response_status=status.HTTP_200_OK,
    )


@router.post(
    "/groups/{group_slug}/members/{username}/decision",
    response_model=CommunityGroupMembershipResponse,
)
def community_group_member_decision(
    group_slug: str,
    username: str,
    payload: CommunityGroupMemberDecisionRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityGroupMembershipResponse:
    return _mutate_with_idempotency(
        db,
        scope="community.group.member.decision",
        idempotency_key=idempotency_key,
        request_payload={
            "group_slug": group_slug,
            "username": username,
            **payload.model_dump(mode="json"),
        },
        principal=principal,
        response_type=CommunityGroupMembershipResponse,
        create=lambda: decide_member(
            db,
            slug=group_slug,
            username=username,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        ),
        response_status=status.HTTP_200_OK,
    )


@router.patch(
    "/groups/{group_slug}/members/{username}/role",
    response_model=CommunityGroupMembershipResponse,
)
def community_group_member_role(
    group_slug: str,
    username: str,
    role: CommunityGroupRole,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityGroupMembershipResponse:
    return _mutate_with_idempotency(
        db,
        scope="community.group.member.role",
        idempotency_key=idempotency_key,
        request_payload={"group_slug": group_slug, "username": username, "role": role.value},
        principal=principal,
        response_type=CommunityGroupMembershipResponse,
        create=lambda: change_member_role(
            db,
            slug=group_slug,
            username=username,
            role=role,
            principal=principal,
            context=get_client_context(request),
        ),
        response_status=status.HTTP_200_OK,
    )


@router.get("/notifications", response_model=CommunityNotificationListResponse)
def community_notifications(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    unread_only: bool = False,
    kind: CommunityNotificationKind | None = None,
) -> CommunityNotificationListResponse:
    return list_notifications(
        db,
        principal=principal,
        cursor=cursor,
        limit=limit,
        unread_only=unread_only,
        kind=kind,
    )


@router.get(
    "/notifications/stream",
    dependencies=[
        Depends(rate_limit("community.notification.stream", limit=60, window_seconds=60))
    ],
)
async def community_notification_stream(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    return StreamingResponse(
        _notification_event_stream(
            request,
            recipient_id=principal.user.id,
            last_event_id=last_event_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/notifications/preferences", response_model=CommunityNotificationPreferencesResponse)
def community_notification_preferences(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> CommunityNotificationPreferencesResponse:
    return get_notification_preferences(db, principal=principal)


@router.put("/notifications/preferences", response_model=CommunityNotificationPreferencesResponse)
def community_notification_preferences_update(
    payload: CommunityNotificationPreferencesUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> CommunityNotificationPreferencesResponse:
    return update_notification_preferences(db, payload=payload, principal=principal)


@router.get("/activity", response_model=CommunityActivityListResponse)
def community_activity(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    feed: CommunityActivityFeed = CommunityActivityFeed.LATEST,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CommunityActivityListResponse:
    return list_activity(db, feed=feed, principal=principal, cursor=cursor, limit=limit)


@router.get("/activity/preferences", response_model=CommunityActivityPreferenceResponse)
def community_activity_preferences(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> CommunityActivityPreferenceResponse:
    return get_activity_preferences(db, principal=principal)


@router.put("/activity/preferences", response_model=CommunityActivityPreferenceResponse)
def community_activity_preferences_update(
    payload: CommunityActivityPreferenceUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> CommunityActivityPreferenceResponse:
    return update_activity_preferences(db, payload=payload, principal=principal)


@router.post(
    "/notifications/read-all",
    response_model=CommunityNotificationReadResponse,
    dependencies=[
        Depends(rate_limit("community.notification.read_all", limit=30, window_seconds=3600))
    ],
)
def community_notifications_read_all(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityNotificationReadResponse:
    return _mutate_with_idempotency(
        db,
        scope="community.notification.read_all",
        idempotency_key=idempotency_key,
        request_payload={},
        principal=principal,
        response_type=CommunityNotificationReadResponse,
        create=lambda: mark_all_notifications_read(db, principal=principal),
        response_status=status.HTTP_200_OK,
    )


@router.post(
    "/notifications/{notification_id}/read",
    response_model=CommunityNotificationReadResponse,
    dependencies=[
        Depends(rate_limit("community.notification.read", limit=120, window_seconds=3600))
    ],
)
def community_notification_read(
    notification_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityNotificationReadResponse:
    return _mutate_with_idempotency(
        db,
        scope="community.notification.read",
        idempotency_key=idempotency_key,
        request_payload={"notification_id": notification_id},
        principal=principal,
        response_type=CommunityNotificationReadResponse,
        create=lambda: mark_notification_read(
            db, notification_id=notification_id, principal=principal
        ),
        response_status=status.HTTP_200_OK,
    )


@router.get("/posts/{post_id}", response_model=CommunityPostDetail)
def community_post_detail(
    post_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
) -> CommunityPostDetail:
    return get_post(db, post_id, principal=principal)


@router.get("/posts/{post_id}/comments", response_model=CommunityCommentListResponse)
def community_comments(
    post_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CommunityCommentListResponse:
    return list_comments(
        db,
        post_id=post_id,
        cursor=cursor,
        limit=limit,
        principal=principal,
    )


@router.post(
    "/posts",
    response_model=CommunityPostDetail,
    status_code=201,
    dependencies=[Depends(rate_limit("community.post.create", limit=10, window_seconds=3600))],
)
def community_post_create(
    payload: CommunityPostCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityPostDetail:
    return _mutate_with_idempotency(
        db,
        scope="community.post.create",
        idempotency_key=idempotency_key,
        request_payload=payload.model_dump(mode="json"),
        principal=principal,
        response_type=CommunityPostDetail,
        create=lambda: create_post(db, payload=payload, principal=principal),
    )


@router.patch(
    "/posts/{post_id}",
    response_model=CommunityPostDetail,
    dependencies=[Depends(rate_limit("community.post.update", limit=30, window_seconds=3600))],
)
def community_post_update(
    post_id: str,
    payload: CommunityPostUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    context: Annotated[ClientContext, Depends(get_client_context)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityPostDetail:
    return _mutate_with_idempotency(
        db,
        scope="community.post.update",
        idempotency_key=idempotency_key,
        request_payload={"post_id": post_id, **payload.model_dump(mode="json")},
        principal=principal,
        response_type=CommunityPostDetail,
        create=lambda: update_post(
            db, post_id=post_id, payload=payload, principal=principal, context=context
        ),
        response_status=status.HTTP_200_OK,
    )


@router.delete(
    "/posts/{post_id}",
    response_model=CommunityPostDetail,
    dependencies=[Depends(rate_limit("community.post.delete", limit=30, window_seconds=3600))],
)
def community_post_delete(
    post_id: str,
    expected_version: Annotated[int, Query(ge=1)],
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    context: Annotated[ClientContext, Depends(get_client_context)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityPostDetail:
    return _mutate_with_idempotency(
        db,
        scope="community.post.delete",
        idempotency_key=idempotency_key,
        request_payload={"post_id": post_id, "expected_version": expected_version},
        principal=principal,
        response_type=CommunityPostDetail,
        create=lambda: delete_post(
            db,
            post_id=post_id,
            expected_version=expected_version,
            principal=principal,
            context=context,
        ),
        response_status=status.HTTP_200_OK,
    )


@router.post(
    "/posts/{post_id}/comments",
    response_model=CommunityPostDetail,
    status_code=201,
    dependencies=[Depends(rate_limit("community.comment.create", limit=30, window_seconds=3600))],
)
def community_comment_create(
    post_id: str,
    payload: CommunityCommentCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityPostDetail:
    return _mutate_with_idempotency(
        db,
        scope="community.comment.create",
        idempotency_key=idempotency_key,
        request_payload={"post_id": post_id, **payload.model_dump(mode="json")},
        principal=principal,
        response_type=CommunityPostDetail,
        create=lambda: create_comment(
            db,
            post_id=post_id,
            payload=payload,
            principal=principal,
        ),
    )


@router.patch(
    "/comments/{comment_id}",
    response_model=CommunityPostDetail,
    dependencies=[Depends(rate_limit("community.comment.update", limit=60, window_seconds=3600))],
)
def community_comment_update(
    comment_id: str,
    payload: CommunityCommentUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    context: Annotated[ClientContext, Depends(get_client_context)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityPostDetail:
    return _mutate_with_idempotency(
        db,
        scope="community.comment.update",
        idempotency_key=idempotency_key,
        request_payload={"comment_id": comment_id, **payload.model_dump(mode="json")},
        principal=principal,
        response_type=CommunityPostDetail,
        create=lambda: update_comment(
            db, comment_id=comment_id, payload=payload, principal=principal, context=context
        ),
        response_status=status.HTTP_200_OK,
    )


@router.delete(
    "/comments/{comment_id}",
    response_model=CommunityPostDetail,
    dependencies=[Depends(rate_limit("community.comment.delete", limit=60, window_seconds=3600))],
)
def community_comment_delete(
    comment_id: str,
    expected_version: Annotated[int, Query(ge=1)],
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    context: Annotated[ClientContext, Depends(get_client_context)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityPostDetail:
    return _mutate_with_idempotency(
        db,
        scope="community.comment.delete",
        idempotency_key=idempotency_key,
        request_payload={"comment_id": comment_id, "expected_version": expected_version},
        principal=principal,
        response_type=CommunityPostDetail,
        create=lambda: delete_comment(
            db,
            comment_id=comment_id,
            expected_version=expected_version,
            principal=principal,
            context=context,
        ),
        response_status=status.HTTP_200_OK,
    )


@router.get("/bookmarks", response_model=CommunityBookmarkListResponse)
def community_bookmarks(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CommunityBookmarkListResponse:
    return list_bookmarks(
        db,
        principal=principal,
        cursor=cursor,
        limit=limit,
    )


def _post_like_mutation(
    *,
    liked: bool,
    post_id: str,
    db: Session,
    principal: Principal,
    idempotency_key: str,
) -> CommunityPostInteractionResponse:
    return _mutate_with_idempotency(
        db,
        scope=f"community.post.like.{str(liked).lower()}",
        idempotency_key=idempotency_key,
        request_payload={"post_id": post_id, "liked": liked},
        principal=principal,
        response_type=CommunityPostInteractionResponse,
        create=lambda: set_post_like(
            db,
            post_id=post_id,
            principal=principal,
            liked=liked,
        ),
        response_status=status.HTTP_200_OK,
    )


@router.put(
    "/posts/{post_id}/like",
    response_model=CommunityPostInteractionResponse,
    dependencies=[Depends(rate_limit("community.post.like", limit=240, window_seconds=3600))],
)
def community_post_like(
    post_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityPostInteractionResponse:
    return _post_like_mutation(
        liked=True,
        post_id=post_id,
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
    )


@router.delete(
    "/posts/{post_id}/like",
    response_model=CommunityPostInteractionResponse,
    dependencies=[Depends(rate_limit("community.post.unlike", limit=240, window_seconds=3600))],
)
def community_post_unlike(
    post_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityPostInteractionResponse:
    return _post_like_mutation(
        liked=False,
        post_id=post_id,
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
    )


def _comment_like_mutation(
    *,
    liked: bool,
    comment_id: str,
    db: Session,
    principal: Principal,
    idempotency_key: str,
) -> CommunityCommentLikeResponse:
    return _mutate_with_idempotency(
        db,
        scope=f"community.comment.like.{str(liked).lower()}",
        idempotency_key=idempotency_key,
        request_payload={"comment_id": comment_id, "liked": liked},
        principal=principal,
        response_type=CommunityCommentLikeResponse,
        create=lambda: set_comment_like(
            db,
            comment_id=comment_id,
            principal=principal,
            liked=liked,
        ),
        response_status=status.HTTP_200_OK,
    )


@router.put(
    "/comments/{comment_id}/like",
    response_model=CommunityCommentLikeResponse,
    dependencies=[Depends(rate_limit("community.comment.like", limit=240, window_seconds=3600))],
)
def community_comment_like(
    comment_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityCommentLikeResponse:
    return _comment_like_mutation(
        liked=True,
        comment_id=comment_id,
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
    )


@router.delete(
    "/comments/{comment_id}/like",
    response_model=CommunityCommentLikeResponse,
    dependencies=[Depends(rate_limit("community.comment.unlike", limit=240, window_seconds=3600))],
)
def community_comment_unlike(
    comment_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityCommentLikeResponse:
    return _comment_like_mutation(
        liked=False,
        comment_id=comment_id,
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
    )


def _post_bookmark_mutation(
    *,
    bookmarked: bool,
    post_id: str,
    db: Session,
    principal: Principal,
    idempotency_key: str,
) -> CommunityPostInteractionResponse:
    return _mutate_with_idempotency(
        db,
        scope=f"community.post.bookmark.{str(bookmarked).lower()}",
        idempotency_key=idempotency_key,
        request_payload={"post_id": post_id, "bookmarked": bookmarked},
        principal=principal,
        response_type=CommunityPostInteractionResponse,
        create=lambda: set_post_bookmark(
            db,
            post_id=post_id,
            principal=principal,
            bookmarked=bookmarked,
        ),
        response_status=status.HTTP_200_OK,
    )


@router.put(
    "/posts/{post_id}/bookmark",
    response_model=CommunityPostInteractionResponse,
    dependencies=[Depends(rate_limit("community.post.bookmark", limit=240, window_seconds=3600))],
)
def community_post_bookmark(
    post_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityPostInteractionResponse:
    return _post_bookmark_mutation(
        bookmarked=True,
        post_id=post_id,
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
    )


@router.delete(
    "/posts/{post_id}/bookmark",
    response_model=CommunityPostInteractionResponse,
    dependencies=[Depends(rate_limit("community.post.unbookmark", limit=240, window_seconds=3600))],
)
def community_post_unbookmark(
    post_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityPostInteractionResponse:
    return _post_bookmark_mutation(
        bookmarked=False,
        post_id=post_id,
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/reports",
    response_model=CommunityReportResponse,
    status_code=201,
    dependencies=[Depends(rate_limit("community.report.create", limit=20, window_seconds=86400))],
)
def community_report_create(
    payload: CommunityReportCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CommunityReportResponse:
    return _mutate_with_idempotency(
        db,
        scope="community.report.create",
        idempotency_key=idempotency_key,
        request_payload=payload.model_dump(mode="json"),
        principal=principal,
        response_type=CommunityReportResponse,
        create=lambda: create_report(db, payload=payload, principal=principal),
    )


def _mutate_with_idempotency[ResponseModel: BaseModel](
    db: Session,
    *,
    scope: str,
    idempotency_key: str,
    request_payload: dict[str, object],
    principal: Principal,
    response_type: type[ResponseModel],
    create: Callable[[], ResponseModel],
    response_status: int = status.HTTP_201_CREATED,
) -> ResponseModel:
    lease = acquire_idempotency(
        db,
        scope=scope,
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest(request_payload),
    )
    if lease.cached_response is not None:
        return response_type.model_validate(lease.cached_response)
    try:
        response = create()
        complete_idempotency(
            db,
            lease,
            response_status=response_status,
            response_body=response.model_dump(mode="json"),
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


def _sse_message(*, event: str, data: BaseModel, event_id: str | None = None) -> str:
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    payload = json.dumps(data.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    lines.append(f"data: {payload}")
    return "\n".join(lines) + "\n\n"


async def _notification_event_stream(
    request: Request,
    *,
    recipient_id: str,
    last_event_id: str | None,
) -> AsyncIterator[str]:
    cursor = last_event_id
    if cursor is None:
        with request.app.state.database.session_factory() as db:
            cursor = latest_delivered_event_id(db, recipient_id)
            unread_count = unread_notification_count(db, recipient_id)
        from password_detective.modules.community.schemas import CommunityNotificationStreamReady

        yield _sse_message(
            event="ready",
            event_id=cursor,
            data=CommunityNotificationStreamReady(event_id=cursor, unread_count=unread_count),
        )
    heartbeat_seconds = 15
    elapsed = 0
    while not await request.is_disconnected():
        with request.app.state.database.session_factory() as db:
            batch = list_delivered_events(
                db,
                recipient_id=recipient_id,
                after_event_id=cursor,
                limit=20,
            )
        if batch.items:
            for item in batch.items:
                cursor = item.event_id
                yield _sse_message(event="notification", event_id=item.event_id, data=item)
            elapsed = 0
        else:
            await asyncio.sleep(1)
            elapsed += 1
            if elapsed >= heartbeat_seconds:
                yield ": heartbeat\n\n"
                elapsed = 0
