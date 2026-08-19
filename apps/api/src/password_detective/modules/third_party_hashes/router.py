from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from password_detective.core.rate_limit import rate_limit
from password_detective.db.dependencies import get_db
from password_detective.db.models.archive_fingerprint import FingerprintAlgorithm
from password_detective.modules.archives.hash_schemas import (
    HashCommentListResponse,
    HashDetailResponse,
)
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.third_party_hashes.service import (
    get_third_party_hash_detail,
    list_third_party_hash_comments,
)
from password_detective.modules.third_party_oauth.dependencies import (
    ThirdPartyPrincipal,
    require_third_party_scope,
)

router = APIRouter(prefix="/third-party/hashes", tags=["第三方 API·哈希只读"])
DbSession = Annotated[Session, Depends(get_db)]
HashReadPrincipal = Annotated[
    ThirdPartyPrincipal,
    Depends(require_third_party_scope("hash:read")),
]


def _disable_private_response_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"


@router.get(
    "/{algorithm}/{digest}",
    response_model=HashDetailResponse,
    dependencies=[Depends(rate_limit("third_party.hash.detail", limit=60, window_seconds=60))],
)
def hash_detail(
    algorithm: FingerprintAlgorithm,
    digest: str,
    request: Request,
    response: Response,
    db: DbSession,
    principal: HashReadPrincipal,
) -> HashDetailResponse:
    _disable_private_response_caching(response)
    return get_third_party_hash_detail(
        db,
        algorithm=algorithm,
        digest=digest,
        principal=principal,
        context=get_client_context(request),
    )


@router.get(
    "/{algorithm}/{digest}/comments",
    response_model=HashCommentListResponse,
    dependencies=[Depends(rate_limit("third_party.hash.comments", limit=120, window_seconds=60))],
)
def hash_comments(
    algorithm: FingerprintAlgorithm,
    digest: str,
    request: Request,
    response: Response,
    db: DbSession,
    principal: HashReadPrincipal,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> HashCommentListResponse:
    _disable_private_response_caching(response)
    return list_third_party_hash_comments(
        db,
        algorithm=algorithm,
        digest=digest,
        principal=principal,
        context=get_client_context(request),
        cursor=cursor,
        limit=limit,
    )
