from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.idempotency import (
    IdempotencyLease,
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
from password_detective.modules.desktop_plugins.schemas import (
    ArtifactUploadResponse,
    PluginProjectCreateRequest,
    PluginProjectDetailResponse,
    PluginProjectListResponse,
    PluginProjectUpdateRequest,
    PluginVersionCreateRequest,
    PluginVersionFinalizeRequest,
    PluginVersionResponse,
    SigningKeyCreateRequest,
    SigningKeyListResponse,
    SigningKeyResponse,
    SigningKeyRevokeRequest,
    UploadSessionCreateRequest,
    UploadSessionResponse,
)
from password_detective.modules.desktop_plugins.service import (
    create_project,
    create_upload_session,
    create_version,
    finalize_version,
    get_project,
    list_projects,
    list_signing_keys,
    register_signing_key,
    revoke_signing_key,
    update_project,
    upload_artifact,
)

router = APIRouter(prefix="/developer", tags=["开发者·桌面插件"])


def _acquire(
    db: Session,
    *,
    principal: Principal,
    scope: str,
    key: str,
    payload: object,
) -> IdempotencyLease:
    return acquire_idempotency(
        db,
        scope=scope,
        owner_key=principal.user.id,
        idempotency_key=key,
        request_hash=payload_digest(payload),
    )


def _cached[ResponseModel: BaseModel](
    lease: IdempotencyLease, model: type[ResponseModel]
) -> ResponseModel | None:
    if lease.cached_response is None:
        return None
    return model.model_validate(lease.cached_response)


def _complete(db: Session, lease: IdempotencyLease, response: BaseModel, code: int) -> None:
    complete_idempotency(
        db,
        lease,
        response_status=code,
        response_body=response.model_dump(mode="json"),
    )


def _abort(db: Session, lease: IdempotencyLease) -> None:
    db.rollback()
    abandon_idempotency(db, lease)


@router.post(
    "/plugins/signing-keys",
    response_model=SigningKeyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit("developer.plugin.signing_key.create", limit=10, window_seconds=3600))
    ],
)
def create_plugin_signing_key(
    payload: SigningKeyCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> SigningKeyResponse:
    lease = _acquire(
        db,
        principal=principal,
        scope="developer.plugin.signing_key.create",
        key=idempotency_key,
        payload=payload.model_dump(),
    )
    if cached := _cached(lease, SigningKeyResponse):
        return cached
    try:
        response = register_signing_key(
            db,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        _complete(db, lease, response, status.HTTP_201_CREATED)
        return response
    except Exception:
        _abort(db, lease)
        raise


@router.get("/plugins/signing-keys", response_model=SigningKeyListResponse)
def get_plugin_signing_keys(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> SigningKeyListResponse:
    return list_signing_keys(db, principal=principal)


@router.post(
    "/plugins/signing-keys/{signing_key_id}/revoke",
    response_model=SigningKeyResponse,
    dependencies=[
        Depends(rate_limit("developer.plugin.signing_key.revoke", limit=10, window_seconds=3600))
    ],
)
def revoke_plugin_signing_key(
    signing_key_id: str,
    payload: SigningKeyRevokeRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> SigningKeyResponse:
    lease = _acquire(
        db,
        principal=principal,
        scope="developer.plugin.signing_key.revoke",
        key=idempotency_key,
        payload={"signing_key_id": signing_key_id, **payload.model_dump()},
    )
    if cached := _cached(lease, SigningKeyResponse):
        return cached
    try:
        response = revoke_signing_key(
            db,
            key_id=signing_key_id,
            reauth_token=payload.reauth_token,
            principal=principal,
            context=get_client_context(request),
        )
        _complete(db, lease, response, status.HTTP_200_OK)
        return response
    except Exception:
        _abort(db, lease)
        raise


@router.post(
    "/plugins",
    response_model=PluginProjectDetailResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit("developer.plugin.project.create", limit=20, window_seconds=3600))
    ],
)
def create_plugin_project(
    payload: PluginProjectCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginProjectDetailResponse:
    lease = _acquire(
        db,
        principal=principal,
        scope="developer.plugin.project.create",
        key=idempotency_key,
        payload=payload.model_dump(),
    )
    if cached := _cached(lease, PluginProjectDetailResponse):
        return cached
    try:
        response = create_project(
            db,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        _complete(db, lease, response, status.HTTP_201_CREATED)
        return response
    except Exception:
        _abort(db, lease)
        raise


@router.get("/plugins", response_model=PluginProjectListResponse)
def get_plugin_projects(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PluginProjectListResponse:
    return list_projects(db, principal=principal, page=page, page_size=page_size)


@router.get("/plugins/{plugin_id}", response_model=PluginProjectDetailResponse)
def get_plugin_project(
    plugin_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> PluginProjectDetailResponse:
    return get_project(db, plugin_id=plugin_id, principal=principal)


@router.patch("/plugins/{plugin_id}", response_model=PluginProjectDetailResponse)
def patch_plugin_project(
    plugin_id: str,
    payload: PluginProjectUpdateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginProjectDetailResponse:
    lease = _acquire(
        db,
        principal=principal,
        scope="developer.plugin.project.update",
        key=idempotency_key,
        payload={"plugin_id": plugin_id, **payload.model_dump(exclude_unset=True)},
    )
    if cached := _cached(lease, PluginProjectDetailResponse):
        return cached
    try:
        response = update_project(
            db,
            plugin_id=plugin_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        _complete(db, lease, response, status.HTTP_200_OK)
        return response
    except Exception:
        _abort(db, lease)
        raise


@router.post(
    "/plugins/{plugin_id}/versions",
    response_model=PluginVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_plugin_version(
    plugin_id: str,
    payload: PluginVersionCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginVersionResponse:
    lease = _acquire(
        db,
        principal=principal,
        scope="developer.plugin.version.create",
        key=idempotency_key,
        payload={"plugin_id": plugin_id, **payload.model_dump()},
    )
    if cached := _cached(lease, PluginVersionResponse):
        return cached
    try:
        response = create_version(
            db,
            plugin_id=plugin_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        _complete(db, lease, response, status.HTTP_201_CREATED)
        return response
    except Exception:
        _abort(db, lease)
        raise


@router.post(
    "/plugin-versions/{version_id}/upload-session",
    response_model=UploadSessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit("developer.plugin.upload_session", limit=30, window_seconds=3600))
    ],
)
def create_plugin_upload_session(
    version_id: str,
    payload: UploadSessionCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> UploadSessionResponse:
    return create_upload_session(
        db,
        settings,
        version_id=version_id,
        payload=payload,
        principal=principal,
        context=get_client_context(request),
        upload_url_builder=lambda session_id, token: (
            f"{request.url_for('upload_desktop_plugin_artifact', session_id=session_id)}"
            f"?token={token}"
        ),
    )


@router.put(
    "/plugin-uploads/{session_id}",
    response_model=ArtifactUploadResponse,
    name="upload_desktop_plugin_artifact",
    dependencies=[
        Depends(rate_limit("developer.plugin.artifact_upload", limit=30, window_seconds=3600))
    ],
)
async def put_plugin_artifact(
    session_id: str,
    request: Request,
    token: Annotated[str, Query(min_length=32, max_length=256)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ArtifactUploadResponse:
    raw_content_length = request.headers.get("content-length")
    content_length = (
        int(raw_content_length) if raw_content_length and raw_content_length.isdigit() else None
    )
    return await upload_artifact(
        db,
        settings,
        session_id=session_id,
        raw_token=token,
        chunks=request.stream(),
        content_length=content_length,
    )


@router.post(
    "/plugin-versions/{version_id}/finalize",
    response_model=PluginVersionResponse,
    dependencies=[
        Depends(rate_limit("developer.plugin.version.finalize", limit=30, window_seconds=3600))
    ],
)
def finalize_plugin_version(
    version_id: str,
    payload: PluginVersionFinalizeRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginVersionResponse:
    lease = _acquire(
        db,
        principal=principal,
        scope="developer.plugin.version.finalize",
        key=idempotency_key,
        payload={"version_id": version_id, **payload.model_dump()},
    )
    if cached := _cached(lease, PluginVersionResponse):
        return cached
    try:
        response = finalize_version(
            db,
            settings,
            version_id=version_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        _complete(db, lease, response, status.HTTP_200_OK)
        return response
    except Exception:
        _abort(db, lease)
        raise
