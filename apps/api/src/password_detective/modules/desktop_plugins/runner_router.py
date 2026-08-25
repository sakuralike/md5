from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.errors import AppError
from password_detective.core.idempotency import (
    abandon_idempotency,
    acquire_idempotency,
    complete_idempotency,
    payload_digest,
    require_idempotency_key,
)
from password_detective.db.dependencies import get_db
from password_detective.db.models.desktop_plugin import DesktopPluginRunnerAgent
from password_detective.modules.auth.dependencies import Principal, require_admin_only_mfa
from password_detective.modules.desktop_plugins.runner_service import (
    authenticate_runner,
    authenticate_task,
    complete_dynamic_task,
    create_runner,
    dynamic_task_artifact,
    heartbeat_dynamic_task,
    lease_dynamic_task,
    list_runners,
    revoke_runner,
    runner_heartbeat,
)
from password_detective.modules.desktop_plugins.schemas import (
    PluginDynamicTaskResponse,
    PluginRunnerCreateRequest,
    PluginRunnerHeartbeatRequest,
    PluginRunnerListResponse,
    PluginRunnerRegistrationResponse,
    PluginRunnerResponse,
    PluginRunnerTaskCompleteRequest,
    PluginRunnerTaskHeartbeatResponse,
    PluginRunnerTaskLeaseResponse,
)

admin_router = APIRouter(prefix="/admin/plugin-review-runners", tags=["管理端·插件执行器"])
runner_router = APIRouter(
    prefix="/plugin-runner",
    tags=["插件动态审核执行器"],
    include_in_schema=False,
)
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class RunnerPrincipal:
    runner: DesktopPluginRunnerAgent


def get_runner_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    runner_id: Annotated[str, Header(alias="X-Plugin-Runner-Id")],
    certificate_fingerprint: Annotated[
        str, Header(alias="X-Plugin-Runner-Certificate-SHA256")
    ],
    certificate_verified: Annotated[str, Header(alias="X-Client-Certificate-Verified")],
    db: Annotated[Session, Depends(get_db)],
) -> RunnerPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            "desktop_plugin.runner_authentication_required",
            "需要 Runner 身份凭据",
            status_code=401,
        )
    return RunnerPrincipal(
        authenticate_runner(
            db,
            runner_id=runner_id,
            certificate_fingerprint=certificate_fingerprint,
            raw_secret=credentials.credentials,
            certificate_verified=certificate_verified.upper() == "SUCCESS",
        )
    )


@admin_router.post("", response_model=PluginRunnerRegistrationResponse, status_code=201)
def register_plugin_review_runner(
    payload: PluginRunnerCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_only_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    ) -> PluginRunnerRegistrationResponse:
    lease = acquire_idempotency(
        db,
        scope="admin.plugin_review_runner.create",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest(payload.model_dump()),
    )
    if lease.cached_response is not None:
        cached = PluginRunnerRegistrationResponse.model_validate(lease.cached_response)
        return cached.model_copy(update={"runner_secret": None})
    try:
        response = create_runner(db, payload=payload, actor_user_id=principal.user.id)
        stored_response = response.model_copy(update={"runner_secret": None})
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_201_CREATED,
            response_body=stored_response.model_dump(mode="json"),
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@admin_router.get("", response_model=PluginRunnerListResponse)
def plugin_review_runners(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_admin_only_mfa)],
) -> PluginRunnerListResponse:
    return list_runners(db)


@admin_router.post("/{runner_id}/revoke", response_model=PluginRunnerResponse)
def revoke_plugin_review_runner(
    runner_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_only_mfa)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> PluginRunnerResponse:
    lease = acquire_idempotency(
        db,
        scope="admin.plugin_review_runner.revoke",
        owner_key=principal.user.id,
        idempotency_key=idempotency_key,
        request_hash=payload_digest({"runner_id": runner_id}),
    )
    if lease.cached_response is not None:
        return PluginRunnerResponse.model_validate(lease.cached_response)
    try:
        response = revoke_runner(db, runner_id=runner_id, actor_user_id=principal.user.id)
        complete_idempotency(
            db,
            lease,
            response_status=status.HTTP_200_OK,
            response_body=response.model_dump(mode="json"),
        )
        return response
    except Exception:
        db.rollback()
        abandon_idempotency(db, lease)
        raise


@runner_router.post("/heartbeat", response_model=PluginRunnerResponse)
def plugin_runner_heartbeat(
    payload: PluginRunnerHeartbeatRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[RunnerPrincipal, Depends(get_runner_principal)],
) -> PluginRunnerResponse:
    return runner_heartbeat(db, runner=principal.runner, payload=payload)


@runner_router.post("/tasks/lease", response_model=PluginRunnerTaskLeaseResponse | None)
def lease_plugin_dynamic_review_task(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[RunnerPrincipal, Depends(get_runner_principal)],
) -> PluginRunnerTaskLeaseResponse | None:
    return lease_dynamic_task(
        db,
        runner=principal.runner,
        artifact_url_builder=lambda task_id: request.url_for(
            "download_dynamic_review_artifact", task_id=task_id
        ),
    )


def _task(
    task_id: str,
    task_token: str,
    db: Session,
    principal: RunnerPrincipal,
    *,
    lock: bool,
):
    return authenticate_task(
        db,
        runner=principal.runner,
        task_id=task_id,
        raw_task_token=task_token,
        lock=lock,
    )


@runner_router.get("/tasks/{task_id}/artifact", name="download_dynamic_review_artifact")
def download_dynamic_review_artifact(
    task_id: str,
    task_token: Annotated[str, Header(alias="X-Plugin-Task-Token")],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[RunnerPrincipal, Depends(get_runner_principal)],
) -> FileResponse:
    task = _task(task_id, task_token, db, principal, lock=False)
    artifact, path = dynamic_task_artifact(db, settings, task=task)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=artifact.artifact_filename,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@runner_router.post(
    "/tasks/{task_id}/heartbeat", response_model=PluginRunnerTaskHeartbeatResponse
)
def heartbeat_plugin_dynamic_review_task(
    task_id: str,
    task_token: Annotated[str, Header(alias="X-Plugin-Task-Token")],
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[RunnerPrincipal, Depends(get_runner_principal)],
) -> PluginRunnerTaskHeartbeatResponse:
    task = _task(task_id, task_token, db, principal, lock=True)
    return heartbeat_dynamic_task(db, task=task, runner=principal.runner)


@runner_router.post("/tasks/{task_id}/complete", response_model=PluginDynamicTaskResponse)
def complete_plugin_dynamic_review_task(
    task_id: str,
    payload: PluginRunnerTaskCompleteRequest,
    task_token: Annotated[str, Header(alias="X-Plugin-Task-Token")],
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[RunnerPrincipal, Depends(get_runner_principal)],
) -> PluginDynamicTaskResponse:
    task = _task(task_id, task_token, db, principal, lock=True)
    return complete_dynamic_task(
        db,
        task=task,
        runner=principal.runner,
        payload=payload,
    )
