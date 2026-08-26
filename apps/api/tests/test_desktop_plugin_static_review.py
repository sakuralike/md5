from __future__ import annotations

from sqlalchemy import select
from test_desktop_plugin_control_plane import (
    _current_version,
    _finalized_fixture,
    _register_verified,
)
from test_desktop_plugin_review_workflow import _admin_headers

from password_detective.db.models.desktop_plugin import (
    DesktopPluginReviewRun,
    DesktopPluginVersionStatus,
)
from password_detective.modules.desktop_plugins import review_service
from password_detective.modules.desktop_plugins.storage import DesktopPluginStorage


def _submit(client, headers: dict[str, str], project_id: str, version_id: str, key: str):
    current = _current_version(client, headers, project_id)
    response = client.post(
        f"/api/v1/developer/plugin-versions/{version_id}/submit",
        headers={**headers, "Idempotency-Key": key},
        json={"version": current["version"]},
    )
    assert response.status_code == 200, response.text
    return response


def _process(client) -> dict[str, int]:
    with client.app.state.database.session_factory() as db:
        return review_service.process_pending_static_reviews(
            db,
            client.app.state.settings,
            worker_id="synthetic-static-review-worker",
        )


def test_static_review_passes_and_exposes_scoped_evidence(client) -> None:
    headers, _, project_id, finalized, _, _, _ = _finalized_fixture(
        client, "com.synthetic.static-review-pass"
    )
    version_id = finalized["id"]
    submitted = _submit(
        client, headers, project_id, version_id, "static-review-pass-submit-001"
    )
    assert submitted.json()["status"] == "review_queued"
    result = _process(client)
    assert result == {"processed": 1, "passed": 1, "failed": 0, "retry_scheduled": 0}

    report = client.get(
        f"/api/v1/developer/plugin-versions/{version_id}/review-report",
        headers=headers,
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["version_status"] == "manual_review_ready"
    assert body["runs"][0]["status"] == "passed"
    assert body["runs"][0]["dynamic_tasks"] == []
    assert body["runs"][0]["summary"]["dynamic_status"] == "disabled"
    assert body["runs"][0]["summary"]["blocking_finding_count"] == 0
    assert set(body["runs"][0]["summary"]["stages"]) == {
        "structure",
        "signature",
        "sbom",
        "vulnerability",
        "license",
        "secret",
        "static_behavior",
        "pe_analysis",
    }

    other_headers, _ = _register_verified(client, "static_review_other")
    hidden = client.get(
        f"/api/v1/developer/plugin-versions/{version_id}/review-report",
        headers=other_headers,
    )
    assert hidden.status_code == 404

    admin_headers = _admin_headers(client)
    detail = client.get(
        f"/api/v1/admin/plugin-reviews/versions/{version_id}", headers=admin_headers
    )
    assert detail.status_code == 200
    assert detail.json()["review_runs"][0]["status"] == "passed"
    with client.app.state.database.session_factory() as db:
        run = db.scalar(
            select(DesktopPluginReviewRun).where(DesktopPluginReviewRun.version_id == version_id)
        )
        assert run is not None and run.evidence_storage_key is not None
        assert DesktopPluginStorage(client.app.state.settings).evidence_path(
            run.evidence_storage_key
        ).is_file()


def test_static_review_blocks_all_expected_malicious_corpus_rules(client) -> None:
    headers, _, project_id, finalized, _, _, _ = _finalized_fixture(
        client,
        "com.synthetic.static-review-block",
        sbom_components=[
            {
                "type": "library",
                "name": "log4j-core",
                "version": "2.14.1",
                "licenses": [{"license": {"id": "AGPL-3.0-only"}}],
            }
        ],
        extra_files={
            "bin/windows-x64/plugin.exe": (
                b"MZ-synthetic powershell.exe CurrentVersion\\Run http://synthetic.invalid"
            ),
            "source/private.pem": b"-----BEGIN PRIVATE KEY-----\nsynthetic-only\n",
        },
    )
    version_id = finalized["id"]
    _submit(client, headers, project_id, version_id, "static-review-block-submit-001")
    result = _process(client)
    assert result["failed"] == 1

    report = client.get(
        f"/api/v1/developer/plugin-versions/{version_id}/review-report",
        headers=headers,
    )
    assert report.status_code == 200
    body = report.json()
    assert body["version_status"] == "auto_review_failed"
    findings = body["runs"][0]["findings"]
    rule_ids = {finding["rule_id"] for finding in findings}
    assert {
        "PD-VULN-001",
        "PD-LICENSE-002",
        "PD-SECRET-001",
        "PD-STATIC-001",
        "PD-STATIC-004",
        "PD-STATIC-006",
    }.issubset(rule_ids)
    serialized = report.text
    assert "synthetic-only" not in serialized
    assert all(finding["blocked"] for finding in findings if finding["rule_id"] in rule_ids)
    with client.app.state.database.session_factory() as db:
        run = db.scalar(
            select(DesktopPluginReviewRun).where(DesktopPluginReviewRun.version_id == version_id)
        )
        assert run is not None and run.evidence_storage_key is not None
        evidence = DesktopPluginStorage(client.app.state.settings).evidence_path(
            run.evidence_storage_key
        ).read_text(encoding="utf-8")
        assert "synthetic-only" not in evidence

    admin_headers = _admin_headers(client)
    detail = client.get(
        f"/api/v1/admin/plugin-reviews/versions/{version_id}", headers=admin_headers
    ).json()
    approval = client.post(
        f"/api/v1/admin/plugin-reviews/versions/{version_id}/approve",
        headers={**admin_headers, "Idempotency-Key": "blocked-review-approve-001"},
        json={
            "version": detail["version"],
            "approved_capabilities": ["ui:command"],
            "review_note": "Synthetic blocked review must not be approved.",
        },
    )
    assert approval.status_code == 409


def test_static_review_missing_sbom_is_blocked(client) -> None:
    headers, _, project_id, finalized, _, _, _ = _finalized_fixture(
        client,
        "com.synthetic.static-review-no-sbom",
        include_sbom=False,
    )
    _submit(
        client,
        headers,
        project_id,
        finalized["id"],
        "static-review-no-sbom-submit-001",
    )
    assert _process(client)["failed"] == 1
    report = client.get(
        f"/api/v1/developer/plugin-versions/{finalized['id']}/review-report",
        headers=headers,
    ).json()
    assert report["version_status"] == "auto_review_failed"
    assert {item["rule_id"] for item in report["runs"][0]["findings"]} == {"PD-SBOM-001"}


def test_static_review_tool_failure_retries_then_fails_closed(client, monkeypatch) -> None:
    headers, _, project_id, finalized, _, _, _ = _finalized_fixture(
        client, "com.synthetic.static-review-tool-failure"
    )
    version_id = finalized["id"]
    _submit(client, headers, project_id, version_id, "static-review-tool-submit-001")

    def fail_tool(**_):
        raise RuntimeError("synthetic internal tool details")

    monkeypatch.setattr(review_service, "inspect_version_artifacts", fail_tool)
    first = _process(client)
    second = _process(client)
    third = _process(client)
    assert first["retry_scheduled"] == 1
    assert second["retry_scheduled"] == 1
    assert third["failed"] == 1

    report = client.get(
        f"/api/v1/developer/plugin-versions/{version_id}/review-report",
        headers=headers,
    ).json()
    assert report["version_status"] == DesktopPluginVersionStatus.AUTO_REVIEW_FAILED.value
    run = report["runs"][0]
    assert run["status"] == "infrastructure_failed"
    assert run["attempt"] == 3
    assert run["error_message"] == "自动审核工具暂时不可用。"
    assert "synthetic internal tool details" not in str(run)
