from __future__ import annotations

from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.errors import AppError
from password_detective.core.idempotency import (
    IdempotencyLease,
    abandon_idempotency,
    acquire_idempotency,
    complete_idempotency,
    payload_digest,
    require_idempotency_key,
)
from password_detective.db.dependencies import get_db
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import Principal, require_admin_mfa
from password_detective.modules.desktop_plugins.llm_review import review_plugin
from password_detective.modules.desktop_plugins.review_policy import (
    get_current_review_policy,
    get_llm_api_key,
    review_policy_response,
    save_llm_api_key,
    save_review_policy,
)
from password_detective.modules.desktop_plugins.runner_service import get_review_metrics
from password_detective.modules.desktop_plugins.schemas import (
    PluginReportListResponse,
    PluginReportResponse,
    PluginReportReviewRequest,
    PluginReviewDetailResponse,
    PluginReviewLlmConnectionResponse,
    PluginReviewLlmKeyUpdate,
    PluginReviewMetricsResponse,
    PluginReviewPolicyResponse,
    PluginReviewPolicyUpdate,
    PluginReviewQueueResponse,
    PluginVersionApproveRequest,
    PluginVersionPublishRequest,
    PluginVersionRejectRequest,
    PluginVersionRevokeRequest,
    PluginVersionYankRequest,
)
from password_detective.modules.desktop_plugins.service import (
    approve_version,
    get_review_detail,
    list_reports,
    list_review_queue,
    publish_version,
    reject_version,
    rerun_static_review,
    review_report,
    revoke_version,
    yank_version,
)

router = APIRouter(prefix="/admin/plugin-reviews", tags=["管理端·插件审核"])
policy_router = APIRouter(prefix="/admin/plugin-review-policy", tags=["管理端·插件审核策略"])


def _lease(
    db: Session, principal: Principal, scope: str, key: str, payload: object
) -> IdempotencyLease:
    return acquire_idempotency(
        db,
        scope=scope,
        owner_key=principal.user.id,
        idempotency_key=key,
        request_hash=payload_digest(payload),
    )


def _finish(db: Session, lease: IdempotencyLease, response) -> None:
    complete_idempotency(
        db,
        lease,
        response_status=status.HTTP_200_OK,
        response_body=response.model_dump(mode="json"),
    )


def _abort(db: Session, lease: IdempotencyLease) -> None:
    db.rollback()
    abandon_idempotency(db, lease)


@router.get("/queue", response_model=PluginReviewQueueResponse)
def review_queue(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_mfa)],
    status_filter: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PluginReviewQueueResponse:
    return list_review_queue(db, page=page, page_size=page_size, status_filter=status_filter)


@router.get("/versions/{version_id}", response_model=PluginReviewDetailResponse)
def review_detail(
    version_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_mfa)],
) -> PluginReviewDetailResponse:
    return get_review_detail(db, version_id=version_id)


