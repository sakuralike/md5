from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from uuid import uuid4

from test_desktop_plugin_control_plane import _finalized_fixture
from test_desktop_plugin_review_workflow import _admin_headers
from test_desktop_plugin_static_review import _process, _submit

from password_detective.core.time import utc_now
from password_detective.db.models.desktop_plugin import DesktopPluginDynamicReviewTask


def _destruction_proof(task_id: str) -> str:
    return hashlib.sha256(f"pdpp-dynamic-destroyed-v1\n{task_id}\n".encode()).hexdigest()


def _register_runner(client, admin_headers: dict[str, str]):
    fingerprint = uuid4().hex + uuid4().hex
    response = client.post(
        "/api/v1/admin/plugin-review-runners",
        headers={**admin_headers, "Idempotency-Key": f"dynamic-runner-{uuid4().hex}"},
        json={
            "name": "Synthetic Dynamic Runner",
            "architecture": "windows-x64",
            "certificate_fingerprint": fingerprint,
        },
    )
    assert response.status_code == 201, response.text
    runner = response.json()
    return runner, {
        "Authorization": f"Bearer {runner['runner_secret']}",
        "X-Plugin-Runner-Id": runner["id"],
        "X-Plugin-Runner-Certificate-SHA256": fingerprint,
        "X-Client-Certificate-Verified": "SUCCESS",
    }


def test_runner_secret_is_not_replayed_by_idempotency(client) -> None:
    admin_headers = _admin_headers(client)
    key = f"runner-secret-replay-{uuid4().hex}"
    payload = {
        "name": "Synthetic Secret Replay Runner",
        "architecture": "windows-x64",
        "certificate_fingerprint": uuid4().hex + uuid4().hex,
    }
    first = client.post(
        "/api/v1/admin/plugin-review-runners",
        headers={**admin_headers, "Idempotency-Key": key},
        json=payload,
    )
    assert first.status_code == 201
    assert first.json()["runner_secret"]
    replay = client.post(
        "/api/v1/admin/plugin-review-runners",
        headers={**admin_headers, "Idempotency-Key": key},
        json=payload,
    )
    assert replay.status_code == 201
    assert replay.json()["runner_secret"] is None


def _ready(client, headers: dict[str, str]):
    response = client.post(
        "/api/v1/plugin-runner/heartbeat",
        headers=headers,
        json={
            "policy_version": "desktop-plugin-dynamic-review-v1",
            "image_digest": "a" * 64,
            "probe_version": "synthetic-probe-v1",
            "fresh_environment_ready": True,
        },
    )
    assert response.status_code == 200, response.text
    return response


def _queued_dynamic_fixture(client, slug: str, **package_options):
    headers, _, project_id, finalized, package, _, _ = _finalized_fixture(
        client, slug, **package_options
    )
    _submit(client, headers, project_id, finalized["id"], f"submit-{uuid4().hex}")
    assert _process(client)["passed"] == 1
    return headers, finalized["id"], package


