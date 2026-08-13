from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
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
from password_detective.db.models.archive_fingerprint import FingerprintAlgorithm
from password_detective.modules.archives.hash_schemas import (
    HashCommentCreateRequest,
    HashDetailResponse,
    HashInteractionResponse,
    HashVoteRequest,
)
from password_detective.modules.archives.hash_service import (
    create_hash_comment,
    get_hash_detail,
    set_hash_comment_like,
    set_hash_like,
    set_hash_vote,
)
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    get_optional_principal,
)

router = APIRouter(prefix="/hashes", tags=["哈希值详情"])


def _mutate_with_idempotency[ResponseModel](
    db: Session,
    *,
    scope: str,
    idempotency_key: str,
    principal: Principal,
    payload: dict[str, object],
    response_type: type[ResponseModel],
    create,
    response_status: int = status.HTTP_200_OK,
) -> ResponseModel:
    lease = acquire_idempotency(
        db,
        scope=scope,
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest(payload),
    )
    if lease.cached_response is not None:
        return response_type.model_validate(lease.cached_response)
    try:
        result = create()
        complete_idempotency(
            db,
            lease,
            response_status=response_status,
            response_body=result.model_dump(mode="json"),
        )
        return result
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@router.get(
    "/{algorithm}/{digest}",
    response_model=HashDetailResponse,
    dependencies=[Depends(rate_limit("hash.detail", limit=60, window_seconds=60))],
)
def hash_detail(
    algorithm: FingerprintAlgorithm,
    digest: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
) -> HashDetailResponse:
    return get_hash_detail(
        db,
        algorithm=algorithm,
        digest=digest,
        principal=principal,
        context=get_client_context(request),
    )


def _like_mutation(
    *,
    liked: bool,
    algorithm: FingerprintAlgorithm,
    digest: str,
    db: Session,
    principal: Principal,
    idempotency_key: str,
) -> HashInteractionResponse:
    return _mutate_with_idempotency(
        db,
        scope=f"hash.like.{str(liked).lower()}",
        idempotency_key=idempotency_key,
        principal=principal,
        payload={"algorithm": algorithm.value, "digest": digest, "liked": liked},
        response_type=HashInteractionResponse,
        create=lambda: set_hash_like(
            db,
            algorithm=algorithm,
            digest=digest,
            principal=principal,
            liked=liked,
        ),
    )


@router.put(
    "/{algorithm}/{digest}/like",
    response_model=HashInteractionResponse,
    dependencies=[Depends(rate_limit("hash.like", limit=240, window_seconds=3600))],
)
def hash_like(
    algorithm: FingerprintAlgorithm,
    digest: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> HashInteractionResponse:
    return _like_mutation(
        liked=True,
        algorithm=algorithm,
        digest=digest,
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
    )


@router.delete(
    "/{algorithm}/{digest}/like",
    response_model=HashInteractionResponse,
    dependencies=[Depends(rate_limit("hash.unlike", limit=240, window_seconds=3600))],
)
def hash_unlike(
    algorithm: FingerprintAlgorithm,
    digest: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> HashInteractionResponse:
    return _like_mutation(
        liked=False,
        algorithm=algorithm,
        digest=digest,
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
    )


@router.put(
    "/{algorithm}/{digest}/vote",
    response_model=HashInteractionResponse,
    dependencies=[Depends(rate_limit("hash.vote", limit=120, window_seconds=3600))],
)
def hash_vote(
    algorithm: FingerprintAlgorithm,
    digest: str,
    payload: HashVoteRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> HashInteractionResponse:
    return _mutate_with_idempotency(
        db,
        scope="hash.vote",
        idempotency_key=idempotency_key,
        principal=principal,
        payload={"algorithm": algorithm.value, "digest": digest, **payload.model_dump(mode="json")},
        response_type=HashInteractionResponse,
        create=lambda: set_hash_vote(
            db,
            algorithm=algorithm,
            digest=digest,
            payload=payload,
            principal=principal,
        ),
    )


def _comment_like_mutation(
    *,
    liked: bool,
    algorithm: FingerprintAlgorithm,
    digest: str,
    comment_id: str,
    db: Session,
    principal: Principal,
    idempotency_key: str,
) -> HashDetailResponse:
    return _mutate_with_idempotency(
        db,
        scope=f"hash.comment.like.{str(liked).lower()}",
        idempotency_key=idempotency_key,
        principal=principal,
        payload={
            "algorithm": algorithm.value,
            "digest": digest,
            "comment_id": comment_id,
            "liked": liked,
        },
        response_type=HashDetailResponse,
        create=lambda: set_hash_comment_like(
            db,
            algorithm=algorithm,
            digest=digest,
            comment_id=comment_id,
            principal=principal,
            liked=liked,
        ),
    )


@router.put(
    "/{algorithm}/{digest}/comments/{comment_id}/like",
    response_model=HashDetailResponse,
    dependencies=[Depends(rate_limit("hash.comment.like", limit=240, window_seconds=3600))],
)
def hash_comment_like(
    algorithm: FingerprintAlgorithm,
    digest: str,
    comment_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> HashDetailResponse:
    return _comment_like_mutation(
        liked=True,
        algorithm=algorithm,
        digest=digest,
        comment_id=comment_id,
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
    )


@router.delete(
    "/{algorithm}/{digest}/comments/{comment_id}/like",
    response_model=HashDetailResponse,
    dependencies=[Depends(rate_limit("hash.comment.unlike", limit=240, window_seconds=3600))],
)
def hash_comment_unlike(
    algorithm: FingerprintAlgorithm,
    digest: str,
    comment_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> HashDetailResponse:
    return _comment_like_mutation(
        liked=False,
        algorithm=algorithm,
        digest=digest,
        comment_id=comment_id,
        db=db,
        principal=principal,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/{algorithm}/{digest}/comments",
    response_model=HashDetailResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("hash.comment.create", limit=30, window_seconds=3600))],
)
def hash_comment_create(
    algorithm: FingerprintAlgorithm,
    digest: str,
    payload: HashCommentCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> HashDetailResponse:
    return _mutate_with_idempotency(
        db,
        scope="hash.comment.create",
        idempotency_key=idempotency_key,
        principal=principal,
        payload={"algorithm": algorithm.value, "digest": digest, **payload.model_dump(mode="json")},
        response_type=HashDetailResponse,
        create=lambda: create_hash_comment(
            db,
            algorithm=algorithm,
            digest=digest,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        ),
        response_status=status.HTTP_201_CREATED,
    )
