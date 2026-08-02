from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
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
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import Principal, get_current_principal
from password_detective.modules.verification.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    MyFeedbackHistoryResponse,
)
from password_detective.modules.verification.service import (
    list_my_feedback_history,
    record_feedback,
)

router = APIRouter(tags=["验证与反馈"])


@router.post(
    "/candidates/{candidate_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit("candidates.feedback", limit=60, window_seconds=3600))],
)
def submit_feedback(
    candidate_id: str,
    payload: FeedbackRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> FeedbackResponse:
    request_hash = payload_digest({"candidate_id": candidate_id, **payload.model_dump(mode="json")})
    lease = acquire_idempotency(
        db,
        scope="candidates.feedback",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    if lease.cached_response is not None:
        response.status_code = lease.cached_status or status.HTTP_200_OK
        return FeedbackResponse.model_validate(lease.cached_response)
    try:
        result = record_feedback(
            db,
            settings,
            candidate_id=candidate_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_200_OK,
            response_body=result.model_dump(mode="json"),
        )
        return result
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@router.get("/me/feedback", response_model=MyFeedbackHistoryResponse)
def my_feedback_history(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MyFeedbackHistoryResponse:
    return list_my_feedback_history(
        db,
        principal=principal,
        page=page,
        page_size=page_size,
    )