def test_dynamic_runner_mtls_lease_artifact_completion_and_token_expiry(client) -> None:
    developer_headers, version_id, package = _queued_dynamic_fixture(
        client, "com.synthetic.dynamic-review-pass"
    )
    admin_headers = _admin_headers(client)
    runner, runner_headers = _register_runner(client, admin_headers)

    missing_mtls = client.post(
        "/api/v1/plugin-runner/heartbeat",
        headers={**runner_headers, "X-Client-Certificate-Verified": "NONE"},
        json={
            "policy_version": "desktop-plugin-dynamic-review-v1",
            "image_digest": "a" * 64,
            "probe_version": "synthetic-probe-v1",
            "fresh_environment_ready": True,
        },
    )
    assert missing_mtls.status_code == 401
    _ready(client, runner_headers)

    lease = client.post("/api/v1/plugin-runner/tasks/lease", headers=runner_headers)
    assert lease.status_code == 200, lease.text
    task = lease.json()
    assert task["architecture"] == "windows-x64"
    task_headers = {**runner_headers, "X-Plugin-Task-Token": task["task_token"]}
    artifact = client.get(task["artifact_url"], headers=task_headers)
    assert artifact.status_code == 200
    assert artifact.content == package
    assert hashlib.sha256(artifact.content).hexdigest() == task["artifact_sha256"]

    heartbeat = client.post(
        f"/api/v1/plugin-runner/tasks/{task['task_id']}/heartbeat",
        headers=task_headers,
    )
    assert heartbeat.status_code == 200
    complete = client.post(
        f"/api/v1/plugin-runner/tasks/{task['task_id']}/complete",
        headers=task_headers,
        json={
            "outcome": "passed",
            "evidence_complete": True,
            "fresh_environment": True,
            "destruction_proof_sha256": _destruction_proof(task["task_id"]),
            "summary": {
                "appcontainer": True,
                "network_connected": False,
                "child_process_count": 0,
                "duration_ms": 50,
                "workspace_deleted": True,
            },
            "findings": [
                {
                    "stage": "dynamic_protocol",
                    "rule_id": "PD-DYNAMIC-INFO-001",
                    "severity": "info",
                    "title": "PDPP 健康检查通过",
                    "detail": "隔离执行器完成初始化、健康检查和关闭。",
                    "evidence": {"appcontainer": True, "duration_ms": 50},
                    "blocked": False,
                }
            ],
        },
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "passed"
    replay = client.get(task["artifact_url"], headers=task_headers)
    assert replay.status_code == 401

    report = client.get(
        f"/api/v1/developer/plugin-versions/{version_id}/review-report",
        headers=developer_headers,
    ).json()
    assert report["version_status"] == "manual_review_ready"
    assert report["runs"][0]["status"] == "passed"
    assert report["runs"][0]["dynamic_tasks"][0]["fresh_environment"] is True
    assert "runner_secret" not in client.get(
        "/api/v1/admin/plugin-review-runners", headers=admin_headers
    ).text
    assert runner["runner_secret"] not in str(report)


def test_dynamic_runner_incomplete_evidence_fails_closed(client) -> None:
    developer_headers, version_id, _ = _queued_dynamic_fixture(
        client, "com.synthetic.dynamic-review-incomplete"
    )
    admin_headers = _admin_headers(client)
    _, runner_headers = _register_runner(client, admin_headers)
    _ready(client, runner_headers)
    task = client.post("/api/v1/plugin-runner/tasks/lease", headers=runner_headers).json()
    task_headers = {**runner_headers, "X-Plugin-Task-Token": task["task_token"]}
    completed = client.post(
        f"/api/v1/plugin-runner/tasks/{task['task_id']}/complete",
        headers=task_headers,
        json={
            "outcome": "passed",
            "evidence_complete": False,
            "fresh_environment": True,
            "destruction_proof_sha256": _destruction_proof(task["task_id"]),
            "summary": {
                "appcontainer": True,
                "network_connected": False,
                "child_process_count": 0,
                "workspace_deleted": True,
            },
            "findings": [],
        },
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "blocked"
    assert completed.json()["error_code"] == "desktop_plugin.dynamic_evidence_incomplete"
    report = client.get(
        f"/api/v1/developer/plugin-versions/{version_id}/review-report",
        headers=developer_headers,
    ).json()
    assert report["version_status"] == "auto_review_failed"


def test_dynamic_runner_rejects_unverifiable_destruction_proof(client) -> None:
    developer_headers, version_id, _ = _queued_dynamic_fixture(
        client, "com.synthetic.dynamic-review-destruction"
    )
    admin_headers = _admin_headers(client)
    _, runner_headers = _register_runner(client, admin_headers)
    _ready(client, runner_headers)
    task = client.post("/api/v1/plugin-runner/tasks/lease", headers=runner_headers).json()
    completed = client.post(
        f"/api/v1/plugin-runner/tasks/{task['task_id']}/complete",
        headers={**runner_headers, "X-Plugin-Task-Token": task["task_token"]},
        json={
            "outcome": "passed",
            "evidence_complete": True,
            "fresh_environment": True,
            "destruction_proof_sha256": "0" * 64,
            "summary": {
                "appcontainer": True,
                "network_connected": False,
                "child_process_count": 0,
                "workspace_deleted": True,
            },
            "findings": [],
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "blocked"
    report = client.get(
        f"/api/v1/developer/plugin-versions/{version_id}/review-report",
        headers=developer_headers,
    ).json()
    assert report["version_status"] == "auto_review_failed"


def test_dynamic_runner_expired_leases_retry_three_times_then_fail_closed(client) -> None:
    developer_headers, version_id, _ = _queued_dynamic_fixture(
        client, "com.synthetic.dynamic-review-timeout"
    )
    admin_headers = _admin_headers(client)
    _, runner_headers = _register_runner(client, admin_headers)
    last_task_id = None
    for _ in range(3):
        _ready(client, runner_headers)
        lease = client.post("/api/v1/plugin-runner/tasks/lease", headers=runner_headers)
        assert lease.status_code == 200
        lease_body = lease.json()
        if lease_body is None:
            report = client.get(
                f"/api/v1/developer/plugin-versions/{version_id}/review-report",
                headers=developer_headers,
            ).json()
            raise AssertionError(report["runs"][0]["dynamic_tasks"])
        last_task_id = lease_body["task_id"]
        with client.app.state.database.session_factory() as db:
            task = db.get(DesktopPluginDynamicReviewTask, last_task_id)
            assert task is not None
            task.lease_expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
    _ready(client, runner_headers)
    exhausted = client.post("/api/v1/plugin-runner/tasks/lease", headers=runner_headers)
    assert exhausted.status_code == 200
    assert exhausted.json() is None
    report = client.get(
        f"/api/v1/developer/plugin-versions/{version_id}/review-report",
        headers=developer_headers,
    ).json()
    assert report["version_status"] == "auto_review_failed"
    task = report["runs"][0]["dynamic_tasks"][0]
    assert task["status"] == "infrastructure_failed"
    assert task["attempt"] == 3


def test_admin_review_metrics_expose_backlog_and_runner_capacity(client) -> None:
    _developer_headers, _version_id, _package = _queued_dynamic_fixture(
        client, "com.synthetic.dynamic-review-metrics"
    )
    admin_headers = _admin_headers(client)
    _runner, runner_headers = _register_runner(client, admin_headers)
    _ready(client, runner_headers)
    metrics = client.get("/api/v1/admin/plugin-reviews/metrics", headers=admin_headers)
    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    assert body["queue_depth_by_architecture"]["windows-x64"] == 1
    assert body["runner_capacity_by_architecture"]["windows-x64"] == 1
    assert body["runner_status_counts"]["ready"] == 1
    assert body["oldest_queued_seconds"] is not None


def test_two_runners_lease_distinct_tasks_and_report_active_capacity(client) -> None:
    _queued_dynamic_fixture(client, "com.synthetic.dynamic-review-capacity-a")
    _queued_dynamic_fixture(
        client,
        "com.synthetic.dynamic-review-capacity-b",
        publisher_key_id="synthetic-ed25519-v2",
    )
    admin_headers = _admin_headers(client)
    _, first_headers = _register_runner(client, admin_headers)
    _, second_headers = _register_runner(client, admin_headers)
    _ready(client, first_headers)
    _ready(client, second_headers)

    first = client.post("/api/v1/plugin-runner/tasks/lease", headers=first_headers)
    second = client.post("/api/v1/plugin-runner/tasks/lease", headers=second_headers)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["task_id"] != second.json()["task_id"]
    metrics = client.get("/api/v1/admin/plugin-reviews/metrics", headers=admin_headers).json()
    assert metrics["runner_capacity_by_architecture"]["windows-x64"] == 2
    assert metrics["runner_active_by_architecture"]["windows-x64"] == 2


def test_admin_review_policy_is_versioned_and_controls_new_leases(client) -> None:
    admin_headers = _admin_headers(client)
    initial = client.get("/api/v1/admin/plugin-review-policy", headers=admin_headers)
    assert initial.status_code == 200, initial.text
    assert initial.json()["version"] == 0
    saved = client.put(
        "/api/v1/admin/plugin-review-policy",
        headers={**admin_headers, "Idempotency-Key": f"review-policy-{uuid4().hex}"},
        json={
            "version": 0,
            "static_lease_seconds": 120,
            "dynamic_lease_seconds": 120,
            "task_token_seconds": 180,
            "maximum_static_attempts": 2,
            "maximum_dynamic_attempts": 2,
            "runner_offline_seconds": 60,
            "revocation_refresh_hours": 6,
            "revocation_max_stale_hours": 168,
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1
    assert saved.json()["policy_version"] == "desktop-plugin-review-policy-v2"
    conflict = client.put(
        "/api/v1/admin/plugin-review-policy",
        headers={**admin_headers, "Idempotency-Key": f"review-policy-{uuid4().hex}"},
        json={**saved.json(), "version": 0},
    )
    assert conflict.status_code == 409

    developer_headers, version_id, _ = _queued_dynamic_fixture(
        client, "com.synthetic.dynamic-review-policy"
    )
    report = client.get(
        f"/api/v1/developer/plugin-versions/{version_id}/review-report",
        headers=developer_headers,
    ).json()
    assert report["runs"][0]["policy_version"] == "desktop-plugin-review-policy-v2"
    _, runner_headers = _register_runner(client, admin_headers)
    _ready(client, runner_headers)
    lease = client.post("/api/v1/plugin-runner/tasks/lease", headers=runner_headers)
    assert lease.status_code == 200, lease.text
    expires_at = datetime.fromisoformat(lease.json()["expires_at"].replace("Z", "+00:00"))
    assert 120 <= (expires_at - utc_now()).total_seconds() <= 181
