from __future__ import annotations

import hashlib
import hmac
import secrets
from collections import Counter
from datetime import UTC, datetime, timedelta
from math import ceil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.security import hash_opaque_token
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.desktop_plugin import (
    DesktopPlugin,
    DesktopPluginArtifact,
    DesktopPluginDynamicReviewTask,
    DesktopPluginDynamicTaskStatus,
    DesktopPluginFindingSeverity,
    DesktopPluginInstallEvent,
    DesktopPluginReviewFinding,
    DesktopPluginReviewRun,
    DesktopPluginReviewRunStatus,
    DesktopPluginReviewStage,
    DesktopPluginRunnerAgent,
    DesktopPluginRunnerStatus,
    DesktopPluginVersion,
    DesktopPluginVersionStatus,
)
from password_detective.modules.desktop_plugins.review_policy import (
    DYNAMIC_REVIEW_ENGINE_VERSION,
    get_current_review_policy,
)
from password_detective.modules.desktop_plugins.schemas import (
    PluginDynamicTaskResponse,
    PluginReviewMetricsResponse,
    PluginRunnerCreateRequest,
    PluginRunnerHeartbeatRequest,
    PluginRunnerListResponse,
    PluginRunnerRegistrationResponse,
    PluginRunnerResponse,
    PluginRunnerTaskCompleteRequest,
    PluginRunnerTaskHeartbeatResponse,
    PluginRunnerTaskLeaseResponse,
)
from password_detective.modules.desktop_plugins.storage import DesktopPluginStorage

DYNAMIC_REVIEW_POLICY_VERSION = DYNAMIC_REVIEW_ENGINE_VERSION


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _runner_response(runner: DesktopPluginRunnerAgent) -> PluginRunnerResponse:
    return PluginRunnerResponse(
        id=runner.id,
        name=runner.name,
        architecture=runner.architecture,
        certificate_fingerprint=runner.certificate_fingerprint,
        status=runner.status.value,
        policy_version=runner.policy_version,
        image_digest=runner.image_digest,
        probe_version=runner.probe_version,
        last_heartbeat_at=runner.last_heartbeat_at,
        revoked_at=runner.revoked_at,
        created_at=runner.created_at,
    )


def create_runner(
    db: Session, *, payload: PluginRunnerCreateRequest, actor_user_id: str
) -> PluginRunnerRegistrationResponse:
    if db.scalar(
        select(DesktopPluginRunnerAgent.id).where(
            DesktopPluginRunnerAgent.certificate_fingerprint == payload.certificate_fingerprint
        )
    ):
        raise AppError(
            "desktop_plugin.runner_certificate_conflict",
            "Runner 证书指纹已登记",
            status_code=409,
        )
    raw_secret = "plugin_runner_" + secrets.token_urlsafe(36)
    runner = DesktopPluginRunnerAgent(
        name=payload.name,
        architecture=payload.architecture,
        certificate_fingerprint=payload.certificate_fingerprint,
        secret_hash=hash_opaque_token(raw_secret),
        status=DesktopPluginRunnerStatus.OFFLINE,
        created_by_user_id=actor_user_id,
    )
    db.add(runner)
    db.flush()
    write_audit_log(
        db,
        actor_id=actor_user_id,
        action="desktop_plugin.runner.created",
        target_type="desktop_plugin_runner",
        target_id=runner.id,
        result="success",
        details={"architecture": runner.architecture},
    )
    db.commit()
    db.refresh(runner)
    return PluginRunnerRegistrationResponse(
        **_runner_response(runner).model_dump(),
        runner_secret=raw_secret,
    )


def list_runners(db: Session) -> PluginRunnerListResponse:
    runners = list(
        db.scalars(
            select(DesktopPluginRunnerAgent).order_by(
                DesktopPluginRunnerAgent.created_at.desc(),
                DesktopPluginRunnerAgent.id,
            )
        ).all()
    )
    return PluginRunnerListResponse(items=[_runner_response(item) for item in runners])


