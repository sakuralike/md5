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
    private_owner_key,
    require_idempotency_key,
)
from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.db.models.archive_fingerprint import FingerprintAlgorithm
from password_detective.modules.archives.schemas import (
    ArchiveSearchResponse,
    MySubmissionsResponse,
    RevealResponse,
    SubmissionRequest,
    SubmissionResponse,
)
from password_detective.modules.archives.service import (
    create_submission,
    list_my_submissions,
    reveal_best_candidate,
    search_archive,
)
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    get_optional_principal,
)

router = APIRouter(tags=["档案与贡献"])


@router.get(
    "/archives/search",
    response_model=ArchiveSearchResponse,
    dependencies=[Depends(rate_limit("archives.search", limit=60, window_seconds=60))],
)
def search(
    fingerprint: Annotated[str, Query(min_length=32, max_length=128)],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    algorithm: FingerprintAlgorithm | None = None,
) -> ArchiveSearchResponse:
    return search_archive(
        db,
        digest=fingerprint,
        algorithm=algorithm,
        principal=principal,
        context=get_client_context(request),
    )


@router.post(
    "/archives/submissions",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("archives.submissions", limit=20, window_seconds=3600))],
)
def submit(
    payload: SubmissionRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> SubmissionResponse:
    request_hash = payload_digest(payload.model_dump(mode="json"))
    context = get_client_context(request)
    owner_key = (
        principal.user.id
        if principal is not None
        else private_owner_key(
            f"guest:{context.ip_prefix or 'unknown'}:{context.user_agent or 'unknown'}"
        )
    )
    lease = acquire_idempotency(
        db,
        scope="archives.submissions",
        owner_key=owner_key,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    if lease.cached_response is not None:
        response.status_code = lease.cached_status or status.HTTP_201_CREATED
        return SubmissionResponse.model_validate(lease.cached_response)
    try:
        result = create_submission(
            db,
            settings,
            payload=payload,
            principal=principal,
            context=context,
            idempotency_key=idempotency_key,
        )
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_201_CREATED,
            response_body=result.model_dump(mode="json"),
        )
        return result
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@router.post(
    "/archives/{archive_id}/reveal",
    response_model=RevealResponse,
    dependencies=[Depends(rate_limit("archives.reveal", limit=20, window_seconds=60))],
)
def reveal(
    archive_id: str,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> RevealResponse:
    result = reveal_best_candidate(
        db,
        settings,
        archive_id=archive_id,
        principal=principal,
        context=get_client_context(request),
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return result


@router.get("/me/submissions", response_model=MySubmissionsResponse)
def my_submissions(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MySubmissionsResponse:
    return list_my_submissions(db, principal=principal, page=page, page_size=page_size)
