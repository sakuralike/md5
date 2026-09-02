from __future__ import annotations

import base64
import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
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
from password_detective.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    get_optional_principal,
    require_admin_only_mfa,
)
from password_detective.modules.desktop_plugins.schemas import (
    DownloadTicketRequest,
    DownloadTicketResponse,
    PluginArchitecture,
    PluginBrokerAuthorizationRequest,
    PluginBrokerAuthorizationResponse,
    PluginCategory,
    PluginInstallEventRequest,
    PluginInstallEventResponse,
    PluginMigrationRetryListResponse,
    PluginReportCreateRequest,
    PluginReportResponse,
    PluginRevocationListResponse,
    PublicPluginCatalogResponse,
    PublicPluginDetailResponse,
    PublicPluginVersionResponse,
)
from password_detective.modules.desktop_plugins.service import (
    authorize_broker_capability,
    create_download_ticket,
    create_report,
    get_canary_plugin,
    get_public_plugin,
    get_public_version,
    list_migration_retries,
    list_public_catalog,
    list_revocations,
    prepare_download,
    record_install_event,
)

router = APIRouter(prefix="/desktop/plugins", tags=["桌面插件市场"])


@router.get("/migration-retries", response_model=PluginMigrationRetryListResponse)
def migration_retries(
    installation_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> PluginMigrationRetryListResponse:
    return list_migration_retries(
        db,
        user_id=principal.user.id,
        installation_id=installation_id,
    )


@router.get(
    "/catalog",
    response_model=PublicPluginCatalogResponse,
    dependencies=[Depends(rate_limit("desktop.plugin.catalog", limit=120, window_seconds=60))],
)
def plugin_catalog(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    query: Annotated[str | None, Query(max_length=128)] = None,
    category: PluginCategory | None = None,
    architecture: PluginArchitecture = "windows-x64",
    host_version: Annotated[str, Query(min_length=5, max_length=32)] = "0.1.0",
    protocol_version: Annotated[int, Query(ge=1, le=1)] = 1,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PublicPluginCatalogResponse:
    response.headers["Cache-Control"] = "public, max-age=60"
    return list_public_catalog(
        db,
        query=query,
        category=category,
        architecture=architecture,
        host_version=host_version,
        protocol_version=protocol_version,
        page=page,
        page_size=page_size,
    )


@router.get("/revocations", response_model=PluginRevocationListResponse)
def plugin_revocations(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> JSONResponse | Response:
    payload = list_revocations(db)
    body = payload.model_dump(mode="json")
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    etag = f'"sha256-{hashlib.sha256(canonical.encode("utf-8")).hexdigest()}"'
    headers = {"Cache-Control": "public, max-age=300", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=body, headers=headers)


@router.get(
    "/canary/catalog",
    response_model=PublicPluginCatalogResponse,
)
def canary_plugin_catalog(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_only_mfa)],
    query: Annotated[str | None, Query(max_length=128)] = None,
    category: PluginCategory | None = None,
    architecture: PluginArchitecture = "windows-x64",
    host_version: Annotated[str, Query(min_length=5, max_length=32)] = "0.1.0",
    protocol_version: Annotated[int, Query(ge=1, le=1)] = 1,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PublicPluginCatalogResponse:
    response.headers["Cache-Control"] = "private, no-store"
    return list_public_catalog(
        db,
        query=query,
        category=category,
        architecture=architecture,
        host_version=host_version,
        protocol_version=protocol_version,
        page=page,
        page_size=page_size,
        publication_channel="canary",
    )


@router.get(
    "/canary/{plugin_slug}",
    response_model=PublicPluginDetailResponse,
)
def canary_plugin_detail(
    plugin_slug: str,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_only_mfa)],
) -> PublicPluginDetailResponse:
    response.headers["Cache-Control"] = "private, no-store"
    return get_canary_plugin(db, slug=plugin_slug)