def get_review_metrics(db: Session) -> PluginReviewMetricsResponse:
    now = utc_now()
    policy = get_current_review_policy(db)
    review_runs = list(db.scalars(select(DesktopPluginReviewRun)).all())
    versions = list(db.scalars(select(DesktopPluginVersion)).all())
    dynamic_rows = list(
        db.execute(
            select(DesktopPluginDynamicReviewTask, DesktopPluginArtifact).join(
                DesktopPluginArtifact,
                DesktopPluginArtifact.id == DesktopPluginDynamicReviewTask.artifact_id,
            )
        ).all()
    )
    runners = list(db.scalars(select(DesktopPluginRunnerAgent)).all())

    review_run_counts = Counter(run.status.value for run in review_runs)
    version_status_counts = Counter(version.status.value for version in versions)
    dynamic_task_counts = Counter(task.status.value for task, _ in dynamic_rows)
    runner_status_counts: Counter[str] = Counter()
    runner_capacity_by_architecture: Counter[str] = Counter()
    runner_active_by_architecture: Counter[str] = Counter()
    for runner in runners:
        effective_status = runner.status
        if (
            effective_status
            not in {DesktopPluginRunnerStatus.REVOKED, DesktopPluginRunnerStatus.OFFLINE}
            and (
                runner.last_heartbeat_at is None
                or (now - _aware(runner.last_heartbeat_at)).total_seconds()
                > policy.runner_offline_seconds
            )
        ):
            effective_status = DesktopPluginRunnerStatus.OFFLINE
        runner_status_counts[effective_status.value] += 1
        if effective_status in {DesktopPluginRunnerStatus.READY, DesktopPluginRunnerStatus.BUSY}:
            runner_capacity_by_architecture[runner.architecture] += 1
        if effective_status == DesktopPluginRunnerStatus.BUSY:
            runner_active_by_architecture[runner.architecture] += 1

    queue_depth_by_architecture: Counter[str] = Counter()
    for task, artifact in dynamic_rows:
        if task.status == DesktopPluginDynamicTaskStatus.QUEUED:
            queue_depth_by_architecture[artifact.architecture] += 1

    queued_at = [
        run.created_at
        for run in review_runs
        if run.status == DesktopPluginReviewRunStatus.QUEUED
    ] + [
        task.created_at
        for task, _ in dynamic_rows
        if task.status == DesktopPluginDynamicTaskStatus.QUEUED
    ]
    oldest_queued_seconds = (
        max(0.0, (now - min(_aware(value) for value in queued_at)).total_seconds())
        if queued_at
        else None
    )
    review_durations = sorted(
        max(0.0, (_aware(run.completed_at) - _aware(run.started_at)).total_seconds())
        for run in review_runs
        if run.started_at is not None and run.completed_at is not None
    )
    completed_cutoff = now - timedelta(hours=24)
    return PluginReviewMetricsResponse(
        generated_at=now,
        review_run_counts=dict(review_run_counts),
        version_status_counts=dict(version_status_counts),
        dynamic_task_counts=dict(dynamic_task_counts),
        runner_status_counts=dict(runner_status_counts),
        runner_capacity_by_architecture=dict(runner_capacity_by_architecture),
        runner_active_by_architecture=dict(runner_active_by_architecture),
        queue_depth_by_architecture=dict(queue_depth_by_architecture),
        oldest_queued_seconds=oldest_queued_seconds,
        average_review_seconds=(
            sum(review_durations) / len(review_durations) if review_durations else None
        ),
        p95_review_seconds=(
            review_durations[ceil(len(review_durations) * 0.95) - 1]
            if review_durations
            else None
        ),
        completed_last_24_hours=sum(
            run.completed_at is not None and _aware(run.completed_at) >= completed_cutoff
            for run in review_runs
        ),
        install_events_last_24_hours=sum(
            _aware(event.created_at) >= completed_cutoff
            for event in db.scalars(select(DesktopPluginInstallEvent)).all()
        ),
    )


def revoke_runner(
    db: Session, *, runner_id: str, actor_user_id: str
) -> PluginRunnerResponse:
    runner = db.scalar(
        select(DesktopPluginRunnerAgent)
        .where(DesktopPluginRunnerAgent.id == runner_id)
        .with_for_update()
    )
    if runner is None:
        raise AppError("desktop_plugin.runner_not_found", "Runner 不存在", status_code=404)
    now = utc_now()
    runner.status = DesktopPluginRunnerStatus.REVOKED
    runner.revoked_at = now
    runner.secret_hash = hash_opaque_token("revoked-" + secrets.token_urlsafe(36))
    for task in db.scalars(
        select(DesktopPluginDynamicReviewTask)
        .where(
            DesktopPluginDynamicReviewTask.runner_id == runner.id,
            DesktopPluginDynamicReviewTask.status == DesktopPluginDynamicTaskStatus.LEASED,
        )
        .with_for_update()
    ).all():
        task.status = DesktopPluginDynamicTaskStatus.QUEUED
        task.runner_id = None
        task.lease_expires_at = None
        task.task_token_hash = None
        task.task_token_expires_at = None
        task.error_code = "desktop_plugin.runner_revoked"
        task.error_message = "Runner 已撤销，任务将重新分配。"
    write_audit_log(
        db,
        actor_id=actor_user_id,
        action="desktop_plugin.runner.revoked",
        target_type="desktop_plugin_runner",
        target_id=runner.id,
        result="success",
        details={},
    )
    db.commit()
    db.refresh(runner)
    return _runner_response(runner)


def authenticate_runner(
    db: Session,
    *,
    runner_id: str,
    certificate_fingerprint: str,
    raw_secret: str,
    certificate_verified: bool,
) -> DesktopPluginRunnerAgent:
    if not certificate_verified:
        raise AppError(
            "desktop_plugin.runner_mtls_required", "Runner 必须通过 mTLS 验证", status_code=401
        )
    runner = db.get(DesktopPluginRunnerAgent, runner_id)
    if (
        runner is None
        or runner.status == DesktopPluginRunnerStatus.REVOKED
        or not hmac.compare_digest(runner.certificate_fingerprint, certificate_fingerprint.lower())
        or not hmac.compare_digest(runner.secret_hash, hash_opaque_token(raw_secret))
    ):
        raise AppError(
            "desktop_plugin.runner_authentication_failed", "Runner 身份验证失败", status_code=401
        )
    return runner


def runner_heartbeat(
    db: Session,
    *,
    runner: DesktopPluginRunnerAgent,
    payload: PluginRunnerHeartbeatRequest,
) -> PluginRunnerResponse:
    now = utc_now()
    runner.policy_version = payload.policy_version
    runner.image_digest = payload.image_digest
    runner.probe_version = payload.probe_version
    runner.last_heartbeat_at = now
    leased_tasks = list(
        db.scalars(
            select(DesktopPluginDynamicReviewTask).where(
            DesktopPluginDynamicReviewTask.runner_id == runner.id,
            DesktopPluginDynamicReviewTask.status == DesktopPluginDynamicTaskStatus.LEASED,
            DesktopPluginDynamicReviewTask.lease_expires_at.is_not(None),
            )
        ).all()
    )
    has_lease = any(_aware(task.lease_expires_at) > now for task in leased_tasks)
    runner.status = (
        DesktopPluginRunnerStatus.BUSY
        if has_lease
        else DesktopPluginRunnerStatus.READY
        if payload.fresh_environment_ready
        and payload.policy_version == DYNAMIC_REVIEW_POLICY_VERSION
        else DesktopPluginRunnerStatus.OFFLINE
    )
    db.commit()
    db.refresh(runner)
    return _runner_response(runner)


def enqueue_dynamic_tasks(
    db: Session,
    *,
    review_run: DesktopPluginReviewRun,
    artifacts: list[DesktopPluginArtifact],
) -> None:
    for artifact in artifacts:
        if db.scalar(
            select(DesktopPluginDynamicReviewTask.id).where(
                DesktopPluginDynamicReviewTask.review_run_id == review_run.id,
                DesktopPluginDynamicReviewTask.artifact_id == artifact.id,
            )
        ):
            continue
        db.add(
            DesktopPluginDynamicReviewTask(
                review_run_id=review_run.id,
                artifact_id=artifact.id,
                status=DesktopPluginDynamicTaskStatus.QUEUED,
                attempt=0,
                result_summary_json={},
            )
        )


def _task_response(
    task: DesktopPluginDynamicReviewTask, artifact: DesktopPluginArtifact
) -> PluginDynamicTaskResponse:
    return PluginDynamicTaskResponse(
        id=task.id,
        artifact_id=task.artifact_id,
        architecture=artifact.architecture,
        status=task.status.value,
        runner_id=task.runner_id,
        attempt=task.attempt,
        lease_expires_at=task.lease_expires_at,
        evidence_complete=task.evidence_complete,
        fresh_environment=task.fresh_environment,
        destruction_proof_sha256=task.destruction_proof_sha256,
        error_code=task.error_code,
        error_message=task.error_message,
        result_summary=task.result_summary_json,
        completed_at=task.completed_at,
        created_at=task.created_at,
    )


def list_dynamic_tasks(
    db: Session, *, review_run_id: str
) -> list[PluginDynamicTaskResponse]:
    rows = list(
        db.execute(
            select(DesktopPluginDynamicReviewTask, DesktopPluginArtifact)
            .join(
                DesktopPluginArtifact,
                DesktopPluginArtifact.id == DesktopPluginDynamicReviewTask.artifact_id,
            )
            .where(DesktopPluginDynamicReviewTask.review_run_id == review_run_id)
            .order_by(DesktopPluginArtifact.architecture)
        ).all()
    )
    return [_task_response(task, artifact) for task, artifact in rows]


def _refresh_review_run(db: Session, review_run_id: str) -> None:
    run = db.get(DesktopPluginReviewRun, review_run_id)
    if run is None:
        return
    version = db.get(DesktopPluginVersion, run.version_id)
    if version is None:
        return
    tasks = list(
        db.scalars(
            select(DesktopPluginDynamicReviewTask).where(
                DesktopPluginDynamicReviewTask.review_run_id == run.id
            )
        ).all()
    )
    dynamic_status = "pending"
    if tasks and all(task.status == DesktopPluginDynamicTaskStatus.PASSED for task in tasks):
        run.status = DesktopPluginReviewRunStatus.PASSED
        run.completed_at = utc_now()
        version.status = DesktopPluginVersionStatus.MANUAL_REVIEW_READY
        version.version += 1
        dynamic_status = "passed"
    elif any(task.status == DesktopPluginDynamicTaskStatus.BLOCKED for task in tasks):
        run.status = DesktopPluginReviewRunStatus.FAILED
        run.completed_at = utc_now()
        version.status = DesktopPluginVersionStatus.AUTO_REVIEW_FAILED
        version.version += 1
        dynamic_status = "blocked"
    elif any(
        task.status == DesktopPluginDynamicTaskStatus.INFRASTRUCTURE_FAILED for task in tasks
    ):
        run.status = DesktopPluginReviewRunStatus.INFRASTRUCTURE_FAILED
        run.completed_at = utc_now()
        version.status = DesktopPluginVersionStatus.AUTO_REVIEW_FAILED
        version.version += 1
        dynamic_status = "infrastructure_failed"
    else:
        run.status = DesktopPluginReviewRunStatus.RUNNING
        version.status = DesktopPluginVersionStatus.AUTO_REVIEW_RUNNING
    run.summary_json = {
        **run.summary_json,
        "static_status": "passed",
        "dynamic_status": dynamic_status,
        "dynamic_task_count": len(tasks),
        "dynamic_completed_count": sum(
            task.status
            in {
                DesktopPluginDynamicTaskStatus.PASSED,
                DesktopPluginDynamicTaskStatus.BLOCKED,
                DesktopPluginDynamicTaskStatus.INFRASTRUCTURE_FAILED,
            }
            for task in tasks
        ),
    }


def _recover_expired_tasks(
    db: Session, *, architecture: str, maximum_attempts: int
) -> None:
    now = utc_now()
    tasks = list(
        db.scalars(
            select(DesktopPluginDynamicReviewTask)
            .join(
                DesktopPluginArtifact,
                DesktopPluginArtifact.id == DesktopPluginDynamicReviewTask.artifact_id,
            )
            .where(
                DesktopPluginDynamicReviewTask.status == DesktopPluginDynamicTaskStatus.LEASED,
                DesktopPluginDynamicReviewTask.lease_expires_at.is_not(None),
                DesktopPluginArtifact.architecture == architecture,
            )
            .with_for_update(skip_locked=True)
        ).all()
    )
    for task in tasks:
        if _aware(task.lease_expires_at) > now:
            continue
        task.runner_id = None
        task.lease_expires_at = None
        task.task_token_hash = None
        task.task_token_expires_at = None
        if task.attempt >= maximum_attempts:
            task.status = DesktopPluginDynamicTaskStatus.INFRASTRUCTURE_FAILED
            task.error_code = "desktop_plugin.dynamic_runner_lease_exhausted"
            task.error_message = "Windows Runner 多次失联，动态审核失败关闭。"
            task.completed_at = now
        else:
            task.status = DesktopPluginDynamicTaskStatus.QUEUED
            task.error_code = "desktop_plugin.dynamic_runner_lease_expired"
            task.error_message = "Windows Runner 租约已过期，任务将重试。"
        _refresh_review_run(db, task.review_run_id)


