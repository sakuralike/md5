from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
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
from password_detective.db.models.trust_case import TrustCaseKind, TrustCaseStatus
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    require_admin_mfa,
)
from password_detective.modules.trust_cases.schemas import (
    AccountAppealCreateRequest,
    AppealCreateRequest,
    ReportCreateRequest,
    TrustCaseAssignRequest,
    TrustCaseAssignResponse,
    TrustCaseDetail,
    TrustCaseListResponse,
    TrustCaseReopenRequest,
    TrustCaseReopenResponse,
    TrustCaseResolveRequest,
    TrustCaseResolveResponse,
    TrustCaseTransitionRequest,
    TrustCaseTransitionResponse,
)
from password_detective.modules.trust_cases.service import (
    assign_case,
    create_account_appeal,
    create_appeal,
    create_report,
    get_case_detail,
    list_admin_cases,
    list_my_cases,
    reopen_case,
    resolve_case,
    transition_case,
)

user_router = APIRouter(prefix="/trust", tags=["举报与申诉"])
admin_router = APIRouter(prefix="/admin/trust-cases", tags=["管理端·举报与申诉"])


@user_router.post(
    "/reports",
    response_model=TrustCaseDetail,
    status_code=201,
    dependencies=[Depends(rate_limit("trust.report.create", limit=10, window_seconds=3600))],
)
def report_create(
    payload: ReportCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> TrustCaseDetail:
    return _create_with_idempotency(
        db,
        scope="trust.report.create",
        idempotency_key=idempotency_key,
        payload={"kind": "report", **payload.model_dump(mode="json")},
        principal=principal,
        create=lambda: create_report(
            db,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        ),
    )


@user_router.post(
    "/appeals",
    response_model=TrustCaseDetail,
    status_code=201,
    dependencies=[Depends(rate_limit("trust.appeal.create", limit=5, window_seconds=86400))],
)
def appeal_create(
    payload: AppealCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> TrustCaseDetail:
    return _create_with_idempotency(
        db,
        scope="trust.appeal.create",
        idempotency_key=idempotency_key,
        payload={"kind": "appeal", **payload.model_dump(mode="json")},
        principal=principal,
        create=lambda: create_appeal(
            db,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        ),
    )


@user_router.post(
    "/account-appeals",
    response_model=TrustCaseDetail,
    status_code=201,
    dependencies=[
        Depends(rate_limit("trust.account_appeal.create", limit=3, window_seconds=86400))
    ],
)
def account_appeal_create(
    payload: AccountAppealCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> TrustCaseDetail:
    return _create_with_idempotency(
        db,
        scope="trust.account_appeal.create",
        idempotency_key=idempotency_key,
        payload={"kind": "account_appeal", **payload.model_dump(mode="json")},
        principal=principal,
        create=lambda: create_account_appeal(
            db,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        ),
    )


@user_router.get("/cases", response_model=TrustCaseListResponse)
def my_cases(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    kind: TrustCaseKind | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TrustCaseListResponse:
    return list_my_cases(db, principal=principal, kind=kind, page=page, page_size=page_size)


@user_router.get("/cases/{case_id}", response_model=TrustCaseDetail)
def my_case_detail(
    case_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> TrustCaseDetail:
    return get_case_detail(db, case_id, viewer_id=principal.user.id)


@admin_router.get("", response_model=TrustCaseListResponse)
def admin_case_list(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    kind: TrustCaseKind | None = None,
    status: TrustCaseStatus | None = None,
    query: Annotated[str | None, Query(max_length=128)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TrustCaseListResponse:
    del principal
    return list_admin_cases(
        db, kind=kind, status=status, query=query, page=page, page_size=page_size
    )


@admin_router.get("/{case_id}", response_model=TrustCaseDetail)
def admin_case_detail(
    case_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> TrustCaseDetail:
    del principal
    return get_case_detail(db, case_id)


@admin_router.post(
    "/{case_id}/transition",
    response_model=TrustCaseTransitionResponse,
    dependencies=[Depends(rate_limit("admin.trust_case.transition", limit=30, window_seconds=60))],
)
def admin_case_transition(
    case_id: str,
    payload: TrustCaseTransitionRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> TrustCaseTransitionResponse:
    request_body = payload.model_dump(mode="json")
    lease = acquire_idempotency(
        db,
        scope="admin.trust_case.transition",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest({"case_id": case_id, **request_body}),
    )
    if lease.cached_response is not None:
        return TrustCaseTransitionResponse.model_validate(lease.cached_response)
    try:
        response = transition_case(
            db,
            case_id=case_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        complete_idempotency(
            db,
            lease,
            response_status=200,
            response_body=response.model_dump(mode="json"),
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@admin_router.post(
    "/{case_id}/resolve",
    response_model=TrustCaseResolveResponse,
    dependencies=[Depends(rate_limit("admin.trust_case.resolve", limit=20, window_seconds=60))],
)
def admin_case_resolve(
    case_id: str,
    payload: TrustCaseResolveRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> TrustCaseResolveResponse:
    lease = acquire_idempotency(
        db,
        scope="admin.trust_case.resolve",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest({"case_id": case_id, **payload.model_dump(mode="json")}),
    )
    if lease.cached_response is not None:
        return TrustCaseResolveResponse.model_validate(lease.cached_response)
    try:
        response = resolve_case(
            db,
            settings=settings,
            case_id=case_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        complete_idempotency(
            db, lease, response_status=200, response_body=response.model_dump(mode="json")
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@admin_router.post(
    "/{case_id}/assign",
    response_model=TrustCaseAssignResponse,
    dependencies=[Depends(rate_limit("admin.trust_case.assign", limit=30, window_seconds=60))],
)
def admin_case_assign(
    case_id: str,
    payload: TrustCaseAssignRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> TrustCaseAssignResponse:
    lease = acquire_idempotency(
        db,
        scope="admin.trust_case.assign",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest({"case_id": case_id, **payload.model_dump(mode="json")}),
    )
    if lease.cached_response is not None:
        return TrustCaseAssignResponse.model_validate(lease.cached_response)
    try:
        response = assign_case(
            db,
            case_id=case_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        complete_idempotency(
            db, lease, response_status=200, response_body=response.model_dump(mode="json")
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@admin_router.post(
    "/{case_id}/reopen",
    response_model=TrustCaseReopenResponse,
    dependencies=[Depends(rate_limit("admin.trust_case.reopen", limit=30, window_seconds=60))],
)
def admin_case_reopen(
    case_id: str,
    payload: TrustCaseReopenRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> TrustCaseReopenResponse:
    lease = acquire_idempotency(
        db,
        scope="admin.trust_case.reopen",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest({"case_id": case_id, **payload.model_dump(mode="json")}),
    )
    if lease.cached_response is not None:
        return TrustCaseReopenResponse.model_validate(lease.cached_response)
    try:
        response = reopen_case(
            db,
            case_id=case_id,
            payload=payload,
            principal=principal,
            context=get_client_context(request),
        )
        complete_idempotency(
            db, lease, response_status=200, response_body=response.model_dump(mode="json")
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


def _create_with_idempotency(
    db: Session,
    *,
    scope: str,
    idempotency_key: str,
    payload: dict,
    principal: Principal,
    create,
) -> TrustCaseDetail:
    lease = acquire_idempotency(
        db,
        scope=scope,
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest(payload),
    )
    if lease.cached_response is not None:
        return TrustCaseDetail.model_validate(lease.cached_response)
    try:
        response = create()
        complete_idempotency(
            db,
            lease,
            response_status=201,
            response_body=response.model_dump(mode="json"),
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise
