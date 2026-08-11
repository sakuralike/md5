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
from password_detective.db.models.community import CommunityReportStatus
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import Principal, require_admin_mfa
from password_detective.modules.community.admin_schemas import (
    AdminCommunityPostModerateRequest,
    AdminCommunityPostMutationResponse,
    AdminCommunityReportListResponse,
    AdminCommunityReportMutationResponse,
    AdminCommunityReportResolveRequest,
)
from password_detective.modules.community.admin_service import (
    list_admin_reports,
    moderate_admin_post,
    resolve_admin_report,
)

admin_router = APIRouter(prefix="/admin/community", tags=["社区治理"])


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
            response_status=200,
            response_body=response.model_dump(mode="json"),
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise
