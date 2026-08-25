from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.desktop_plugin import (
    DesktopPlugin,
    DesktopPluginArtifact,
    DesktopPluginReviewFinding,
    DesktopPluginReviewRun,
    DesktopPluginReviewRunStatus,
    DesktopPluginSigningKey,
    DesktopPluginVersion,
    DesktopPluginVersionStatus,
)
from password_detective.modules.desktop_plugins.review_policy import get_current_review_policy
from password_detective.modules.desktop_plugins.runner_service import (
    enqueue_dynamic_tasks,
    list_dynamic_tasks,
)
from password_detective.modules.desktop_plugins.schemas import (
    PluginStaticFindingResponse,
    PluginStaticReviewReportResponse,
    PluginStaticReviewRunResponse,
)
from password_detective.modules.desktop_plugins.static_review import (
    StaticReviewInfrastructureError,
    inspect_version_artifacts,
)
from password_detective.modules.desktop_plugins.storage import DesktopPluginStorage


def enqueue_static_review(db: Session, *, version: DesktopPluginVersion) -> DesktopPluginReviewRun:
    policy = get_current_review_policy(db)
    run = DesktopPluginReviewRun(
        version_id=version.id,
        policy_version=policy.policy_version,
        status=DesktopPluginReviewRunStatus.QUEUED,
        attempt=0,
        summary_json={},
    )
    db.add(run)
    db.flush()
    return run


def _finding_response(finding: DesktopPluginReviewFinding) -> PluginStaticFindingResponse:
    return PluginStaticFindingResponse(
        id=finding.id,
        stage=finding.stage.value,
        rule_id=finding.rule_id,
        severity=finding.severity.value,
        title=finding.title,
        detail=finding.detail,
        file_path=finding.file_path,
        evidence=finding.evidence_json,
        blocked=finding.blocked,
        created_at=finding.created_at,
    )


def list_review_runs(
    db: Session, *, version_id: str, developer_visible_only: bool
) -> list[PluginStaticReviewRunResponse]:
    runs = list(
        db.scalars(
            select(DesktopPluginReviewRun)
            .where(DesktopPluginReviewRun.version_id == version_id)
            .order_by(DesktopPluginReviewRun.created_at.desc(), DesktopPluginReviewRun.id.desc())
        ).all()
    )
    responses: list[PluginStaticReviewRunResponse] = []
    for run in runs:
        finding_statement = select(DesktopPluginReviewFinding).where(
            DesktopPluginReviewFinding.review_run_id == run.id
        )
        if developer_visible_only:
            finding_statement = finding_statement.where(
                DesktopPluginReviewFinding.developer_visible.is_(True)
            )
        findings = list(
            db.scalars(
                finding_statement.order_by(
                    DesktopPluginReviewFinding.created_at,
                    DesktopPluginReviewFinding.rule_id,
                )
            ).all()
        )
        responses.append(
            PluginStaticReviewRunResponse(
                id=run.id,
                policy_version=run.policy_version,
                status=run.status.value,
                attempt=run.attempt,
                summary=run.summary_json,
                error_code=run.error_code,
                error_message=run.error_message,
                started_at=run.started_at,
                completed_at=run.completed_at,
                created_at=run.created_at,
                findings=[_finding_response(item) for item in findings],
                dynamic_tasks=list_dynamic_tasks(db, review_run_id=run.id),
            )
        )
    return responses


def get_developer_review_report(
    db: Session, *, version_id: str, owner_user_id: str
) -> PluginStaticReviewReportResponse:
    row = db.execute(
        select(DesktopPluginVersion, DesktopPlugin)
        .join(DesktopPlugin, DesktopPlugin.id == DesktopPluginVersion.plugin_id)
        .where(
            DesktopPluginVersion.id == version_id,
            DesktopPlugin.owner_user_id == owner_user_id,
        )
    ).one_or_none()
    if row is None:
        from password_detective.core.errors import AppError

        raise AppError("desktop_plugin.version_not_found", "插件版本不存在", status_code=404)
    version = row[0]
    return PluginStaticReviewReportResponse(
        version_id=version.id,
        version_status=version.status.value,
        runs=list_review_runs(db, version_id=version.id, developer_visible_only=True),
    )


def _mark_infrastructure_failure(
    run: DesktopPluginReviewRun,
    version: DesktopPluginVersion,
    *,
    code: str,
    safe_message: str,
    maximum_attempts: int,
) -> bool:
    run.error_code = code[:128]
    run.error_message = safe_message[:2_000]
    run.summary_json = {
        "policy_version": run.policy_version,
        "blocked": True,
        "infrastructure_failure": True,
    }
    run.worker_id = None
    run.lease_expires_at = None
    if run.attempt < maximum_attempts:
        run.status = DesktopPluginReviewRunStatus.QUEUED
        version.status = DesktopPluginVersionStatus.REVIEW_QUEUED
        return True
    run.status = DesktopPluginReviewRunStatus.INFRASTRUCTURE_FAILED
    run.completed_at = utc_now()
    version.status = DesktopPluginVersionStatus.AUTO_REVIEW_FAILED
    return False


def process_pending_static_reviews(
    db: Session,
    settings: Settings,
    *,
    worker_id: str = "plugin-static-review-worker",
    limit: int = 10,
) -> dict[str, int]:
    processed = passed = failed = retry_scheduled = 0
    policy = get_current_review_policy(db)
    storage = DesktopPluginStorage(settings)
    handled_ids: set[str] = set()
    for _ in range(limit):
        now = utc_now()
        run = db.scalar(
            select(DesktopPluginReviewRun)
            .where(
                DesktopPluginReviewRun.id.not_in(handled_ids) if handled_ids else True,
                or_(
                    DesktopPluginReviewRun.status == DesktopPluginReviewRunStatus.QUEUED,
                    (
                        (DesktopPluginReviewRun.status == DesktopPluginReviewRunStatus.RUNNING)
                        & DesktopPluginReviewRun.lease_expires_at.is_not(None)
                        & (DesktopPluginReviewRun.lease_expires_at <= now)
                    ),
                )
            )
            .order_by(DesktopPluginReviewRun.created_at, DesktopPluginReviewRun.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if run is None:
            break
        handled_ids.add(run.id)
        version = db.scalar(
            select(DesktopPluginVersion)
            .where(DesktopPluginVersion.id == run.version_id)
            .with_for_update()
        )
        if version is None:
            run.status = DesktopPluginReviewRunStatus.CANCELLED
            run.error_code = "desktop_plugin.version_missing"
            run.error_message = "插件版本不存在。"
            run.completed_at = now
            db.commit()
            processed += 1
            continue
        run.status = DesktopPluginReviewRunStatus.RUNNING
        run.attempt += 1
        run.worker_id = worker_id[:128]
        run.lease_expires_at = now + timedelta(seconds=policy.static_lease_seconds)
        run.started_at = now
        run.completed_at = None
        run.error_code = None
        run.error_message = None
        version.status = DesktopPluginVersionStatus.AUTO_REVIEW_RUNNING
        version.version += 1
        db.commit()

        try:
            version = db.get(DesktopPluginVersion, run.version_id)
            run = db.get(DesktopPluginReviewRun, run.id)
            if version is None or run is None:
                continue
            plugin = db.get(DesktopPlugin, version.plugin_id)
            signing_key = db.get(DesktopPluginSigningKey, version.signing_key_id)
            artifacts = list(
                db.scalars(
                    select(DesktopPluginArtifact).where(
                        DesktopPluginArtifact.plugin_version_id == version.id
                    )
                ).all()
            )
            if plugin is None or signing_key is None or not artifacts:
                raise StaticReviewInfrastructureError(
                    "desktop_plugin.review_context_missing", "审核上下文暂不可用。"
                )
            db.execute(
                delete(DesktopPluginReviewFinding).where(
                    DesktopPluginReviewFinding.review_run_id == run.id
                )
            )
            result = inspect_version_artifacts(
                storage=storage,
                plugin=plugin,
                version=version,
                signing_key=signing_key,
                artifacts=artifacts,
                max_expanded_bytes=settings.desktop_plugin_max_expanded_bytes,
            )
            for finding in result.findings:
                db.add(
                    DesktopPluginReviewFinding(
                        review_run_id=run.id,
                        stage=finding.stage,
                        rule_id=finding.rule_id,
                        severity=finding.severity,
                        title=finding.title,
                        detail=finding.detail,
                        file_path=finding.file_path,
                        evidence_json=finding.evidence,
                        blocked=finding.blocked,
                        developer_visible=finding.developer_visible,
                    )
                )
            evidence_key = storage.evidence_key(version.id, run.id, "static-review.json")
            storage.write_evidence_json(evidence_key, result.evidence)
            run.evidence_storage_key = evidence_key
            run.summary_json = result.summary
            run.status = (
                DesktopPluginReviewRunStatus.FAILED
                if result.blocked
                else DesktopPluginReviewRunStatus.RUNNING
            )
            run.worker_id = None
            run.lease_expires_at = None
            run.completed_at = utc_now() if result.blocked else None
            version.status = (
                DesktopPluginVersionStatus.AUTO_REVIEW_FAILED
                if result.blocked
                else DesktopPluginVersionStatus.AUTO_REVIEW_RUNNING
            )
            version.version += 1
            if result.blocked:
                failed += 1
            else:
                run.summary_json = {
                    **result.summary,
                    "static_status": "passed",
                    "dynamic_status": "pending",
                }
                enqueue_dynamic_tasks(db, review_run=run, artifacts=artifacts)
                passed += 1
        except StaticReviewInfrastructureError as exc:
            retry_scheduled += int(
                _mark_infrastructure_failure(
                    run,
                    version,
                    code=exc.code,
                    safe_message=exc.safe_message,
                    maximum_attempts=policy.maximum_static_attempts,
                )
            )
            failed += int(run.status == DesktopPluginReviewRunStatus.INFRASTRUCTURE_FAILED)
            version.version += 1
        except Exception as exc:  # noqa: BLE001 - persisted as a fail-closed review fact.
            retry_scheduled += int(
                _mark_infrastructure_failure(
                    run,
                    version,
                    code=f"desktop_plugin.review_tool_error.{type(exc).__name__}"[:128],
                    safe_message="自动审核工具暂时不可用。",
                    maximum_attempts=policy.maximum_static_attempts,
                )
            )
            failed += int(run.status == DesktopPluginReviewRunStatus.INFRASTRUCTURE_FAILED)
            version.version += 1
        write_audit_log(
            db,
            actor_id=None,
            action="desktop_plugin.static_review.completed",
            target_type="desktop_plugin_review_run",
            target_id=run.id,
            result="success" if run.status == DesktopPluginReviewRunStatus.PASSED else "failure",
            details={
                "status": run.status.value,
                "attempt": run.attempt,
                "error_code": run.error_code,
            },
        )
        db.commit()
        processed += 1
    return {
        "processed": processed,
        "passed": passed,
        "failed": failed,
        "retry_scheduled": retry_scheduled,
    }