@router.post("/versions/{version_id}/approve", response_model=PluginReviewDetailResponse)
def approve_plugin_version(
    version_id: str,
    payload: PluginVersionApproveRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginReviewDetailResponse:
    lease = _lease(
        db,
        principal,
        "admin.plugin.version.approve",
        idempotency_key,
        {"version_id": version_id, **payload.model_dump()},
    )
    if lease.cached_response is not None:
        return PluginReviewDetailResponse.model_validate(lease.cached_response)
    try:
        response = approve_version(
            db,
            version_id=version_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        _finish(db, lease, response)
        return response
    except Exception:
        _abort(db, lease)
        raise


@router.post("/versions/{version_id}/rerun", response_model=PluginReviewDetailResponse)
def rerun_plugin_static_review(
    version_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginReviewDetailResponse:
    lease = _lease(
        db,
        principal,
        "admin.plugin.version.static_review_rerun",
        idempotency_key,
        {"version_id": version_id},
    )
    if lease.cached_response is not None:
        return PluginReviewDetailResponse.model_validate(lease.cached_response)
    try:
        response = rerun_static_review(
            db,
            version_id=version_id,
            principal=principal,
            context=get_client_context(request),
        )
        _finish(db, lease, response)
        return response
    except Exception:
        _abort(db, lease)
        raise


@router.post("/versions/{version_id}/reject", response_model=PluginReviewDetailResponse)
def reject_plugin_version(
    version_id: str,
    payload: PluginVersionRejectRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginReviewDetailResponse:
    lease = _lease(
        db,
        principal,
        "admin.plugin.version.reject",
        idempotency_key,
        {"version_id": version_id, **payload.model_dump()},
    )
    if lease.cached_response is not None:
        return PluginReviewDetailResponse.model_validate(lease.cached_response)
    try:
        response = reject_version(
            db,
            version_id=version_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        _finish(db, lease, response)
        return response
    except Exception:
        _abort(db, lease)
        raise


@router.post("/versions/{version_id}/publish", response_model=PluginReviewDetailResponse)
def publish_plugin_version(
    version_id: str,
    payload: PluginVersionPublishRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginReviewDetailResponse:
    lease = _lease(
        db,
        principal,
        "admin.plugin.version.publish",
        idempotency_key,
        {"version_id": version_id, **payload.model_dump()},
    )
    if lease.cached_response is not None:
        return PluginReviewDetailResponse.model_validate(lease.cached_response)
    try:
        response = publish_version(
            db,
            settings,
            version_id=version_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        _finish(db, lease, response)
        return response
    except Exception:
        _abort(db, lease)
        raise


@router.post("/versions/{version_id}/yank", response_model=PluginReviewDetailResponse)
def yank_plugin_version(
    version_id: str,
    payload: PluginVersionYankRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginReviewDetailResponse:
    lease = _lease(
        db,
        principal,
        "admin.plugin.version.yank",
        idempotency_key,
        {"version_id": version_id, **payload.model_dump()},
    )
    if lease.cached_response is not None:
        return PluginReviewDetailResponse.model_validate(lease.cached_response)
    try:
        response = yank_version(
            db,
            version_id=version_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        _finish(db, lease, response)
        return response
    except Exception:
        _abort(db, lease)
        raise


@router.post("/versions/{version_id}/revoke", response_model=PluginReviewDetailResponse)
def revoke_plugin_version(
    version_id: str,
    payload: PluginVersionRevokeRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginReviewDetailResponse:
    lease = _lease(
        db,
        principal,
        "admin.plugin.version.revoke",
        idempotency_key,
        {"version_id": version_id, **payload.model_dump()},
    )
    if lease.cached_response is not None:
        return PluginReviewDetailResponse.model_validate(lease.cached_response)
    try:
        response = revoke_version(
            db,
            settings,
            version_id=version_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        _finish(db, lease, response)
        return response
    except Exception:
        _abort(db, lease)
        raise


@router.get("/reports", response_model=PluginReportListResponse)
def reports(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_mfa)],
    status_filter: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PluginReportListResponse:
    return list_reports(db, page=page, page_size=page_size, status_filter=status_filter)


@router.post("/reports/{report_id}/review", response_model=PluginReportResponse)
def review_plugin_report(
    report_id: str,
    payload: PluginReportReviewRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginReportResponse:
    lease = _lease(
        db,
        principal,
        "admin.plugin.report.review",
        idempotency_key,
        {"report_id": report_id, **payload.model_dump()},
    )
    if lease.cached_response is not None:
        return PluginReportResponse.model_validate(lease.cached_response)
    try:
        response = review_report(
            db,
            report_id=report_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        _finish(db, lease, response)
        return response
    except Exception:
        _abort(db, lease)
        raise


@router.get("/metrics", response_model=PluginReviewMetricsResponse)
def review_metrics(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_mfa)],
) -> PluginReviewMetricsResponse:
    return get_review_metrics(db)


@policy_router.get("", response_model=PluginReviewPolicyResponse)
def plugin_review_policy(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_mfa)],
) -> PluginReviewPolicyResponse:
    return review_policy_response(db, get_current_review_policy(db))


@policy_router.put("", response_model=PluginReviewPolicyResponse)
def update_plugin_review_policy(
    payload: PluginReviewPolicyUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginReviewPolicyResponse:
    lease = _lease(
        db,
        principal,
        "admin.plugin_review_policy.save",
        idempotency_key,
        payload.model_dump(mode="json"),
    )
    if lease.cached_response is not None:
        return PluginReviewPolicyResponse.model_validate(lease.cached_response)
    try:
        response = save_review_policy(
            db,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        _finish(db, lease, response)
        return response
    except Exception:
        _abort(db, lease)
        raise


@policy_router.put("/llm-key", status_code=status.HTTP_204_NO_CONTENT)
def update_plugin_review_llm_key(
    payload: PluginReviewLlmKeyUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> None:
    lease = _lease(
        db,
        principal,
        "admin.plugin_review_policy.llm_key.save",
        idempotency_key,
        {"api_key": "redacted"},
    )
    if lease.cached_response is not None:
        return None
    try:
        save_llm_api_key(
            db,
            settings,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        _finish(
            db,
            lease,
            PluginReviewLlmConnectionResponse(
                connected=True,
                provider="openai_compatible",
                model="key_saved",
            ),
        )
        return None
    except Exception:
        _abort(db, lease)
        raise


@policy_router.post("/llm-test", response_model=PluginReviewLlmConnectionResponse)
def test_plugin_review_llm(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[Principal, Depends(require_admin_mfa)],
) -> PluginReviewLlmConnectionResponse:
    policy = get_current_review_policy(db)
    result = review_plugin(
        settings,
        plugin=SimpleNamespace(slug="connectivity.probe"),
        version=SimpleNamespace(
            semver="0.0.0",
            manifest_json={"schema": "pd.plugin/v1"},
            requested_capabilities=[],
        ),
        static_result=SimpleNamespace(summary={"blocked": False}, evidence={"findings": []}),
        policy=policy,
        api_key=get_llm_api_key(db, settings),
    )
    if result is None:
        raise AppError("desktop_plugin.llm_not_configured", "LLM Provider 未配置", status_code=409)
    return PluginReviewLlmConnectionResponse(
        connected=True,
        provider=policy.llm_provider,
        model=policy.llm_model,
    )
