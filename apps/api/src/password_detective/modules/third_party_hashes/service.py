from __future__ import annotations

from sqlalchemy.orm import Session

from password_detective.db.audit import write_audit_log
from password_detective.db.models.archive_fingerprint import FingerprintAlgorithm
from password_detective.modules.archives.hash_schemas import (
    HashCommentListResponse,
    HashDetailResponse,
)
from password_detective.modules.archives.hash_service import (
    get_hash_detail,
    list_hash_comments,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.third_party_oauth.dependencies import ThirdPartyPrincipal


def _site_principal(principal: ThirdPartyPrincipal) -> Principal:
    return Principal(
        user=principal.user,
        session_family_id=principal.claims.token_family_id,
        mfa_verified=False,
    )


def _record_third_party_read(
    db: Session,
    *,
    principal: ThirdPartyPrincipal,
    context: ClientContext,
    action: str,
    algorithm: FingerprintAlgorithm,
    matched: bool,
    item_count: int | None = None,
) -> None:
    details: dict[str, str | bool | int] = {
        "client_id": principal.app.client_id,
        "algorithm": algorithm.value,
        "matched": matched,
    }
    if item_count is not None:
        details["item_count"] = item_count
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action=action,
        target_type="third_party_app",
        target_id=principal.app.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details=details,
    )
    db.commit()


def get_third_party_hash_detail(
    db: Session,
    *,
    algorithm: FingerprintAlgorithm,
    digest: str,
    principal: ThirdPartyPrincipal,
    context: ClientContext,
) -> HashDetailResponse:
    response = get_hash_detail(
        db,
        algorithm=algorithm,
        digest=digest,
        principal=_site_principal(principal),
        context=context,
    )
    _record_third_party_read(
        db,
        principal=principal,
        context=context,
        action="third_party_hash.detail_read",
        algorithm=algorithm,
        matched=response.matched,
    )
    return response


def list_third_party_hash_comments(
    db: Session,
    *,
    algorithm: FingerprintAlgorithm,
    digest: str,
    principal: ThirdPartyPrincipal,
    context: ClientContext,
    cursor: str | None,
    limit: int,
) -> HashCommentListResponse:
    response = list_hash_comments(
        db,
        algorithm=algorithm,
        digest=digest,
        principal=_site_principal(principal),
        cursor=cursor,
        limit=limit,
    )
    _record_third_party_read(
        db,
        principal=principal,
        context=context,
        action="third_party_hash.comments_read",
        algorithm=algorithm,
        matched=True,
        item_count=len(response.items),
    )
    return response
