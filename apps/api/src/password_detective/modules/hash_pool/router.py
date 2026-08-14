from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from password_detective.db.dependencies import get_db
from password_detective.db.models.archive_fingerprint import FingerprintAlgorithm
from password_detective.modules.auth.dependencies import Principal, require_admin_mfa
from password_detective.modules.hash_pool.schemas import HashPoolListResponse
from password_detective.modules.hash_pool.service import list_hash_pool

router = APIRouter(prefix="/admin/hash-pool", tags=["管理端·总哈希池"])


@router.get("", response_model=HashPoolListResponse)
def hash_pool_list(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    query: Annotated[str | None, Query(max_length=128)] = None,
    algorithm: FingerprintAlgorithm | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> HashPoolListResponse:
    del principal
    return list_hash_pool(
        db,
        query=query,
        algorithm=algorithm,
        page=page,
        page_size=page_size,
    )
