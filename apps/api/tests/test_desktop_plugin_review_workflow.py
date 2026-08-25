from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import select
from test_desktop_plugin_control_plane import (
    _current_version,
    _finalized_fixture,
    _register_verified,
)

from password_detective.db.models.desktop_plugin import (
    DesktopPlugin,
    DesktopPluginArtifact,
    DesktopPluginVersion,
)
from password_detective.db.models.third_party_app import ThirdPartyApp, ThirdPartyAppStatus
from password_detective.db.models.third_party_oauth import ThirdPartyAuthorization
from password_detective.db.models.user import User, UserRole
from password_detective.modules.desktop_plugins.review_service import (
    process_pending_static_reviews,
)
from password_detective.modules.desktop_plugins.storage import DesktopPluginStorage


def _canonical_json(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _isoformat(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return f"{parsed.isoformat()}Z"
    return parsed.isoformat().replace("+00:00", "Z")


def _verify_platform_signature(body: dict, payload: dict[str, object]) -> None:
    public_key = base64.b64decode(body["platform_public_key_base64"], validate=True)
    assert body["platform_key_id"] == (
        f"platform-ed25519-{hashlib.sha256(public_key).hexdigest()[:16]}"
    )
    Ed25519PublicKey.from_public_bytes(public_key).verify(
        base64.b64decode(body["platform_signature_base64"], validate=True),
        _canonical_json(body["platform_signature_payload"]),
    )


def _admin_headers(client) -> dict[str, str]:
    headers, user_id = _register_verified(client, "plugin_reviewer")
    with client.app.state.database.session_factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()
    return headers


def _run_static_review(client) -> dict[str, int]:
    with client.app.state.database.session_factory() as db:
        return process_pending_static_reviews(
            db,
            client.app.state.settings,
            worker_id="synthetic-static-review-worker",
        )


def _complete_dynamic_review(client, admin_headers: dict[str, str]) -> None:
    certificate_fingerprint = uuid4().hex + uuid4().hex
    registered = client.post(
        "/api/v1/admin/plugin-review-runners",
        headers={**admin_headers, "Idempotency-Key": f"runner-create-{uuid4().hex}"},
        json={
            "name": "Synthetic Windows Runner",
            "architecture": "windows-x64",
            "certificate_fingerprint": certificate_fingerprint,
        },
    )
    assert registered.status_code == 201, registered.text
    runner = registered.json()
    runner_headers = {
        "Authorization": f"Bearer {runner['runner_secret']}",
        "X-Plugin-Runner-Id": runner["id"],
        "X-Plugin-Runner-Certificate-SHA256": certificate_fingerprint,
        "X-Client-Certificate-Verified": "SUCCESS",
    }
    heartbeat = client.post(
        "/api/v1/plugin-runner/heartbeat",
        headers=runner_headers,
        json={
            "policy_version": "desktop-plugin-dynamic-review-v1",
            "image_digest": "a" * 64,
            "probe_version": "synthetic-probe-v1",
            "fresh_environment_ready": True,
        },
    )
    assert heartbeat.status_code == 200, heartbeat.text
    leased = client.post("/api/v1/plugin-runner/tasks/lease", headers=runner_headers)
    assert leased.status_code == 200, leased.text
    task = leased.json()
    task_headers = {**runner_headers, "X-Plugin-Task-Token": task["task_token"]}
    completed = client.post(
        f"/api/v1/plugin-runner/tasks/{task['task_id']}/complete",
        headers=task_headers,
        json={
            "outcome": "passed",
            "evidence_complete": True,
            "fresh_environment": True,
            "destruction_proof_sha256": hashlib.sha256(
                f"pdpp-dynamic-destroyed-v1\n{task['task_id']}\n".encode()
            ).hexdigest(),
            "summary": {
                "appcontainer": True,
                "network_connected": False,
                "child_process_count": 0,
                "duration_ms": 25,
                "workspace_deleted": True,
            },
            "findings": [],
        },
    )
    assert completed.status_code == 200, completed.text


def test_manual_review_publish_yank_revoke_and_report_workflow(client) -> None:
    developer_headers, _, project_id, finalized, _, _, _ = _finalized_fixture(
        client, "com.synthetic.review-workflow"
    )
    version_id = finalized["id"]
    current = _current_version(client, developer_headers, project_id)
    submitted = client.post(
        f"/api/v1/developer/plugin-versions/{version_id}/submit",
        headers={
            **developer_headers,
            "Idempotency-Key": "review-submit-synthetic-001",
        },
        json={"version": current["version"]},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "review_queued"
    assert _run_static_review(client)["passed"] == 1

    admin_headers = _admin_headers(client)
    _complete_dynamic_review(client, admin_headers)
    queue = client.get("/api/v1/admin/plugin-reviews/queue", headers=admin_headers)
    assert queue.status_code == 200, queue.text
    assert queue.json()["items"][0]["version_id"] == version_id

    detail = client.get(
        f"/api/v1/admin/plugin-reviews/versions/{version_id}", headers=admin_headers
    )
    assert detail.status_code == 200
    review_version = detail.json()["version"]
    approved = client.post(
        f"/api/v1/admin/plugin-reviews/versions/{version_id}/approve",
        headers={**admin_headers, "Idempotency-Key": "review-approve-synthetic-001"},
        json={
            "version": review_version,
            "approved_capabilities": ["ui:command"],
            "review_note": "Synthetic manual review approved the requested command capability.",
        },
    )
    assert approved.status_code == 200, approved.text
    approved_body = approved.json()
    assert approved_body["status"] == "approved"
    assert approved_body["approved_capabilities"] == ["ui:command"]
    assert approved_body["events"][-1]["kind"] == "approved"

    published = client.post(
        f"/api/v1/admin/plugin-reviews/versions/{version_id}/publish",
        headers={**admin_headers, "Idempotency-Key": "review-publish-synthetic-001"},
        json={"version": approved_body["version"], "channel": "stable"},
    )
    assert published.status_code == 200, published.text
    published_body = published.json()
    assert published_body["status"] == "published"
    assert published_body["platform_public_key_base64"]
    assert published_body["platform_signature_base64"]
    assert published_body["events"][-1]["kind"] == "published"
    project = client.get(
        f"/api/v1/developer/plugins/{project_id}", headers=developer_headers
    ).json()
    published_version = next(item for item in project["versions"] if item["id"] == version_id)
    _verify_platform_signature(
        published_body,
        {
            "plugin_id": project_id,
            "version_id": version_id,
            "semver": published_version["semver"],
            "manifest_sha256": published_version["manifest_sha256"],
            "approved_capabilities": published_version["approved_capabilities"],
            "policy": published_version["review_policy_version"],
            "published_at": _isoformat(published_version["published_at"]),
        },
    )
    with client.app.state.database.session_factory() as db:
        artifact = db.scalar(
            select(DesktopPluginArtifact).where(
                DesktopPluginArtifact.plugin_version_id == version_id
            )
        )
        assert artifact is not None
        assert artifact.public_storage_key is not None
        public_path = DesktopPluginStorage(client.app.state.settings).public_path(
            artifact.public_storage_key
        )
        assert public_path.is_file()
    catalog = client.get("/api/v1/desktop/plugins/catalog")
    assert catalog.status_code == 200
    assert catalog.json()["items"][0]["slug"] == "com.synthetic.review-workflow"

    report_payload = {
        "version_id": version_id,
        "category": "privacy",
        "description": "Synthetic report for manual review workflow coverage.",
    }
    report_headers = {**developer_headers, "Idempotency-Key": "report-create-synthetic-001"}
    report = client.post(
        "/api/v1/desktop/plugins/com.synthetic.review-workflow/reports",
        headers=report_headers,
        json=report_payload,
    )
    assert report.status_code == 201, report.text
    report_replay = client.post(
        "/api/v1/desktop/plugins/com.synthetic.review-workflow/reports",
        headers=report_headers,
        json=report_payload,
    )
    assert report_replay.status_code == 201
    assert report_replay.json()["id"] == report.json()["id"]
    reports = client.get("/api/v1/admin/plugin-reviews/reports", headers=admin_headers)
    assert reports.status_code == 200
    report_id = reports.json()["items"][0]["id"]
    reviewed = client.post(
        f"/api/v1/admin/plugin-reviews/reports/{report_id}/review",
        headers={**admin_headers, "Idempotency-Key": "report-review-synthetic-001"},
        json={"status": "resolved", "resolution_note": "Synthetic report resolved."},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "resolved"

    latest = client.get(
        f"/api/v1/admin/plugin-reviews/versions/{version_id}", headers=admin_headers
    ).json()
    yanked = client.post(
        f"/api/v1/admin/plugin-reviews/versions/{version_id}/yank",
        headers={**admin_headers, "Idempotency-Key": "review-yank-synthetic-001"},
        json={"version": latest["version"], "reason": "Synthetic ordinary withdrawal."},
    )
    assert yanked.status_code == 200, yanked.text
    assert yanked.json()["status"] == "yanked"
    assert client.get("/api/v1/desktop/plugins/catalog").json()["total"] == 0

    latest = yanked.json()
    revoked = client.post(
        f"/api/v1/admin/plugin-reviews/versions/{version_id}/revoke",
        headers={**admin_headers, "Idempotency-Key": "review-revoke-synthetic-001"},
        json={
            "version": latest["version"],
            "reason_code": "synthetic_security",
            "reason": "Synthetic emergency revocation coverage.",
            "affects_historical_versions": True,
        },
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "revoked"
    revocations = client.get("/api/v1/desktop/plugins/revocations")
    assert revocations.status_code == 200
    revocation = revocations.json()["items"][0]
    assert revocation["semver"] == "1.0.0"
    _verify_platform_signature(
        revocation,
        {
            "scope": "version",
            "plugin_id": project_id,
            "version_id": version_id,
            "reason_code": "synthetic_security",
            "effective_at": _isoformat(revocation["effective_at"]),
        },
    )
    assert not public_path.exists()
    with client.app.state.database.session_factory() as db:
        artifact = db.scalar(
            select(DesktopPluginArtifact).where(
                DesktopPluginArtifact.plugin_version_id == version_id
            )
        )
        assert artifact is not None
        assert artifact.public_storage_key is None
        assert artifact.storage_key is not None
        assert artifact.storage_key.startswith("revoked/")
        assert DesktopPluginStorage(client.app.state.settings).revoked_path(
            artifact.storage_key
        ).is_file()


def test_manual_review_rejects_unrequested_capability_and_records_rejection(client) -> None:
    developer_headers, _, project_id, finalized, _, _, _ = _finalized_fixture(
        client, "com.synthetic.review-negative"
    )
    version_id = finalized["id"]
    current = _current_version(client, developer_headers, project_id)
    submitted = client.post(
        f"/api/v1/developer/plugin-versions/{version_id}/submit",
        headers={**developer_headers, "Idempotency-Key": "review-submit-negative-001"},
        json={"version": current["version"]},
    )
    assert submitted.status_code == 200, submitted.text
    assert _run_static_review(client)["passed"] == 1
    admin_headers = _admin_headers(client)
    _complete_dynamic_review(client, admin_headers)
    current_detail = client.get(
        f"/api/v1/admin/plugin-reviews/versions/{version_id}", headers=admin_headers
    ).json()
    invalid_approval = client.post(
        f"/api/v1/admin/plugin-reviews/versions/{version_id}/approve",
        headers={**admin_headers, "Idempotency-Key": "review-approve-negative-001"},
        json={
            "version": current_detail["version"],
            "approved_capabilities": ["network:internet"],
            "review_note": "Synthetic invalid capability approval.",
        },
    )
    assert invalid_approval.status_code == 422, invalid_approval.text
    detail = client.get(
        f"/api/v1/admin/plugin-reviews/versions/{version_id}", headers=admin_headers
    ).json()
    assert detail["status"] == "manual_review_ready"
    assert [event["kind"] for event in detail["events"]] == ["submitted"]
    rejected = client.post(
        f"/api/v1/admin/plugin-reviews/versions/{version_id}/reject",
        headers={**admin_headers, "Idempotency-Key": "review-reject-negative-001"},
        json={
            "version": detail["version"],
            "review_note": "Synthetic rejection is retained in review history.",
        },
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert [event["kind"] for event in rejected.json()["events"]] == [
        "submitted",
        "rejected",
    ]


def test_api_capability_requires_owner_approved_linked_application_scope(client) -> None:
    developer_headers, owner_id, project_id, finalized, _, _, _ = _finalized_fixture(
        client, "com.synthetic.review-api-scope"
    )
    version_id = finalized["id"]
    with client.app.state.database.session_factory() as db:
        version = db.get(DesktopPluginVersion, version_id)
        assert version is not None
        version.requested_capabilities = ["api:hash:read"]
        db.commit()

    no_application = client.post(
        f"/api/v1/developer/plugin-versions/{version_id}/submit",
        headers={**developer_headers, "Idempotency-Key": "review-api-scope-none-001"},
        json={"version": finalized["version"]},
    )
    assert no_application.status_code == 422, no_application.text
    assert no_application.json()["code"] == "desktop_plugin.linked_application_required"

    with client.app.state.database.session_factory() as db:
        app = ThirdPartyApp(
            client_id=f"pdc_{uuid4().hex}",
            management_secret_hash="0" * 64,
            name="Synthetic linked application",
            developer_name="Synthetic developer",
            description="Synthetic scope validation application.",
            status=ThirdPartyAppStatus.APPROVED,
            requested_scopes_json=json.dumps(["profile:read"]),
            approved_scopes_json=json.dumps(["profile:read"]),
            submitted_by_user_id=owner_id,
        )
        db.add(app)
        db.flush()
        plugin = db.get(DesktopPlugin, project_id)
        assert plugin is not None
        plugin.linked_third_party_app_id = app.id
        linked_app_id = app.id
        db.commit()

    missing_scope = client.post(
        f"/api/v1/developer/plugin-versions/{version_id}/submit",
        headers={**developer_headers, "Idempotency-Key": "review-api-scope-missing-001"},
        json={"version": finalized["version"]},
    )
    assert missing_scope.status_code == 422, missing_scope.text
    assert missing_scope.json()["code"] == "desktop_plugin.linked_application_scope_missing"

    with client.app.state.database.session_factory() as db:
        app = db.get(ThirdPartyApp, linked_app_id)
        assert app is not None
        app.requested_scopes_json = json.dumps(["hash:read"])
        app.approved_scopes_json = json.dumps(["hash:read"])
        db.commit()
    submitted = client.post(
        f"/api/v1/developer/plugin-versions/{version_id}/submit",
        headers={**developer_headers, "Idempotency-Key": "review-api-scope-approved-001"},
        json={"version": finalized["version"]},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "review_queued"


def test_plugin_broker_authorization_rechecks_publication_scope_and_user_consent(client) -> None:
    user_headers, user_id = _register_verified(client, "plugin_broker_user")
    developer_headers, owner_id, project_id, finalized, _, _, _ = _finalized_fixture(
        client, "com.synthetic.plugin-broker"
    )
    version_id = finalized["id"]
    with client.app.state.database.session_factory() as db:
        app = ThirdPartyApp(
            client_id=f"pdc_{uuid4().hex}",
            management_secret_hash="0" * 64,
            name="Synthetic plugin broker app",
            developer_name="Synthetic developer",
            description="Synthetic broker authorization app.",
            status=ThirdPartyAppStatus.APPROVED,
            requested_scopes_json=json.dumps(["profile:read"]),
            approved_scopes_json=json.dumps(["profile:read"]),
            submitted_by_user_id=owner_id,
        )
        db.add(app)
        db.flush()
        plugin = db.get(DesktopPlugin, project_id)
        version = db.get(DesktopPluginVersion, version_id)
        assert plugin is not None and version is not None
        plugin.linked_third_party_app_id = app.id
        plugin.status = "active"
        version.status = "published"
        version.approved_capabilities = ["api:profile:read"]
        version.published_at = datetime.now().astimezone()
        db.add(
            ThirdPartyAuthorization(
                app_id=app.id,
                user_id=user_id,
                scope_json=json.dumps(["profile:read"]),
            )
        )
        authorization_id = app.id
        db.commit()

    allowed = client.post(
        "/api/v1/desktop/plugins/com.synthetic.plugin-broker/broker/authorize",
        headers=user_headers,
        json={"semver": "1.0.0", "capability": "api:profile:read"},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["scope"] == "profile:read"
    assert "access_token" not in allowed.text

    with client.app.state.database.session_factory() as db:
        authorization = db.scalar(
            select(ThirdPartyAuthorization).where(
                ThirdPartyAuthorization.app_id == authorization_id,
                ThirdPartyAuthorization.user_id == user_id,
            )
        )
        assert authorization is not None
        authorization.revoked_at = datetime.now().astimezone()
        db.commit()
    denied = client.post(
        "/api/v1/desktop/plugins/com.synthetic.plugin-broker/broker/authorize",
        headers=user_headers,
        json={"semver": "1.0.0", "capability": "api:profile:read"},
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "desktop_plugin.broker_user_authorization_required"