def lease_dynamic_task(
    db: Session,
    *,
    runner: DesktopPluginRunnerAgent,
    artifact_url_builder,
) -> PluginRunnerTaskLeaseResponse | None:
    if (
        runner.status != DesktopPluginRunnerStatus.READY
        or runner.policy_version != DYNAMIC_REVIEW_POLICY_VERSION
        or not runner.image_digest
        or not runner.probe_version
    ):
        raise AppError(
            "desktop_plugin.runner_not_ready", "Runner 尚未通过健康检查", status_code=409
        )
    policy = get_current_review_policy(db)
    _recover_expired_tasks(
        db,
        architecture=runner.architecture,
        maximum_attempts=policy.maximum_dynamic_attempts,
    )
    db.flush()
    now = utc_now()
    row = db.execute(
        select(
            DesktopPluginDynamicReviewTask,
            DesktopPluginArtifact,
            DesktopPluginReviewRun,
            DesktopPluginVersion,
            DesktopPlugin,
        )
        .join(
            DesktopPluginArtifact,
            DesktopPluginArtifact.id == DesktopPluginDynamicReviewTask.artifact_id,
        )
        .join(
            DesktopPluginReviewRun,
            DesktopPluginReviewRun.id == DesktopPluginDynamicReviewTask.review_run_id,
        )
        .join(
            DesktopPluginVersion,
            DesktopPluginVersion.id == DesktopPluginReviewRun.version_id,
        )
        .join(DesktopPlugin, DesktopPlugin.id == DesktopPluginVersion.plugin_id)
        .where(
            DesktopPluginDynamicReviewTask.status == DesktopPluginDynamicTaskStatus.QUEUED,
            DesktopPluginArtifact.architecture == runner.architecture,
        )
        .order_by(DesktopPluginDynamicReviewTask.created_at, DesktopPluginDynamicReviewTask.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).one_or_none()
    if row is None:
        db.commit()
        return None
    task, artifact, run, version, plugin = row
    raw_token = "plugin_task_" + secrets.token_urlsafe(36)
    expires_at = now + timedelta(seconds=policy.task_token_seconds)
    task.status = DesktopPluginDynamicTaskStatus.LEASED
    task.runner_id = runner.id
    task.attempt += 1
    task.leased_at = now
    task.lease_expires_at = now + timedelta(seconds=policy.dynamic_lease_seconds)
    task.task_token_hash = hash_opaque_token(raw_token)
    task.task_token_expires_at = expires_at
    runner.status = DesktopPluginRunnerStatus.BUSY
    runner.last_heartbeat_at = now
    db.commit()
    return PluginRunnerTaskLeaseResponse(
        task_id=task.id,
        review_run_id=run.id,
        plugin_id=plugin.id,
        plugin_slug=plugin.slug,
        version_id=version.id,
        semver=version.semver,
        artifact_id=artifact.id,
        architecture=artifact.architecture,
        artifact_sha256=artifact.sha256,
        artifact_size_bytes=artifact.size_bytes,
        requested_capabilities=list(version.requested_capabilities),
        policy_version=DYNAMIC_REVIEW_POLICY_VERSION,
        artifact_url=str(artifact_url_builder(task.id)),
        task_token=raw_token,
        expires_at=expires_at,
    )


def authenticate_task(
    db: Session,
    *,
    runner: DesktopPluginRunnerAgent,
    task_id: str,
    raw_task_token: str,
    lock: bool = False,
) -> DesktopPluginDynamicReviewTask:
    statement = select(DesktopPluginDynamicReviewTask).where(
        DesktopPluginDynamicReviewTask.id == task_id
    )
    if lock:
        statement = statement.with_for_update()
    task = db.scalar(statement)
    now = utc_now()
    if (
        task is None
        or task.status != DesktopPluginDynamicTaskStatus.LEASED
        or task.runner_id != runner.id
        or task.task_token_hash is None
        or task.task_token_expires_at is None
        or _aware(task.task_token_expires_at) <= now
        or not hmac.compare_digest(task.task_token_hash, hash_opaque_token(raw_task_token))
    ):
        raise AppError(
            "desktop_plugin.dynamic_task_authentication_failed",
            "动态审核任务凭据无效或已过期",
            status_code=401,
        )
    return task


def dynamic_task_artifact(
    db: Session,
    settings: Settings,
    *,
    task: DesktopPluginDynamicReviewTask,
) -> tuple[DesktopPluginArtifact, Path]:
    artifact = db.get(DesktopPluginArtifact, task.artifact_id)
    if artifact is None or not artifact.storage_key:
        raise AppError(
            "desktop_plugin.review_artifact_missing", "动态审核制品不存在", status_code=404
        )
    path = DesktopPluginStorage(settings).quarantine_path(artifact.storage_key)
    if not path.is_file():
        raise AppError(
            "desktop_plugin.review_artifact_missing", "动态审核制品不存在", status_code=404
        )
    return artifact, path


def heartbeat_dynamic_task(
    db: Session,
    *,
    task: DesktopPluginDynamicReviewTask,
    runner: DesktopPluginRunnerAgent,
) -> PluginRunnerTaskHeartbeatResponse:
    now = utc_now()
    policy = get_current_review_policy(db)
    task.lease_expires_at = now + timedelta(seconds=policy.dynamic_lease_seconds)
    runner.last_heartbeat_at = now
    runner.status = DesktopPluginRunnerStatus.BUSY
    db.commit()
    return PluginRunnerTaskHeartbeatResponse(
        task_id=task.id,
        lease_expires_at=task.lease_expires_at,
    )


def complete_dynamic_task(
    db: Session,
    *,
    task: DesktopPluginDynamicReviewTask,
    runner: DesktopPluginRunnerAgent,
    payload: PluginRunnerTaskCompleteRequest,
) -> PluginDynamicTaskResponse:
    now = utc_now()
    policy = get_current_review_policy(db)
    artifact = db.get(DesktopPluginArtifact, task.artifact_id)
    expected_destruction_proof = (
        hashlib.sha256(
            f"pdpp-dynamic-destroyed-v1\n{task.id}\n".encode()
        ).hexdigest()
    )
    required_summary = (
        payload.summary.get("appcontainer") is True
        and payload.summary.get("network_connected") is False
        and payload.summary.get("child_process_count") == 0
        and payload.summary.get("workspace_deleted") is True
    )
    valid_pass = (
        payload.outcome == "passed"
        and payload.evidence_complete
        and payload.fresh_environment
        and payload.destruction_proof_sha256 == expected_destruction_proof
        and required_summary
        and not any(finding.blocked for finding in payload.findings)
    )
    db.query(DesktopPluginReviewFinding).filter(
        DesktopPluginReviewFinding.dynamic_task_id == task.id,
    ).delete(synchronize_session=False)
    for finding in payload.findings:
        db.add(
            DesktopPluginReviewFinding(
                review_run_id=task.review_run_id,
                dynamic_task_id=task.id,
                stage=DesktopPluginReviewStage(finding.stage),
                rule_id=finding.rule_id,
                severity=DesktopPluginFindingSeverity(finding.severity),
                title=finding.title,
                detail=finding.detail,
                file_path=finding.file_path,
                evidence_json=finding.evidence,
                blocked=finding.blocked,
                developer_visible=True,
            )
        )
    task.result_summary_json = payload.summary
    task.evidence_complete = payload.evidence_complete
    task.fresh_environment = payload.fresh_environment
    task.destruction_proof_sha256 = payload.destruction_proof_sha256
    task.error_code = payload.error_code
    task.error_message = payload.error_message
    task.task_token_hash = None
    task.task_token_expires_at = None
    task.lease_expires_at = None
    task.completed_at = now
    if valid_pass:
        task.status = DesktopPluginDynamicTaskStatus.PASSED
    elif (
        payload.outcome == "infrastructure_failed"
        and task.attempt < policy.maximum_dynamic_attempts
    ):
        task.status = DesktopPluginDynamicTaskStatus.QUEUED
        task.runner_id = None
        task.completed_at = None
        task.error_message = "Windows Runner 基础设施失败，任务将重试。"
    elif payload.outcome == "infrastructure_failed":
        task.status = DesktopPluginDynamicTaskStatus.INFRASTRUCTURE_FAILED
    else:
        task.status = DesktopPluginDynamicTaskStatus.BLOCKED
        if payload.outcome == "passed":
            task.error_code = "desktop_plugin.dynamic_evidence_incomplete"
            task.error_message = "动态审核证据不完整，审核失败关闭。"
    runner.status = DesktopPluginRunnerStatus.READY
    runner.last_heartbeat_at = now
    _refresh_review_run(db, task.review_run_id)
    write_audit_log(
        db,
        actor_id=None,
        action="desktop_plugin.dynamic_review.completed",
        target_type="desktop_plugin_dynamic_task",
        target_id=task.id,
        result="success" if task.status == DesktopPluginDynamicTaskStatus.PASSED else "failure",
        details={
            "runner_id": runner.id,
            "status": task.status.value,
            "attempt": task.attempt,
            "evidence_complete": task.evidence_complete,
            "fresh_environment": task.fresh_environment,
        },
    )
    db.commit()
    if artifact is None:
        raise AppError("desktop_plugin.artifact_missing", "插件制品不存在", status_code=404)
    return _task_response(task, artifact)
