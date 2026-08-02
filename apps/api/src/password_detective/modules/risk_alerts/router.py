from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
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
from password_detective.db.models.risk_alert import (
    RiskAlertKind,
    RiskAlertSeverity,
    RiskAlertStatus,
)
from password_detective.modules.auth.context import get_client_context
from password_detective.modules.auth.dependencies import Principal, require_admin_mfa
from password_detective.modules.risk_alerts.schemas import (
    RiskAlertDetail,
    RiskAlertListResponse,
    RiskAlertTransitionRequest,
    RiskAlertTransitionResponse,
)
from password_detective.modules.risk_alerts.service import (
    get_risk_alert_detail,
    list_risk_alerts,
    transition_risk_alert,
)

router = APIRouter(prefix="/admin/risk-alerts", tags=["admin-risk-alerts"])


@router.get("", response_model=RiskAlertListResponse)
def risk_alert_list(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    kind: RiskAlertKind | None = None,
    severity: RiskAlertSeverity | None = None,
    status: RiskAlertStatus | None = None,
    query: Annotated[str | None, Query(max_length=128)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RiskAlertListResponse:
    del principal
    return list_risk_alerts(
        db,
        kind=kind,
        severity=severity,
        status=status,
        query=query,
        page=page,
        page_size=page_size,
    )


@router.get("/{alert_id}", response_model=RiskAlertDetail)
def risk_alert_detail(
    alert_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
) -> RiskAlertDetail:
    del principal
    return get_risk_alert_detail(db, alert_id)


@router.post(
    "/{alert_id}/transition",
    response_model=RiskAlertTransitionResponse,
    dependencies=[Depends(rate_limit("admin.risk_alert.transition", limit=30, window_seconds=60))],
)
def risk_alert_transition(
    alert_id: str,
    payload: RiskAlertTransitionRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> RiskAlertTransitionResponse:
    request_body = payload.model_dump(mode="json")
    lease = acquire_idempotency(
        db,
        scope="admin.risk_alert.transition",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest({"alert_id": alert_id, **request_body}),
    )
    if lease.cached_response is not None:
        return RiskAlertTransitionResponse.model_validate(lease.cached_response)
    try:
        response = transition_risk_alert(
            db,
            alert_id=alert_id,
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
