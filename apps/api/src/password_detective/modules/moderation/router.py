from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.idempotency import (
    abandon_idempotency,
    acquire_idempotency,
    complete_idempotency,
    payload_digest,
    require_idempotency_key,
)
from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.db.models.password_candidate import CandidateStatus
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import Principal, require_admin_mfa
from password_detective.modules.moderation.schemas import (
    CandidateModerationDetail,
    CandidateModerationListResponse,
    CandidateTransitionRequest,
    CandidateTransitionResponse,
)
from password_detective.modules.moderation.service import (
    get_candidate_detail,
    list_candidates,
    transition_candidate,
)

router = APIRouter(prefix="/admin/candidates", tags=["管理端·候选审核"])


@router.get("", response_model=CandidateModerationListResponse)
def candidate_review_list(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    status: CandidateStatus | None = None,
    query: Annotated[str | None, Query(max_length=128)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CandidateModerationListResponse:
    del principal
    return list_candidates(db, status=status, query=query, page=page, page_size=page_size)


@router.get("/{candidate_id}", response_model=CandidateModerationDetail)
def candidate_review_detail(
    candidate_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> CandidateModerationDetail:
    del principal
    return get_candidate_detail(db, candidate_id)


@router.post(
    "/{candidate_id}/transition",
    response_model=CandidateTransitionResponse,
    dependencies=[Depends(rate_limit("admin.candidate.transition", limit=30, window_seconds=60))],
)
def candidate_transition(
    candidate_id: str,
    payload: CandidateTransitionRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CandidateTransitionResponse:
    request_body = payload.model_dump(mode="json")
    lease = acquire_idempotency(
        db,
        scope="admin.candidate.transition",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest({"candidate_id": candidate_id, **request_body}),
    )
    if lease.cached_response is not None:
        return CandidateTransitionResponse.model_validate(lease.cached_response)
    try:
        response = transition_candidate(
            db,
            settings=settings,
            candidate_id=candidate_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
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