@router.get(
    "/downloads/{token}",
    name="download_desktop_plugin_artifact",
    dependencies=[Depends(rate_limit("desktop.plugin.download", limit=60, window_seconds=60))],
)
def download_plugin_artifact(
    token: str,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    installation_id: Annotated[
        str | None, Header(alias="X-Plugin-Installation-Id", max_length=36)
    ] = None,
    canary_signature: Annotated[
        str | None, Header(alias="X-Plugin-Canary-Signature", max_length=2048)
    ] = None,
) -> FileResponse:
    artifact, path = prepare_download(
        db,
        settings,
        raw_token=token,
        user_id=principal.user.id if principal else None,
        installation_id=installation_id,
        signature=canary_signature,
    )
    digest = base64.b64encode(bytes.fromhex(artifact.sha256)).decode("ascii")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=artifact.artifact_filename,
        headers={
            "Cache-Control": "private, no-store",
            "ETag": f'"sha256-{artifact.sha256}"',
            "Digest": f"sha-256={digest}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{plugin_slug}", response_model=PublicPluginDetailResponse)
def plugin_detail(
    plugin_slug: str,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> PublicPluginDetailResponse:
    response.headers["Cache-Control"] = "public, max-age=60"
    return get_public_plugin(db, slug=plugin_slug)


@router.post(
    "/{plugin_slug}/broker/authorize",
    response_model=PluginBrokerAuthorizationResponse,
    dependencies=[
        Depends(rate_limit("desktop.plugin.broker.authorize", limit=120, window_seconds=60))
    ],
)
def authorize_plugin_broker(
    plugin_slug: str,
    payload: PluginBrokerAuthorizationRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> PluginBrokerAuthorizationResponse:
    return authorize_broker_capability(
        db,
        plugin_slug=plugin_slug,
        payload=payload,
        principal=principal,
        context=get_client_context(request),
    )


@router.get("/{plugin_slug}/versions/{semver}", response_model=PublicPluginVersionResponse)
def plugin_version(
    plugin_slug: str,
    semver: str,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> PublicPluginVersionResponse:
    response.headers["Cache-Control"] = "public, max-age=60"
    return get_public_version(db, slug=plugin_slug, semver=semver)


@router.post(
    "/{plugin_slug}/download-ticket",
    response_model=DownloadTicketResponse,
    dependencies=[
        Depends(rate_limit("desktop.plugin.download_ticket", limit=60, window_seconds=60))
    ],
)
def issue_plugin_download_ticket(
    plugin_slug: str,
    payload: DownloadTicketRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DownloadTicketResponse:
    response.headers["Cache-Control"] = "no-store"
    return create_download_ticket(
        db,
        settings,
        slug=plugin_slug,
        semver=payload.semver,
        architecture=payload.architecture,
        download_url_builder=lambda token: (
            f"{settings.public_origin}"
            f"{request.url_for('download_desktop_plugin_artifact', token=token).path}"
        ),
    )


@router.post("/{plugin_slug}/reports", response_model=PluginReportResponse, status_code=201)
def report_plugin(
    plugin_slug: str,
    payload: PluginReportCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginReportResponse:
    lease = acquire_idempotency(
        db,
        scope="desktop.plugin.report.create",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest({"plugin_slug": plugin_slug, **payload.model_dump()}),
    )
    if lease.cached_response is not None:
        return PluginReportResponse.model_validate(lease.cached_response)
    try:
        response = create_report(
            db,
            plugin_slug=plugin_slug,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_201_CREATED,
            response_body=response.model_dump(mode="json"),
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@router.post("/install-events", response_model=PluginInstallEventResponse, status_code=202)
def record_plugin_install_event(
    payload: PluginInstallEventRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginInstallEventResponse:
    return record_install_event(
        db,
        payload=payload,
        user_id=principal.user.id if principal else None,
        idempotency_key=idempotency_key,
    )
