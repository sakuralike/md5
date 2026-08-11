from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query
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
from password_detective.modules.auth.dependencies import Principal, get_current_principal
from password_detective.modules.community.schemas import (
    CommunityBoardListResponse,
    CommunityCommentCreateRequest,
    CommunityPostCreateRequest,
    CommunityPostDetail,
    CommunityPostListResponse,
    CommunityReportCreateRequest,
    CommunityReportResponse,
)
from password_detective.modules.community.service import (
    create_comment,
    create_post,
    create_report,
    get_post,
    list_boards,
    list_posts,
)

router = APIRouter(prefix="/community", tags=["community"])
@router.get("/boards", response_model=CommunityBoardListResponse)
def community_boards(
    db: Annotated[Session, Depends(get_db)],
) -> CommunityBoardListResponse:
    return list_boards(db)


@router.get("/posts", response_model=CommunityPostListResponse)
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
    return _create_with_idempotency(
        db,
        scope="community.post.create",
        idempotency_key=idempotency_key,
        request_payload=payload.model_dump(mode="json"),
        principal=principal,
        response_type=CommunityPostDetail,
        create=lambda: create_post(db, payload=payload, principal=principal),
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
    return _create_with_idempotency(
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
    return _create_with_idempotency(
        db,
        scope="community.report.create",
        idempotency_key=idempotency_key,
        request_payload=payload.model_dump(mode="json"),
        principal=principal,
        response_type=CommunityReportResponse,
        create=lambda: create_report(db, payload=payload, principal=principal),
    )


def _create_with_idempotency[ResponseModel: BaseModel](
    db: Session,
    *,
    scope: str,
    idempotency_key: str,
    request_payload: dict[str, object],
    principal: Principal,
    response_type: type[ResponseModel],
    create: Callable[[], ResponseModel],
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
            response_status=201,
            response_body=response.model_dump(mode="json"),
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise
