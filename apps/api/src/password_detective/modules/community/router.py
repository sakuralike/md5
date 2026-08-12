from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
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
from password_detective.db.models.community import CommunityBoardCode
from password_detective.modules.auth.context import ClientContext, get_client_context
from password_detective.modules.auth.dependencies import Principal, get_current_principal
from password_detective.modules.community.schemas import (
    CommunityBoardListResponse,
    CommunityCommentCreateRequest,
    CommunityCommentListResponse,
    CommunityCommentUpdateRequest,
    CommunityHomeResponse,
    CommunityPostCreateRequest,
    CommunityPostDetail,
    CommunityPostListResponse,
    CommunityPostUpdateRequest,
    CommunityReportCreateRequest,
    CommunityReportResponse,
)
from password_detective.modules.community.service import (
    create_comment,
    create_post,
    create_report,
    delete_comment,
    delete_post,
    get_post,
    list_boards,
    list_comments,
    list_home,
    list_posts,
    update_comment,
    update_post,
)

router = APIRouter(prefix="/community", tags=["community"])
@router.get("/boards", response_model=CommunityBoardListResponse)
def community_boards(
    db: Annotated[Session, Depends(get_db)],
) -> CommunityBoardListResponse:
    return list_boards(db)


@router.get("/home", response_model=CommunityHomeResponse)
def community_home(
    db: Annotated[Session, Depends(get_db)],
    board_code: CommunityBoardCode | None = None,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CommunityHomeResponse:
    return list_home(db, board_code=board_code, page_size=page_size)


@router.get(
    "/posts", response_model=CommunityPostListResponse, response_model_exclude_unset=True
)
def community_posts(
    db: Annotated[Session, Depends(get_db)],
    board_code: CommunityBoardCode | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CommunityPostListResponse:
    return list_posts(db, board_code=board_code, page=page, page_size=page_size)


@router.get("/posts/{post_id}", response_model=CommunityPostDetail)
def community_post_detail(
    post_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> CommunityPostDetail:
    return get_post(db, post_id)


@router.get("/posts/{post_id}/comments", response_model=CommunityCommentListResponse)
def community_comments(
    post_id: str,
    db: Annotated[Session, Depends(get_db)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CommunityCommentListResponse:
    return list_comments(db, post_id=post_id, cursor=cursor, limit=limit)


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
