from __future__ import annotations

import json
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
from password_detective.modules.account_privacy.schemas import (
    AuthorizationDeclarationCreateRequest,
    AuthorizationDeclarationListResponse,
    AuthorizationDeclarationResponse,
    PrivacyDeletionCreateRequest,
    PrivacyDeletionResponse,
    PrivacyExportDownloadRequest,
    PrivacyExportResponse,
    RevealHistoryResponse,
)
from password_detective.modules.account_privacy.service import (
    build_privacy_export,
    cancel_deletion_request,
    confirm_authorization_declaration,
    consume_privacy_export,
    create_deletion_request,
    create_privacy_export,
    get_current_deletion_request,
    get_privacy_export,
    list_authorization_declarations,
    list_reveal_history,
)
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import Principal, get_current_principal

router = APIRouter(tags=["账号活动与隐私"])


@router.get("/me/reveals", response_model=RevealHistoryResponse)
def reveals(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RevealHistoryResponse:
    return list_reveal_history(db, principal=principal, page=page, page_size=page_size)


@router.get(
    "/me/authorization-declarations",
    response_model=AuthorizationDeclarationListResponse,
)
def authorization_declarations(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AuthorizationDeclarationListResponse:
    return list_authorization_declarations(
        db, principal=principal, page=page, page_size=page_size
    )


@router.post(
    "/me/authorization-declarations",
    response_model=AuthorizationDeclarationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("privacy.authorization", limit=20, window_seconds=3600))],
)
def confirm_authorization(
    payload: AuthorizationDeclarationCreateRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AuthorizationDeclarationResponse:
    lease = acquire_idempotency(
        db,
        scope="privacy.authorization",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest(payload.model_dump(mode="json")),
    )
    if lease.cached_response is not None:
        response.status_code = lease.cached_status or status.HTTP_201_CREATED
        return AuthorizationDeclarationResponse.model_validate(lease.cached_response)
    try:
        result = confirm_authorization_declaration(
            db,
            settings,
            principal=principal,
            payload=payload,
            context=get_client_context(request),
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
    "/me/privacy/exports",
    response_model=PrivacyExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("privacy.exports", limit=3, window_seconds=86400))],
)
def request_export(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PrivacyExportResponse:
    lease = acquire_idempotency(
        db,
        scope="privacy.exports",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest({}),
    )
    if lease.cached_response is not None:
        response.status_code = lease.cached_status or status.HTTP_202_ACCEPTED
        return PrivacyExportResponse.model_validate(lease.cached_response)
    try:
        record = create_privacy_export(
            db, principal=principal, context=get_client_context(request)
        )
        if record.status.value == "pending":
            if settings.privacy_job_backend == "celery":
                from password_detective.worker import celery_app

                celery_app.send_task("privacy.build_export", args=[record.id])
            else:
                build_privacy_export(db, settings, record.id)
        result = get_privacy_export(
            db, settings, export_id=record.id, principal=principal
        )
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_202_ACCEPTED,
            response_body=result.model_dump(mode="json"),
        )
        return result
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@router.get("/me/privacy/exports/{export_id}", response_model=PrivacyExportResponse)
def export_status(
    export_id: str,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> PrivacyExportResponse:
    return get_privacy_export(db, settings, export_id=export_id, principal=principal)


@router.post(
    "/me/privacy/exports/{export_id}/download",
    dependencies=[Depends(rate_limit("privacy.export_download", limit=10, window_seconds=60))],
)
def download_export(
    export_id: str,
    payload: PrivacyExportDownloadRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> Response:
    artifact, digest = consume_privacy_export(
        db,
        export_id=export_id,
        principal=principal,
        token=payload.token,
        context=get_client_context(request),
    )
    body = json.dumps(artifact, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="privacy-export-{export_id}.json"',
            "Cache-Control": "no-store",
            "X-Artifact-SHA256": digest,
        },
    )


@router.post(
    "/me/privacy/deletion-requests",
    response_model=PrivacyDeletionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("privacy.deletion", limit=3, window_seconds=86400))],
)
def request_deletion(
    payload: PrivacyDeletionCreateRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PrivacyDeletionResponse:
    lease = acquire_idempotency(
        db,
        scope="privacy.deletion",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest(payload.model_dump(mode="json")),
    )
    if lease.cached_response is not None:
        response.status_code = lease.cached_status or status.HTTP_202_ACCEPTED
        return PrivacyDeletionResponse.model_validate(lease.cached_response)
    try:
        result = create_deletion_request(
            db,
            settings,
            principal=principal,
            reauth_token=payload.reauth_token,
            context=get_client_context(request),
        )
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_202_ACCEPTED,
            response_body=result.model_dump(mode="json"),
        )
        return result
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@router.get(
    "/me/privacy/deletion-requests/current",
    response_model=PrivacyDeletionResponse | None,
)
def current_deletion(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> PrivacyDeletionResponse | None:
    return get_current_deletion_request(db, principal=principal)


@router.post(
    "/me/privacy/deletion-requests/{request_id}/cancel",
    response_model=PrivacyDeletionResponse,
    dependencies=[Depends(rate_limit("privacy.deletion_cancel", limit=5, window_seconds=3600))],
)
def cancel_deletion(
    request_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PrivacyDeletionResponse:
    lease = acquire_idempotency(
        db,
        scope="privacy.deletion_cancel",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest({"request_id": request_id}),
    )
    if lease.cached_response is not None:
        return PrivacyDeletionResponse.model_validate(lease.cached_response)
    try:
        result = cancel_deletion_request(
            db,
            request_id=request_id,
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
