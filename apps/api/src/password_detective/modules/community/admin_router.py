from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
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
    CommunityNotificationKind,
    CommunityNotificationOutboxStatus,
    CommunityReportStatus,
)
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import (
    Principal,
    require_admin_mfa,
    require_admin_only_mfa,
)
from password_detective.modules.community.admin_schemas import (
    AdminCommunityBoardCreateRequest,
    AdminCommunityBoardListResponse,
    AdminCommunityBoardMutationResponse,
    AdminCommunityBoardUpdateRequest,
    AdminCommunityNotificationOutboxListResponse,
    AdminCommunityNotificationOutboxMetrics,
    AdminCommunityNotificationReplayRequest,
    AdminCommunityNotificationReplayResponse,
    AdminCommunityPostModerateRequest,
    AdminCommunityPostMutationResponse,
    AdminCommunityReportListResponse,
    AdminCommunityReportMutationResponse,
    AdminCommunityReportResolveRequest,
)
from password_detective.modules.community.admin_service import (
    create_admin_board,
    get_admin_notification_outbox_metrics,
    list_admin_boards,
    list_admin_notification_outbox,
    list_admin_reports,
    moderate_admin_post,
    replay_admin_notification_outbox,
    resolve_admin_report,
    update_admin_board,
)

admin_router = APIRouter(prefix="/admin/community", tags=["社区治理"])


@admin_router.get("/boards", response_model=AdminCommunityBoardListResponse)
def admin_community_boards(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_only_mfa)],
) -> AdminCommunityBoardListResponse:
    del principal
    return list_admin_boards(db)


@admin_router.post(
    "/boards",
    response_model=AdminCommunityBoardMutationResponse,
    status_code=201,
    dependencies=[
        Depends(rate_limit("admin.community.board.create", limit=20, window_seconds=3600))
    ],
)
def admin_community_board_create(
    payload: AdminCommunityBoardCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_only_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AdminCommunityBoardMutationResponse:
    return _mutate_with_idempotency(
        db,
        scope="admin.community.board.create",
        idempotency_key=idempotency_key,
        request_payload=payload.model_dump(mode="json"),
        principal=principal,
        response_type=AdminCommunityBoardMutationResponse,
        mutate=lambda: create_admin_board(
            db, payload=payload, principal=principal, context=get_client_context(request)
        ),
        response_status=201,
    )


@admin_router.patch(
    "/boards/{board_code}",
    response_model=AdminCommunityBoardMutationResponse,
    dependencies=[
        Depends(rate_limit("admin.community.board.update", limit=60, window_seconds=3600))
    ],
)
def admin_community_board_update(
    board_code: str,
    payload: AdminCommunityBoardUpdateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_only_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AdminCommunityBoardMutationResponse:
    return _mutate_with_idempotency(
        db,
        scope="admin.community.board.update",
        idempotency_key=idempotency_key,
        request_payload={"board_code": board_code, **payload.model_dump(mode="json")},
        principal=principal,
        response_type=AdminCommunityBoardMutationResponse,
        mutate=lambda: update_admin_board(
            db,
            board_code=board_code,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        ),
    )


@admin_router.get(
    "/notification-outbox/metrics",
    response_model=AdminCommunityNotificationOutboxMetrics,
)
def admin_community_notification_outbox_metrics(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_only_mfa)],
) -> AdminCommunityNotificationOutboxMetrics:
    del principal
    return get_admin_notification_outbox_metrics(db)


@admin_router.get(
    "/notification-outbox",
    response_model=AdminCommunityNotificationOutboxListResponse,
)
def admin_community_notification_outbox(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_only_mfa)],
    status: CommunityNotificationOutboxStatus | None = None,
    kind: CommunityNotificationKind | None = None,
    error_code: Annotated[str | None, Query(max_length=128)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminCommunityNotificationOutboxListResponse:
    del principal
    return list_admin_notification_outbox(
        db,
        status=status,
        kind=kind,
        error_code=error_code,
        page=page,
        page_size=page_size,
    )


@admin_router.post(
    "/notification-outbox/{event_id}/replay",
    response_model=AdminCommunityNotificationReplayResponse,
    dependencies=[
        Depends(
            rate_limit(
                "admin.community.notification_outbox.replay",
                limit=30,
                window_seconds=3600,
            )
        )
    ],
)
def admin_community_notification_outbox_replay(
    event_id: str,
    payload: AdminCommunityNotificationReplayRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_only_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AdminCommunityNotificationReplayResponse:
    return _mutate_with_idempotency(
        db,
        scope="admin.community.notification_outbox.replay",
        idempotency_key=idempotency_key,
        request_payload={"event_id": event_id, **payload.model_dump(mode="json")},
        principal=principal,
        response_type=AdminCommunityNotificationReplayResponse,
        mutate=lambda: replay_admin_notification_outbox(
            db,
            event_id=event_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        ),
    )


@admin_router.get("/reports", response_model=AdminCommunityReportListResponse)
def admin_community_reports(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    status: CommunityReportStatus | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminCommunityReportListResponse:
    del principal
    return list_admin_reports(db, status=status, page=page, page_size=page_size)


@admin_router.post(
    "/reports/{report_id}/resolve",
    response_model=AdminCommunityReportMutationResponse,
    dependencies=[
        Depends(rate_limit("admin.community.report.resolve", limit=120, window_seconds=3600))
    ],
)
def admin_community_report_resolve(
    report_id: str,
    payload: AdminCommunityReportResolveRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AdminCommunityReportMutationResponse:
    return _mutate_with_idempotency(
        db,
        scope="admin.community.report.resolve",
        idempotency_key=idempotency_key,
        request_payload={"report_id": report_id, **payload.model_dump(mode="json")},
        principal=principal,
        response_type=AdminCommunityReportMutationResponse,
        mutate=lambda: resolve_admin_report(
            db,
            report_id=report_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        ),
    )


@admin_router.post(
    "/posts/{post_id}/moderate",
    response_model=AdminCommunityPostMutationResponse,
    dependencies=[
        Depends(rate_limit("admin.community.post.moderate", limit=120, window_seconds=3600))
    ],
)
def admin_community_post_moderate(
    post_id: str,
    payload: AdminCommunityPostModerateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AdminCommunityPostMutationResponse:
    return _mutate_with_idempotency(
        db,
        scope="admin.community.post.moderate",
        idempotency_key=idempotency_key,
        request_payload={"post_id": post_id, **payload.model_dump(mode="json")},
        principal=principal,
        response_type=AdminCommunityPostMutationResponse,
        mutate=lambda: moderate_admin_post(
            db,
            post_id=post_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        ),
    )


def _mutate_with_idempotency[ResponseModel: BaseModel](
    db: Session,
    *,
    scope: str,
    idempotency_key: str,
    request_payload: dict[str, object],
    principal: Principal,
    response_type: type[ResponseModel],
    mutate: Callable[[], ResponseModel],
    response_status: int = 200,
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
        response = mutate()
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
