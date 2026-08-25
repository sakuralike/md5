from __future__ import annotations

import base64
import hashlib
import io
import json
import shutil
import zipfile
from datetime import timedelta
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from password_detective.core.time import utc_now
from password_detective.db.models.desktop_plugin import (
    DesktopPlugin,
    DesktopPluginArtifact,
    DesktopPluginArtifactStatus,
    DesktopPluginArtifactZone,
    DesktopPluginRevocation,
    DesktopPluginRevocationScope,
    DesktopPluginStatus,
    DesktopPluginVersion,
    DesktopPluginVersionStatus,
)
from password_detective.db.models.user import User
from password_detective.modules.desktop_plugins.storage import DesktopPluginStorage

_PASSWORD = "SyntheticPluginDeveloper123!"


def _register_verified(client, prefix: str) -> tuple[dict[str, str], str]:
    username = f"{prefix}_{uuid4().hex[:8]}"[:32]
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@synthetic.example.com",
            "password": _PASSWORD,
        },
    )
    assert registered.status_code == 201, registered.text
    user_id = registered.json()["id"]
    with client.app.state.database.session_factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        user.email_verified_at = utc_now()
        db.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={"login": username, "password": _PASSWORD},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, user_id


def _reauthenticate(client, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/me/security/reauthenticate",
        headers=headers,
        json={
            "purpose": "desktop_plugin_signing_key",
            "current_password": _PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["reauth_token"]


def _signature_payload(files: dict[str, bytes]) -> bytes:
    rows = []
    for path, content in sorted(files.items(), key=lambda item: item[0].encode("utf-16-be")):
        rows.extend([path, str(len(content)), hashlib.sha256(content).hexdigest()])
    return ("PD-PDPKG-SIGNATURE-V1\n" + "\n".join(rows) + "\n").encode()


def _package(
    private_key: Ed25519PrivateKey,
    *,
    plugin_id: str,
    version: str = "1.0.0",
    valid_signature: bool = True,
) -> tuple[bytes, str]:
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    public_key_base64 = base64.b64encode(public_key).decode()
    manifest = {
        "schema": "pd.plugin/v1",
        "plugin_id": plugin_id,
        "version": version,
        "display_name": "合成市场插件",
        "description": "仅用于插件控制面自动化测试。",
        "publisher_key_id": "synthetic-ed25519-v1",
        "publisher_public_key": public_key_base64,
        "protocol": {"min": 1, "max": 1},
        "host": {"min_version": "0.1.0", "max_version": "0.x"},
        "runtime": {
            "kind": "process",
            "entrypoints": {
                "windows-x64": "bin/windows-x64/plugin.exe",
                "windows-arm64": "bin/windows-arm64/plugin.exe",
            },
        },
        "commands": [{"id": "echo", "title": "回显", "input_schema": "schemas/echo.schema.json"}],
        "capabilities": {
            "required": ["ui:command"],
            "optional": ["storage:private"],
        },
        "limits": {
            "memory_mb": 128,
            "cpu_percent": 25,
            "command_timeout_seconds": 30,
            "child_processes": 0,
        },
    }
    files = {
        "manifest.json": json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode(),
        "bin/windows-x64/plugin.exe": b"MZ-synthetic-x64-plugin",
        "bin/windows-arm64/plugin.exe": b"MZ-synthetic-arm64-plugin",
        "schemas/echo.schema.json": b'{"type":"object","properties":{}}',
    }
    signature = private_key.sign(_signature_payload(files))
    if not valid_signature:
        signature = bytes([signature[0] ^ 1]) + signature[1:]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
        archive.writestr("signature.ed25519", base64.b64encode(signature))
    return output.getvalue(), public_key_base64


def _create_project_and_key(
    client,
    headers: dict[str, str],
    *,
    slug: str,
    public_key_base64: str,
) -> tuple[str, str]:
    project = client.post(
        "/api/v1/developer/plugins",
        headers={**headers, "Idempotency-Key": f"project-{uuid4().hex}"},
        json={
            "slug": slug,
            "name": "合成市场插件",
            "summary": "合成插件摘要",
            "description": "合成插件详情",
            "category": "development",
            "tags": ["synthetic"],
        },
    )
    assert project.status_code == 201, project.text
    signing_key = client.post(
        "/api/v1/developer/plugins/signing-keys",
        headers={**headers, "Idempotency-Key": f"key-{uuid4().hex}"},
        json={
            "key_id": "synthetic-ed25519-v1",
            "public_key_base64": public_key_base64,
            "reauth_token": _reauthenticate(client, headers),
        },
    )
    assert signing_key.status_code == 201, signing_key.text
    return project.json()["id"], signing_key.json()["id"]


def _create_version(
    client,
    headers: dict[str, str],
    *,
    project_id: str,
    signing_key_id: str,
) -> dict:
    response = client.post(
        f"/api/v1/developer/plugins/{project_id}/versions",
        headers={**headers, "Idempotency-Key": f"version-{uuid4().hex}"},
        json={
            "semver": "1.0.0",
            "signing_key_id": signing_key_id,
            "protocol_min": 1,
            "protocol_max": 1,
            "host_min": "0.1.0",
            "host_max": "0.x",
            "requested_capabilities": ["ui:command", "storage:private"],
            "release_notes": "合成发布说明",
            "source_review_mode": "binary_only",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _upload(client, headers: dict[str, str], version_id: str, package: bytes) -> None:
    session = client.post(
        f"/api/v1/developer/plugin-versions/{version_id}/upload-session",
        headers=headers,
        json={
            "architecture": "windows-x64",
            "artifact_filename": "plugin.pdpkg",
            "size_bytes": len(package),
            "sha256": hashlib.sha256(package).hexdigest(),
        },
    )
    assert session.status_code == 201, session.text
    uploaded = client.put(
        session.json()["upload_url"],
        headers={"Content-Type": "application/octet-stream"},
        content=package,
    )
    assert uploaded.status_code == 200, uploaded.text


def _current_version(client, headers: dict[str, str], project_id: str) -> dict:
    response = client.get(f"/api/v1/developer/plugins/{project_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["versions"][0]


def _finalized_fixture(client, slug: str):
    headers, owner_id = _register_verified(client, "plugin_owner")
    private_key = Ed25519PrivateKey.generate()
    package, public_key = _package(private_key, plugin_id=slug)
    project_id, signing_key_id = _create_project_and_key(
        client, headers, slug=slug, public_key_base64=public_key
    )
    version = _create_version(
        client,
        headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
    )
    _upload(client, headers, version["id"], package)
    current = _current_version(client, headers, project_id)
    finalize_key = f"finalize-{uuid4().hex}"
    finalized = client.post(
        f"/api/v1/developer/plugin-versions/{version['id']}/finalize",
        headers={**headers, "Idempotency-Key": finalize_key},
        json={"version": current["version"]},
    )
    assert finalized.status_code == 200, finalized.text
    return (
        headers,
        owner_id,
        project_id,
        finalized.json(),
        package,
        finalize_key,
        current["version"],
    )


def test_developer_finalizes_signed_package_and_projects_are_isolated(client) -> None:
    headers, _, project_id, finalized, _, finalize_key, finalize_version = _finalized_fixture(
        client, "com.synthetic.control-plane"
    )
    assert finalized["status"] == "quarantined"
    assert finalized["manifest_json"]["plugin_id"] == "com.synthetic.control-plane"
    assert finalized["manifest_sha256"]
    assert finalized["artifacts"][0]["expanded_size_bytes"] > 0

    replay = client.post(
        f"/api/v1/developer/plugin-versions/{finalized['id']}/finalize",
        headers={**headers, "Idempotency-Key": finalize_key},
        json={"version": finalize_version},
    )
    assert replay.status_code == 200
    assert replay.json() == finalized

    conflict = client.post(
        f"/api/v1/developer/plugin-versions/{finalized['id']}/finalize",
        headers={**headers, "Idempotency-Key": "finalize-new-key-synthetic-001"},
        json={"version": finalized["version"]},
    )
    assert conflict.status_code == 409

    other_headers, _ = _register_verified(client, "plugin_other")
    hidden = client.get(f"/api/v1/developer/plugins/{project_id}", headers=other_headers)
    assert hidden.status_code == 404


def test_finalize_rejects_invalid_signature_and_accepts_replacement(client) -> None:
    headers, _ = _register_verified(client, "plugin_signature")
    private_key = Ed25519PrivateKey.generate()
    invalid_package, public_key = _package(
        private_key,
        plugin_id="com.synthetic.signature-check",
        valid_signature=False,
    )
    project_id, signing_key_id = _create_project_and_key(
        client,
        headers,
        slug="com.synthetic.signature-check",
        public_key_base64=public_key,
    )
    version = _create_version(
        client,
        headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
    )
    _upload(client, headers, version["id"], invalid_package)
    current = _current_version(client, headers, project_id)
    rejected = client.post(
        f"/api/v1/developer/plugin-versions/{version['id']}/finalize",
        headers={**headers, "Idempotency-Key": "invalid-signature-finalize-001"},
        json={"version": current["version"]},
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "desktop_plugin.invalid_signature"

    valid_package, _ = _package(private_key, plugin_id="com.synthetic.signature-check")
    _upload(client, headers, version["id"], valid_package)
    current = _current_version(client, headers, project_id)
    accepted = client.post(
        f"/api/v1/developer/plugin-versions/{version['id']}/finalize",
        headers={**headers, "Idempotency-Key": "valid-signature-finalize-001"},
        json={"version": current["version"]},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "quarantined"


def test_public_market_filters_downloads_and_returns_signed_revocations(client) -> None:
    _, _, project_id, finalized, package, _, _ = _finalized_fixture(
        client, "com.synthetic.published-plugin"
    )
    settings = client.app.state.settings
    storage = DesktopPluginStorage(settings)
    with client.app.state.database.session_factory() as db:
        plugin = db.get(DesktopPlugin, project_id)
        version = db.get(DesktopPluginVersion, finalized["id"])
        artifact = db.get(DesktopPluginArtifact, finalized["artifacts"][0]["id"])
        assert plugin is not None and version is not None and artifact is not None
        assert artifact.storage_key
        public_key = storage.public_key(version.id, artifact.architecture, artifact.id)
        public_path = storage.public_path(public_key)
        public_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(storage.quarantine_path(artifact.storage_key), public_path)
        plugin.status = DesktopPluginStatus.ACTIVE
        version.status = DesktopPluginVersionStatus.PUBLISHED
        version.approved_capabilities = list(version.requested_capabilities)
        version.review_policy_version = "synthetic-review-policy-v1"
        version.platform_key_id = "synthetic-platform-ed25519-v1"
        version.platform_signature_base64 = base64.b64encode(
            b"synthetic-platform-signature"
        ).decode()
        version.published_at = utc_now()
        artifact.status = DesktopPluginArtifactStatus.PUBLIC
        artifact.zone = DesktopPluginArtifactZone.PUBLIC
        artifact.public_storage_key = public_key
        db.commit()

    catalog = client.get(
        "/api/v1/desktop/plugins/catalog",
        params={
            "architecture": "windows-x64",
            "host_version": "0.1.0",
            "protocol_version": 1,
        },
    )
    assert catalog.status_code == 200, catalog.text
    assert catalog.json()["total"] == 1
    assert catalog.json()["items"][0]["slug"] == "com.synthetic.published-plugin"
    assert (
        client.get(
            "/api/v1/desktop/plugins/catalog",
            params={"architecture": "windows-arm64", "host_version": "0.1.0"},
        ).json()["total"]
        == 0
    )
    assert (
        client.get(
            "/api/v1/desktop/plugins/catalog",
            params={"architecture": "windows-x64", "host_version": "1.0.0"},
        ).json()["total"]
        == 0
    )

    detail = client.get("/api/v1/desktop/plugins/com.synthetic.published-plugin")
    assert detail.status_code == 200
    assert detail.json()["versions"][0]["platform_signature_base64"]
    ticket = client.post(
        "/api/v1/desktop/plugins/com.synthetic.published-plugin/download-ticket",
        json={"architecture": "windows-x64", "semver": "1.0.0"},
    )
    assert ticket.status_code == 200, ticket.text
    downloaded = client.get(ticket.json()["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.content == package
    assert client.get(ticket.json()["download_url"]).status_code == 410

    with client.app.state.database.session_factory() as db:
        db.add(
            DesktopPluginRevocation(
                scope=DesktopPluginRevocationScope.VERSION,
                plugin_version_id=finalized["id"],
                reason_code="synthetic_security_test",
                affects_historical_versions=True,
                effective_at=utc_now() - timedelta(seconds=1),
                batch_id="synthetic-batch-001",
                platform_key_id="synthetic-platform-ed25519-v1",
                platform_signature_base64=base64.b64encode(
                    b"synthetic-revocation-signature"
                ).decode(),
            )
        )
        db.commit()

    revocations = client.get("/api/v1/desktop/plugins/revocations")
    assert revocations.status_code == 200
    assert revocations.json()["items"][0]["plugin_slug"] == "com.synthetic.published-plugin"
    conditional = client.get(
        "/api/v1/desktop/plugins/revocations",
        headers={"If-None-Match": revocations.headers["etag"]},
    )
    assert conditional.status_code == 304
    assert client.get("/api/v1/desktop/plugins/catalog").json()["total"] == 0
    blocked_ticket = client.post(
        "/api/v1/desktop/plugins/com.synthetic.published-plugin/download-ticket",
        json={"architecture": "windows-x64", "semver": "1.0.0"},
    )
    assert blocked_ticket.status_code == 404
