from __future__ import annotations

import base64
import hashlib
import io
import json
import shutil
import zipfile
from datetime import timedelta
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.models.desktop_plugin import (
    DesktopPlugin,
    DesktopPluginArtifact,
    DesktopPluginArtifactStatus,
    DesktopPluginArtifactZone,
    DesktopPluginInstallEvent,
    DesktopPluginPublication,
    DesktopPluginPublicationStatus,
    DesktopPluginRevocation,
    DesktopPluginRevocationScope,
    DesktopPluginSigningKey,
    DesktopPluginSigningKeyStatus,
    DesktopPluginStatus,
    DesktopPluginVersion,
    DesktopPluginVersionStatus,
)
from password_detective.db.models.user import User, UserRole
from password_detective.modules.desktop_plugins.package_verifier import verify_plugin_package
from password_detective.modules.desktop_plugins.schemas import (
    PluginCanaryDownloadRequest,
    PluginInstallEventRequest,
)
from password_detective.modules.desktop_plugins.service import (
    _allowed_build_proof_artifact_names,
    _schema_is_backward_compatible,
    build_canary_download_payload,
    build_canary_ticket_payload,
    build_install_evidence_payload,
    schedule_due_migration_retries,
)
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
    include_sbom: bool = True,
    sbom_components: list[dict] | None = None,
    extra_files: dict[str, bytes] | None = None,
    publisher_key_id: str = "synthetic-ed25519-v1",
    commands: list[dict] | None = None,
    include_provenance: bool = False,
    migration: dict[str, object] | None = None,
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
        "publisher_key_id": publisher_key_id,
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
        "commands": commands
        or [{"id": "echo", "title": "回显", "input_schema": "schemas/echo.schema.json"}],
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
    if migration is not None:
        manifest["migration"] = migration
    files = {
        "manifest.json": json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode(),
        "bin/windows-x64/plugin.exe": b"MZ-synthetic-x64-plugin",
        "bin/windows-arm64/plugin.exe": b"MZ-synthetic-arm64-plugin",
        "schemas/echo.schema.json": b'{"type":"object","properties":{}}',
    }
    if include_sbom:
        files["sbom.cdx.json"] = json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.5",
                "version": 1,
                "components": sbom_components or [],
            },
            separators=(",", ":"),
        ).encode()
    files.update(extra_files or {})
    if include_provenance:
        def record(path: str) -> dict[str, object]:
            content = files[path]
            return {
                "path": path,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }

        files["provenance.json"] = json.dumps(
            {
                "schema": "pd.plugin.provenance/v1",
                "source_commit": "a" * 40,
                "source_files": [
                    record(path) for path in sorted(files) if path.startswith("source/")
                ],
                "sbom": record("sbom.cdx.json"),
                "binaries": [record(path) for path in sorted(files) if path.startswith("bin/")],
            },
            separators=(",", ":"),
        ).encode()
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
    key_id: str = "synthetic-ed25519-v1",
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
            "key_id": key_id,
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
    semver: str = "1.0.0",
    host_min: str = "0.1.0",
    requested_capabilities: list[str] | None = None,
    release_notes: str = "合成发布说明",
    source_review_mode: str = "binary_only",
) -> dict:
    response = client.post(
        f"/api/v1/developer/plugins/{project_id}/versions",
        headers={**headers, "Idempotency-Key": f"version-{uuid4().hex}"},
        json={
            "semver": semver,
            "signing_key_id": signing_key_id,
            "protocol_min": 1,
            "protocol_max": 1,
            "host_min": host_min,
            "host_max": "0.x",
            "requested_capabilities": requested_capabilities
            or ["ui:command", "storage:private"],
            "release_notes": release_notes,
            "source_review_mode": source_review_mode,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_developer_signing_key_can_be_generated_server_side(client):
    headers, _ = _register_verified(client, "generated_key")
    response = client.post(
        "/api/v1/developer/plugins/signing-keys",
        headers={**headers, "Idempotency-Key": f"generated-key-{uuid4().hex}"},
        json={"reauth_token": _reauthenticate(client, headers)},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["key_id"].startswith("generated-ed25519-")
    assert len(base64.b64decode(body["public_key_base64"], validate=True)) == 32
    private_key = Ed25519PrivateKey.from_private_bytes(
        base64.b64decode(body["private_key_base64"], validate=True)
    )
    assert base64.b64encode(
        private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    ).decode() == body["public_key_base64"]
    listed = client.get("/api/v1/developer/plugins/signing-keys", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["private_key_base64"] is None


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


def _finalized_fixture(client, slug: str, **package_options):
    headers, owner_id = _register_verified(client, "plugin_owner")
    private_key = Ed25519PrivateKey.generate()
    package, public_key = _package(private_key, plugin_id=slug, **package_options)
    project_id, signing_key_id = _create_project_and_key(
        client,
        headers,
        slug=slug,
        public_key_base64=public_key,
        key_id=package_options.get("publisher_key_id", "synthetic-ed25519-v1"),
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


def test_published_plugin_upgrade_enforces_semver_patch_and_major_rules(client) -> None:
    headers, _, project_id, finalized, _, _, _ = _finalized_fixture(
        client, "com.synthetic.upgrade-policy"
    )
    with client.app.state.database.session_factory() as db:
        baseline = db.get(DesktopPluginVersion, finalized["id"])
        assert baseline is not None
        baseline.status = DesktopPluginVersionStatus.PUBLISHED
        db.commit()

    def create(payload: dict[str, object]):
        return client.post(
            f"/api/v1/developer/plugins/{project_id}/versions",
            headers={**headers, "Idempotency-Key": f"upgrade-{uuid4().hex}"},
            json={
                "signing_key_id": finalized["signing_key_id"],
                "protocol_min": 1,
                "protocol_max": 1,
                "host_min": "0.1.0",
                "host_max": "0.x",
                "requested_capabilities": ["ui:command", "storage:private"],
                "release_notes": "合成升级说明",
                "source_review_mode": "binary_only",
                **payload,
            },
        )

    lower = create({"semver": "0.9.0"})
    assert lower.status_code == 409
    assert lower.json()["code"] == "desktop_plugin.version_not_increasing"

    changed_permissions = create(
        {"semver": "1.0.1", "requested_capabilities": ["ui:command"]}
    )
    assert changed_permissions.status_code == 422
    assert changed_permissions.json()["code"] == "desktop_plugin.patch_upgrade_incompatible"

    invalid_major = create({"semver": "2.0.0"})
    assert invalid_major.status_code == 422
    assert invalid_major.json()["code"] == "desktop_plugin.major_upgrade_compatibility_required"

    valid_patch = create({"semver": "1.0.1"})
    assert valid_patch.status_code == 201, valid_patch.text
    assert valid_patch.json()["semver"] == "1.0.1"


def test_finalize_enforces_patch_commands_and_allows_minor_addition(client) -> None:
    headers, _ = _register_verified(client, "upgrade_manifest")
    private_key = Ed25519PrivateKey.generate()
    baseline_package, public_key = _package(
        private_key, plugin_id="com.synthetic.upgrade-manifest"
    )
    project_id, signing_key_id = _create_project_and_key(
        client,
        headers,
        slug="com.synthetic.upgrade-manifest",
        public_key_base64=public_key,
    )
    baseline = _create_version(
        client,
        headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
    )
    _upload(client, headers, baseline["id"], baseline_package)
    current = _current_version(client, headers, project_id)
    finalized = client.post(
        f"/api/v1/developer/plugin-versions/{baseline['id']}/finalize",
        headers={**headers, "Idempotency-Key": f"finalize-{uuid4().hex}"},
        json={"version": current["version"]},
    )
    assert finalized.status_code == 200, finalized.text
    with client.app.state.database.session_factory() as db:
        published = db.get(DesktopPluginVersion, baseline["id"])
        assert published is not None
        published.status = DesktopPluginVersionStatus.PUBLISHED
        db.commit()

    patch = _create_version(
        client,
        headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
        semver="1.0.1",
    )
    incompatible_package, _ = _package(
        private_key,
        plugin_id="com.synthetic.upgrade-manifest",
        version="1.0.1",
        commands=[
            {"id": "changed", "title": "变更命令", "input_schema": "schemas/echo.schema.json"}
        ],
    )
    _upload(client, headers, patch["id"], incompatible_package)
    patch_current = next(
        item
        for item in client.get(
            f"/api/v1/developer/plugins/{project_id}", headers=headers
        ).json()["versions"]
        if item["id"] == patch["id"]
    )
    rejected = client.post(
        f"/api/v1/developer/plugin-versions/{patch['id']}/finalize",
        headers={**headers, "Idempotency-Key": f"finalize-{uuid4().hex}"},
        json={"version": patch_current["version"]},
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "desktop_plugin.upgrade_command_incompatible"

    minor = _create_version(
        client,
        headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
        semver="1.1.0",
    )
    minor_package, _ = _package(
        private_key,
        plugin_id="com.synthetic.upgrade-manifest",
        version="1.1.0",
        commands=[
            {"id": "echo", "title": "回显", "input_schema": "schemas/echo.schema.json"},
            {"id": "inspect", "title": "检查", "input_schema": "schemas/inspect.schema.json"},
        ],
        extra_files={"schemas/inspect.schema.json": b'{"type":"object","properties":{}}'},
    )
    _upload(client, headers, minor["id"], minor_package)
    minor_current = next(
        item
        for item in client.get(
            f"/api/v1/developer/plugins/{project_id}", headers=headers
        ).json()["versions"]
        if item["id"] == minor["id"]
    )
    accepted = client.post(
        f"/api/v1/developer/plugin-versions/{minor['id']}/finalize",
        headers={**headers, "Idempotency-Key": f"finalize-{uuid4().hex}"},
        json={"version": minor_current["version"]},
    )
    assert accepted.status_code == 200, accepted.text


def test_finalize_rejects_patch_capability_reclassification(client) -> None:
    headers, _ = _register_verified(client, "upgrade_capabilities")
    private_key = Ed25519PrivateKey.generate()
    baseline_package, public_key = _package(
        private_key, plugin_id="com.synthetic.upgrade-capabilities"
    )
    project_id, signing_key_id = _create_project_and_key(
        client,
        headers,
        slug="com.synthetic.upgrade-capabilities",
        public_key_base64=public_key,
    )
    baseline = _create_version(
        client,
        headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
    )
    _upload(client, headers, baseline["id"], baseline_package)
    current = _current_version(client, headers, project_id)
    finalized = client.post(
        f"/api/v1/developer/plugin-versions/{baseline['id']}/finalize",
        headers={**headers, "Idempotency-Key": f"finalize-{uuid4().hex}"},
        json={"version": current["version"]},
    )
    assert finalized.status_code == 200, finalized.text
    with client.app.state.database.session_factory() as db:
        published = db.get(DesktopPluginVersion, baseline["id"])
        assert published is not None
        published.status = DesktopPluginVersionStatus.PUBLISHED
        db.commit()

    patch = _create_version(
        client,
        headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
        semver="1.0.1",
    )
    reclassified_package, _ = _package(
        private_key,
        plugin_id="com.synthetic.upgrade-capabilities",
        version="1.0.1",
        extra_files={
            "manifest.json": json.dumps(
                {
                    "schema": "pd.plugin/v1",
                    "plugin_id": "com.synthetic.upgrade-capabilities",
                    "version": "1.0.1",
                    "display_name": "合成市场插件",
                    "description": "仅用于插件控制面自动化测试。",
                    "publisher_key_id": "synthetic-ed25519-v1",
                    "publisher_public_key": public_key,
                    "protocol": {"min": 1, "max": 1},
                    "host": {"min_version": "0.1.0", "max_version": "0.x"},
                    "runtime": {
                        "kind": "process",
                        "entrypoints": {
                            "windows-x64": "bin/windows-x64/plugin.exe",
                            "windows-arm64": "bin/windows-arm64/plugin.exe",
                        },
                    },
                    "commands": [
                        {"id": "echo", "title": "回显", "input_schema": "schemas/echo.schema.json"}
                    ],
                    "capabilities": {
                        "required": ["ui:command", "storage:private"],
                        "optional": [],
                    },
                    "limits": {
                        "memory_mb": 128,
                        "cpu_percent": 25,
                        "command_timeout_seconds": 30,
                        "child_processes": 0,
                    },
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        },
    )
    _upload(client, headers, patch["id"], reclassified_package)
    patch_current = next(
        item
        for item in client.get(
            f"/api/v1/developer/plugins/{project_id}", headers=headers
        ).json()["versions"]
        if item["id"] == patch["id"]
    )
    rejected = client.post(
        f"/api/v1/developer/plugin-versions/{patch['id']}/finalize",
        headers={**headers, "Idempotency-Key": f"finalize-{uuid4().hex}"},
        json={"version": patch_current["version"]},
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "desktop_plugin.upgrade_capability_incompatible"


def test_finalize_rejects_patch_schema_narrowing(client) -> None:
    headers, _ = _register_verified(client, "upgrade_schema")
    private_key = Ed25519PrivateKey.generate()
    baseline_package, public_key = _package(
        private_key, plugin_id="com.synthetic.upgrade-schema"
    )
    project_id, signing_key_id = _create_project_and_key(
        client,
        headers,
        slug="com.synthetic.upgrade-schema",
        public_key_base64=public_key,
    )
    baseline = _create_version(
        client,
        headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
    )
    _upload(client, headers, baseline["id"], baseline_package)
    current = _current_version(client, headers, project_id)
    finalized = client.post(
        f"/api/v1/developer/plugin-versions/{baseline['id']}/finalize",
        headers={**headers, "Idempotency-Key": f"finalize-{uuid4().hex}"},
        json={"version": current["version"]},
    )
    assert finalized.status_code == 200, finalized.text
    with client.app.state.database.session_factory() as db:
        published = db.get(DesktopPluginVersion, baseline["id"])
        assert published is not None
        published.status = DesktopPluginVersionStatus.PUBLISHED
        db.commit()

    patch = _create_version(
        client,
        headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
        semver="1.0.1",
    )
    narrowed_package, _ = _package(
        private_key,
        plugin_id="com.synthetic.upgrade-schema",
        version="1.0.1",
        extra_files={
            "schemas/echo.schema.json": (
                b'{"type":"object","required":["message"],'
                b'"properties":{"message":{"type":"string"}}}'
            )
        },
    )
    _upload(client, headers, patch["id"], narrowed_package)
    patch_current = next(
        item
        for item in client.get(
            f"/api/v1/developer/plugins/{project_id}", headers=headers
        ).json()["versions"]
        if item["id"] == patch["id"]
    )
    rejected = client.post(
        f"/api/v1/developer/plugin-versions/{patch['id']}/finalize",
        headers={**headers, "Idempotency-Key": f"finalize-{uuid4().hex}"},
        json={"version": patch_current["version"]},
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "desktop_plugin.upgrade_schema_incompatible"


def test_command_schema_backward_compatibility_matrix() -> None:
    def root(property_schema: dict, *, additional: bool = True) -> dict:
        return {
            "type": "object",
            "additionalProperties": additional,
            "required": ["value"],
            "properties": {"value": property_schema},
        }

    cases = [
        (
            "string bounds can widen",
            root({"type": "string", "minLength": 2, "maxLength": 20, "pattern": "^[a-z]+$"}),
            root({"type": "string", "minLength": 1, "maxLength": 30}),
            True,
        ),
        (
            "adding a pattern narrows input",
            root({"type": "string"}),
            root({"type": "string", "pattern": "^[a-z]+$"}),
            False,
        ),
        (
            "enum may widen",
            root({"type": "string", "enum": ["safe", "plain"]}),
            root({"type": "string", "enum": ["safe", "plain", "extended"]}),
            True,
        ),
        (
            "enum may not narrow",
            root({"type": "string", "enum": ["safe", "plain"]}),
            root({"type": "string", "enum": ["safe"]}),
            False,
        ),
        (
            "format changes are incompatible",
            root({"type": "string", "format": "file"}),
            root({"type": "string"}),
            False,
        ),
        (
            "default changes are incompatible",
            root({"type": "string", "default": "plain"}),
            root({"type": "string", "default": "safe"}),
            False,
        ),
        (
            "numeric range can widen",
            root({"type": "number", "minimum": 1, "maximum": 10, "multipleOf": 2}),
            root({"type": "number", "minimum": 0, "maximum": 20, "multipleOf": 1}),
            True,
        ),
        (
            "exclusive lower bound cannot replace inclusive bound",
            root({"type": "number", "minimum": 1}),
            root({"type": "number", "exclusiveMinimum": 1}),
            False,
        ),
        (
            "additional properties cannot be disabled",
            root({"type": "string"}),
            root({"type": "string"}, additional=False),
            False,
        ),
        (
            "array remains outside command schema v1",
            root({"type": "array", "items": {"type": "string"}}),
            root({"type": "array", "items": {"type": "string"}}),
            False,
        ),
    ]
    for label, previous, target, expected in cases:
        assert _schema_is_backward_compatible(previous, target) is expected, label


@pytest.mark.parametrize(
    "command_schema",
    [
        {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "string"}}},
        },
        {
            "type": "object",
            "properties": {
                "value": {
                    "oneOf": [{"type": "string"}, {"type": "integer"}],
                }
            },
        },
    ],
)
def test_server_package_verifier_rejects_command_schema_outside_v1(
    tmp_path, command_schema: dict
) -> None:
    private_key = Ed25519PrivateKey.generate()
    package, public_key = _package(
        private_key,
        plugin_id="com.synthetic.schema-v1",
        extra_files={
            "schemas/echo.schema.json": json.dumps(command_schema, separators=(",", ":")).encode()
        },
    )
    package_path = tmp_path / "schema-v1.pdpkg"
    package_path.write_bytes(package)

    with pytest.raises(AppError) as raised:
        verify_plugin_package(
            package_path,
            architecture="windows-x64",
            project_slug="com.synthetic.schema-v1",
            semver="1.0.0",
            signing_key_id="synthetic-ed25519-v1",
            public_key_base64=public_key,
            protocol_min=1,
            protocol_max=1,
            host_min="0.1.0",
            host_max="0.x",
            requested_capabilities=["ui:command", "storage:private"],
            source_review_mode="binary_only",
            max_expanded_bytes=1024 * 1024 * 1024,
        )

    assert raised.value.code == "desktop_plugin.invalid_package"



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


def test_source_review_mode_requires_signed_build_provenance(client) -> None:
    headers, _ = _register_verified(client, "plugin_provenance")
    private_key = Ed25519PrivateKey.generate()
    missing_provenance, public_key = _package(
        private_key,
        plugin_id="com.synthetic.provenance",
        extra_files={"source/Program.cs": b"internal static class ProvenanceSource { }"},
    )
    project_id, signing_key_id = _create_project_and_key(
        client,
        headers,
        slug="com.synthetic.provenance",
        public_key_base64=public_key,
    )
    version = _create_version(
        client,
        headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
        source_review_mode="source",
    )
    _upload(client, headers, version["id"], missing_provenance)
    current = _current_version(client, headers, project_id)
    rejected = client.post(
        f"/api/v1/developer/plugin-versions/{version['id']}/finalize",
        headers={**headers, "Idempotency-Key": f"provenance-missing-{uuid4().hex}"},
        json={"version": current["version"]},
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "desktop_plugin.invalid_package"

    valid_provenance, _ = _package(
        private_key,
        plugin_id="com.synthetic.provenance",
        extra_files={"source/Program.cs": b"internal static class ProvenanceSource { }"},
        include_provenance=True,
    )
    _upload(client, headers, version["id"], valid_provenance)
    current = _current_version(client, headers, project_id)
    accepted = client.post(
        f"/api/v1/developer/plugin-versions/{version['id']}/finalize",
        headers={**headers, "Idempotency-Key": f"provenance-valid-{uuid4().hex}"},
        json={"version": current["version"]},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "quarantined"


def test_optional_migration_declaration_is_validated_during_finalize(client) -> None:
    headers, _ = _register_verified(client, "plugin_migration")
    private_key = Ed25519PrivateKey.generate()
    project_id, signing_key_id = _create_project_and_key(
        client,
        headers,
        slug="com.synthetic.migration",
        public_key_base64=base64.b64encode(
            private_key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        ).decode(),
    )
    version = _create_version(
        client,
        headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
    )
    package, _ = _package(
        private_key,
        plugin_id="com.synthetic.migration",
        migration={
            "required": True,
            "from_versions": ["0.9.0"],
            "strategy": "idempotent",
        },
    )
    _upload(client, headers, version["id"], package)
    current = _current_version(client, headers, project_id)
    accepted = client.post(
        f"/api/v1/developer/plugin-versions/{version['id']}/finalize",
        headers={**headers, "Idempotency-Key": f"migration-valid-{uuid4().hex}"},
        json={"version": current["version"]},
    )
    assert accepted.status_code == 200, accepted.text

    invalid_version = _create_version(
        client,
        headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
        semver="1.1.0",
    )
    invalid_package, _ = _package(
        private_key,
        plugin_id="com.synthetic.migration",
        version="1.1.0",
        migration={
            "required": True,
            "from_versions": [],
            "strategy": "best_effort",
        },
    )
    _upload(client, headers, invalid_version["id"], invalid_package)
    invalid_current = _current_version(client, headers, project_id)
    rejected = client.post(
        f"/api/v1/developer/plugin-versions/{invalid_version['id']}/finalize",
        headers={**headers, "Idempotency-Key": f"migration-invalid-{uuid4().hex}"},
        json={"version": invalid_current["version"]},
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "desktop_plugin.invalid_package"


def test_source_publish_requires_verified_build_proof(client, monkeypatch) -> None:
    headers, _ = _register_verified(client, "build_proof_owner")
    private_key = Ed25519PrivateKey.generate()
    package, public_key = _package(
        private_key,
        plugin_id="com.synthetic.build-proof",
        include_provenance=True,
        extra_files={"source/Program.cs": b"internal static class SyntheticBuildProof {}"},
    )
    project_id, signing_key_id = _create_project_and_key(
        client,
        headers,
        slug="com.synthetic.build-proof",
        public_key_base64=public_key,
    )
    version = _create_version(
        client,
        headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
        source_review_mode="source",
    )
    _upload(client, headers, version["id"], package)
    current = _current_version(client, headers, project_id)
    finalized = client.post(
        f"/api/v1/developer/plugin-versions/{version['id']}/finalize",
        headers={**headers, "Idempotency-Key": f"build-proof-finalize-{uuid4().hex}"},
        json={"version": current["version"]},
    )
    assert finalized.status_code == 200, finalized.text

    admin_headers, admin_id = _register_verified(client, "build_proof_admin")
    with client.app.state.database.session_factory() as db:
        admin = db.get(User, admin_id)
        row = db.get(DesktopPluginVersion, version["id"])
        assert admin is not None and row is not None
        admin.role = UserRole.ADMIN
        row.status = DesktopPluginVersionStatus.APPROVED
        row.approved_capabilities = list(row.requested_capabilities)
        row.review_policy_version = "synthetic-review-policy-v1"
        db.commit()

    blocked = client.post(
        f"/api/v1/admin/plugin-reviews/versions/{version['id']}/publish",
        headers={**admin_headers, "Idempotency-Key": f"build-proof-publish-blocked-{uuid4().hex}"},
        json={"version": finalized.json()["version"], "channel": "stable"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "desktop_plugin.build_proof_required"

    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        provenance = json.loads(archive.read("provenance.json"))
    ci_package_sha256 = "c" * 64
    assert ci_package_sha256 != hashlib.sha256(package).hexdigest()
    proof = {
        "schema": "pd.plugin.build-proof/v1",
        "git_commit": "a" * 40,
        "package_sha256": ci_package_sha256,
        "rebuild_sha256": "b" * 64,
        "content_reproducible": True,
        "provenance": provenance,
        "toolchain": {"dotnet": "10.0.0", "python": "3.12.13"},
    }
    def fake_download_proof(
        settings, *, repository, run_id, artifact_id, expected_plugin_id
    ):
        assert repository == "sakuralike/md5"
        assert run_id == 33_655_843_084
        assert artifact_id == 9_856_748_830
        assert expected_plugin_id == "com.synthetic.build-proof"
        return proof, "a" * 40

    monkeypatch.setattr(
        "password_detective.modules.desktop_plugins.service._download_github_build_proof",
        fake_download_proof,
    )
    attached = client.post(
        f"/api/v1/developer/plugin-versions/{version['id']}/build-proof",
        headers={**headers, "Idempotency-Key": f"build-proof-attach-{uuid4().hex}"},
        json={
            "version": finalized.json()["version"],
            "architecture": "windows-x64",
            "github_repository": "sakuralike/md5",
            "github_run_id": 33_655_843_084,
            "github_artifact_id": 9_856_748_830,
            "proof": proof,
        },
    )
    assert attached.status_code == 200, attached.text
    assert attached.json()["build_proof_sha256"]
    assert attached.json()["build_proof_package_sha256"] == proof["package_sha256"]

    published = client.post(
        f"/api/v1/admin/plugin-reviews/versions/{version['id']}/publish",
        headers={**admin_headers, "Idempotency-Key": f"build-proof-publish-{uuid4().hex}"},
        json={"version": attached.json()["version"], "channel": "stable"},
    )
    assert published.status_code == 200, published.text


def test_build_proof_artifact_names_are_scoped_to_plugin() -> None:
    head_sha = "a" * 40
    skin_names = _allowed_build_proof_artifact_names(
        head_sha=head_sha,
        plugin_id="com.passworddetective.official-skin",
    )
    assert skin_names == {
        f"plugin-build-proof-{head_sha}",
        f"plugin-build-proof-{head_sha}-com.passworddetective.official-skin",
    }
    assert _allowed_build_proof_artifact_names(
        head_sha=head_sha,
        plugin_id="com.passworddetective.official-hash-query",
    ) == {
        f"plugin-build-proof-{head_sha}-com.passworddetective.official-hash-query"
    }


def test_public_market_filters_downloads_and_returns_signed_revocations(client) -> None:
    _, owner_id, project_id, finalized, package, _, _ = _finalized_fixture(
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
        version.platform_public_key_base64 = base64.b64encode(b"\x01" * 32).decode()
        version.platform_signature_base64 = base64.b64encode(
            b"synthetic-platform-signature"
        ).decode()
        version.published_at = utc_now()
        artifact.status = DesktopPluginArtifactStatus.PUBLIC
        artifact.zone = DesktopPluginArtifactZone.PUBLIC
        artifact.public_storage_key = public_key
        db.add(
            DesktopPluginPublication(
                version_id=version.id,
                channel="stable",
                status=DesktopPluginPublicationStatus.PUBLISHED,
                published_by_user_id=owner_id,
                published_at=version.published_at,
            )
        )
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
    assert ticket.json()["download_url"].startswith(
        "http://localhost:5173/api/v1/desktop/plugins/downloads/"
    )
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
                platform_public_key_base64=base64.b64encode(b"\x01" * 32).decode(),
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


def test_canary_publication_is_hidden_from_public_market(client) -> None:
    owner_headers, owner_id, project_id, finalized, package, _, _ = _finalized_fixture(
        client, "com.synthetic.canary-plugin"
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
        version.platform_public_key_base64 = base64.b64encode(b"\x01" * 32).decode()
        version.platform_signature_base64 = base64.b64encode(
            b"synthetic-platform-signature"
        ).decode()
        version.published_at = utc_now()
        artifact.status = DesktopPluginArtifactStatus.PUBLIC
        artifact.zone = DesktopPluginArtifactZone.PUBLIC
        artifact.public_storage_key = public_key
        db.add(
            DesktopPluginPublication(
                version_id=version.id,
                channel="canary",
                status=DesktopPluginPublicationStatus.PUBLISHED,
                published_by_user_id=owner_id,
                published_at=version.published_at,
            )
        )
        db.commit()

    admin_headers, admin_id = _register_verified(client, "canary_download_admin")
    with client.app.state.database.session_factory() as db:
        admin = db.get(User, admin_id)
        assert admin is not None
        admin.role = UserRole.ADMIN
        db.commit()
    installation_id = str(uuid4())
    installation_key = ec.generate_private_key(ec.SECP256R1())
    installation_public_key = installation_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    registered = client.post(
        "/api/v1/desktop/installations",
        headers=admin_headers,
        json={
            "installation_id": installation_id,
            "public_key": base64.b64encode(installation_public_key).decode(),
            "key_algorithm": "ecdsa-p256-sha256",
            "client_version": "0.1.0",
        },
    )
    assert registered.status_code == 200, registered.text
    review_detail = client.get(
        f"/api/v1/admin/plugin-reviews/versions/{finalized['id']}",
        headers=admin_headers,
    )
    assert review_detail.status_code == 200
    assert review_detail.json()["publication_channels"] == ["canary"]
    canary_catalog = client.get(
        "/api/v1/desktop/plugins/canary/catalog",
        headers=admin_headers,
    )
    assert canary_catalog.status_code == 200, canary_catalog.text
    assert canary_catalog.headers["cache-control"] == "private, no-store"
    assert canary_catalog.json()["items"][0]["slug"] == "com.synthetic.canary-plugin"
    canary_detail = client.get(
        "/api/v1/desktop/plugins/canary/com.synthetic.canary-plugin",
        headers=admin_headers,
    )
    assert canary_detail.status_code == 200, canary_detail.text
    assert canary_detail.json()["versions"][0]["version_id"] == finalized["id"]
    assert (
        client.get("/api/v1/desktop/plugins/canary/catalog", headers=owner_headers).status_code
        == 403
    )
    canary_request = {
        "architecture": "windows-x64",
        "installation_id": installation_id,
        "signature": "x" * 64,
    }
    canary_request["signature"] = base64.b64encode(
        installation_key.sign(
            build_canary_ticket_payload(
                finalized["id"],
                PluginCanaryDownloadRequest.model_validate(canary_request),
            ),
            ec.ECDSA(hashes.SHA256()),
        )
    ).decode()
    canary_ticket = client.post(
        f"/api/v1/admin/plugin-reviews/versions/{finalized['id']}/canary-download-ticket",
        headers=admin_headers,
        json=canary_request,
    )
    assert canary_ticket.status_code == 200, canary_ticket.text
    download_url = canary_ticket.json()["download_url"]
    assert client.get(download_url).status_code == 403
    raw_token = download_url.rsplit("/", 1)[-1]
    download_signature = base64.b64encode(
        installation_key.sign(
            build_canary_download_payload(raw_token, installation_id),
            ec.ECDSA(hashes.SHA256()),
        )
    ).decode()
    downloaded = client.get(
        download_url,
        headers={
            **admin_headers,
            "X-Plugin-Installation-Id": installation_id,
            "X-Plugin-Canary-Signature": download_signature,
        },
    )
    assert downloaded.status_code == 200
    assert downloaded.content == package
    assert client.get("/api/v1/desktop/plugins/catalog").json()["total"] == 0
    assert client.get("/api/v1/desktop/plugins/com.synthetic.canary-plugin").status_code == 404
    ticket = client.post(
        "/api/v1/desktop/plugins/com.synthetic.canary-plugin/download-ticket",
        json={"architecture": "windows-x64", "semver": "1.0.0"},
    )
    assert ticket.status_code == 404


def test_stable_rollback_switches_publication_without_rewriting_versions(client) -> None:
    developer_headers, _ = _register_verified(client, "stable_rollback_developer")
    private_key = Ed25519PrivateKey.generate()
    package_v1, public_key = _package(
        private_key,
        plugin_id="com.synthetic.stable-rollback",
        version="1.0.0",
    )
    project_id, signing_key_id = _create_project_and_key(
        client,
        developer_headers,
        slug="com.synthetic.stable-rollback",
        public_key_base64=public_key,
    )
    v1 = _create_version(
        client,
        developer_headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
        semver="1.0.0",
    )
    _upload(client, developer_headers, v1["id"], package_v1)
    current = _current_version(client, developer_headers, project_id)
    finalized_v1 = client.post(
        f"/api/v1/developer/plugin-versions/{v1['id']}/finalize",
        headers={**developer_headers, "Idempotency-Key": f"rollback-finalize-v1-{uuid4().hex}"},
        json={"version": current["version"]},
    )
    assert finalized_v1.status_code == 200, finalized_v1.text
    package_v2, _ = _package(
        private_key,
        plugin_id="com.synthetic.stable-rollback",
        version="1.1.0",
    )
    v2 = _create_version(
        client,
        developer_headers,
        project_id=project_id,
        signing_key_id=signing_key_id,
        semver="1.1.0",
    )
    _upload(client, developer_headers, v2["id"], package_v2)
    current_v2 = _current_version(client, developer_headers, project_id)
    finalized_v2 = client.post(
        f"/api/v1/developer/plugin-versions/{v2['id']}/finalize",
        headers={**developer_headers, "Idempotency-Key": f"rollback-finalize-v2-{uuid4().hex}"},
        json={"version": current_v2["version"]},
    )
    assert finalized_v2.status_code == 200, finalized_v2.text

    admin_headers, admin_id = _register_verified(client, "stable_rollback_admin")
    with client.app.state.database.session_factory() as db:
        admin = db.get(User, admin_id)
        assert admin is not None
        admin.role = UserRole.ADMIN
        for version_id in (v1["id"], v2["id"]):
            version = db.get(DesktopPluginVersion, version_id)
            assert version is not None
            version.status = DesktopPluginVersionStatus.APPROVED
            version.approved_capabilities = list(version.requested_capabilities)
            version.review_policy_version = "synthetic-review-policy-v1"
        db.commit()

    published_v1 = client.post(
        f"/api/v1/admin/plugin-reviews/versions/{v1['id']}/publish",
        headers={**admin_headers, "Idempotency-Key": f"rollback-publish-v1-{uuid4().hex}"},
        json={"version": finalized_v1.json()["version"], "channel": "stable"},
    )
    assert published_v1.status_code == 200, published_v1.text
    published_v2 = client.post(
        f"/api/v1/admin/plugin-reviews/versions/{v2['id']}/publish",
        headers={**admin_headers, "Idempotency-Key": f"rollback-publish-v2-{uuid4().hex}"},
        json={"version": finalized_v2.json()["version"], "channel": "stable"},
    )
    assert published_v2.status_code == 200, published_v2.text
    detail_v2 = client.get(
        f"/api/v1/admin/plugin-reviews/versions/{v2['id']}", headers=admin_headers
    ).json()
    rollback = client.post(
        f"/api/v1/admin/plugin-reviews/versions/{v2['id']}/rollback",
        headers={**admin_headers, "Idempotency-Key": "stable-rollback-integration-001"},
        json={"version": detail_v2["version"], "reason": "Synthetic stable rollback."},
    )
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["version_id"] == v1["id"]
    assert rollback.json()["semver"] == "1.0.0"

    catalog = client.get("/api/v1/desktop/plugins/catalog")
    item = next(
        item for item in catalog.json()["items"] if item["slug"] == "com.synthetic.stable-rollback"
    )
    assert item["latest_version"] == "1.0.0"
    assert (
        client.get(
            "/api/v1/desktop/plugins/com.synthetic.stable-rollback/versions/1.1.0"
        ).status_code
        == 404
    )
    with client.app.state.database.session_factory() as db:
        current_v2_row = db.get(DesktopPluginVersion, v2["id"])
        current_v1_row = db.get(DesktopPluginVersion, v1["id"])
        assert current_v2_row is not None and current_v1_row is not None
        assert current_v2_row.status == DesktopPluginVersionStatus.PUBLISHED
        assert current_v1_row.status == DesktopPluginVersionStatus.PUBLISHED
        assert current_v2_row.manifest_sha256 == finalized_v2.json()["manifest_sha256"]
        assert current_v1_row.manifest_sha256 == finalized_v1.json()["manifest_sha256"]


def test_install_event_is_privacy_minimized_and_idempotent(client) -> None:
    event = {
        "event_id": "synthetic-install-event-001",
        "plugin_slug": "com.synthetic.market-event",
        "semver": "1.0.0",
        "architecture": "windows-x64",
        "source": "local_unreviewed",
        "kind": "installed",
        "result": "success",
        "client_version": "0.1.0",
    }
    first = client.post(
        "/api/v1/desktop/plugins/install-events",
        headers={"Idempotency-Key": event["event_id"]},
        json=event,
    )
    assert first.status_code == 202, first.text
    replay = client.post(
        "/api/v1/desktop/plugins/install-events",
        headers={"Idempotency-Key": event["event_id"]},
        json=event,
    )
    assert replay.status_code == 202
    assert replay.json() == first.json()
    mismatch = client.post(
        "/api/v1/desktop/plugins/install-events",
        headers={"Idempotency-Key": "different-event-id"},
        json=event,
    )
    assert mismatch.status_code == 422


def test_authenticated_install_event_stores_validated_upgrade_evidence_and_admin_can_read_it(
    client,
) -> None:
    developer_headers, owner_id, project_id, finalized, _, _, _ = _finalized_fixture(
        client,
        "com.synthetic.upgrade-evidence",
        migration={
            "required": True,
            "from_versions": ["0.9.0"],
            "strategy": "idempotent",
        },
    )
    with client.app.state.database.session_factory() as db:
        plugin = db.get(DesktopPlugin, project_id)
        version = db.get(DesktopPluginVersion, finalized["id"])
        artifact = db.get(DesktopPluginArtifact, finalized["artifacts"][0]["id"])
        assert plugin is not None and version is not None
        assert artifact is not None
        plugin.status = DesktopPluginStatus.ACTIVE
        version.status = DesktopPluginVersionStatus.PUBLISHED
        version.approved_capabilities = list(version.requested_capabilities)
        version.signing_key_fingerprint = "a" * 64
        artifact.status = DesktopPluginArtifactStatus.PUBLIC
        artifact.zone = DesktopPluginArtifactZone.PUBLIC
        artifact.public_storage_key = artifact.storage_key or "public/synthetic.pdpkg"
        db.commit()
        requested = sorted(version.requested_capabilities)
        approved = sorted(version.approved_capabilities)

    installation_id = str(uuid4())
    installation_key = ec.generate_private_key(ec.SECP256R1())
    public_key = installation_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    registered = client.post(
        "/api/v1/desktop/installations",
        headers=developer_headers,
        json={
            "installation_id": installation_id,
            "public_key": base64.b64encode(public_key).decode(),
            "key_algorithm": "ecdsa-p256-sha256",
            "client_version": "0.1.0",
        },
    )
    assert registered.status_code == 200, registered.text

    event = {
        "event_id": "synthetic-upgrade-evidence-001",
        "plugin_slug": "com.synthetic.upgrade-evidence",
        "semver": "1.0.0",
        "architecture": "windows-x64",
        "source": "market_reviewed",
        "kind": "upgraded",
        "result": "success",
        "client_version": "0.1.0",
        "permission_evidence": {
            "requested_capabilities": requested,
            "approved_capabilities": approved,
            "granted_capabilities": requested,
            "publisher_key_fingerprint": "a" * 64,
            "risk_tier": "standard",
            "consented_at": utc_now().isoformat(),
        },
        "migration_evidence": {
            "from_version": "0.9.0",
            "to_version": "1.0.0",
            "status": "completed",
            "started_at": utc_now().isoformat(),
            "completed_at": utc_now().isoformat(),
            "steps": [
                {"step_id": "settings.copy", "status": "completed", "attempt_count": 2}
            ],
            "package_sha256": artifact.sha256,
        },
        "installation_id": installation_id,
        "evidence_signature": "x" * 64,
    }
    event["evidence_signature"] = base64.b64encode(
        installation_key.sign(
            build_install_evidence_payload(PluginInstallEventRequest.model_validate(event)),
            ec.ECDSA(hashes.SHA256()),
        )
    ).decode()
    accepted = client.post(
        "/api/v1/desktop/plugins/install-events",
        headers={**developer_headers, "Idempotency-Key": event["event_id"]},
        json=event,
    )
    assert accepted.status_code == 202, accepted.text

    admin_headers, admin_id = _register_verified(client, "upgrade_evidence_admin")
    with client.app.state.database.session_factory() as db:
        admin = db.get(User, admin_id)
        assert admin is not None
        admin.role = UserRole.ADMIN
        db.commit()
    evidence = client.get(
        "/api/v1/admin/plugin-reviews/install-evidence?page=1&page_size=20",
        headers=admin_headers,
    )
    assert evidence.status_code == 200, evidence.text
    item = next(row for row in evidence.json()["items"] if row["event_id"] == event["event_id"])
    assert item["user_id"] == owner_id
    assert item["installation_id"] == installation_id
    assert len(item["evidence_payload_hash"]) == 64
    assert item["permission_evidence"]["publisher_key_fingerprint"] == "a" * 64
    assert item["migration_evidence"]["status"] == "completed"
    assert item["migration_evidence"]["steps"][0]["attempt_count"] == 2

    anonymous = {**event, "event_id": "synthetic-upgrade-evidence-anonymous"}
    anonymous_rejected = client.post(
        "/api/v1/desktop/plugins/install-events",
        headers={"Idempotency-Key": anonymous["event_id"]},
        json=anonymous,
    )
    assert anonymous_rejected.status_code == 401
    assert anonymous_rejected.json()["code"] == (
        "desktop_plugin.evidence_authentication_required"
    )

    invalid = {**event, "event_id": "synthetic-upgrade-evidence-002"}
    invalid["permission_evidence"] = {
        **event["permission_evidence"],
        "granted_capabilities": ["network:internet"],
    }
    invalid["evidence_signature"] = base64.b64encode(
        installation_key.sign(
            build_install_evidence_payload(PluginInstallEventRequest.model_validate(invalid)),
            ec.ECDSA(hashes.SHA256()),
        )
    ).decode()
    rejected = client.post(
        "/api/v1/desktop/plugins/install-events",
        headers={**developer_headers, "Idempotency-Key": invalid["event_id"]},
        json=invalid,
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "desktop_plugin.permission_evidence_invalid"

    mismatched = {**event, "event_id": "synthetic-upgrade-evidence-003"}
    mismatched["migration_evidence"] = {
        **event["migration_evidence"],
        "package_sha256": "c" * 64,
    }
    mismatched["evidence_signature"] = base64.b64encode(
        installation_key.sign(
            build_install_evidence_payload(PluginInstallEventRequest.model_validate(mismatched)),
            ec.ECDSA(hashes.SHA256()),
        )
    ).decode()
    mismatched_rejected = client.post(
        "/api/v1/desktop/plugins/install-events",
        headers={**developer_headers, "Idempotency-Key": mismatched["event_id"]},
        json=mismatched,
    )
    assert mismatched_rejected.status_code == 422
    assert mismatched_rejected.json()["code"] == "desktop_plugin.migration_evidence_invalid"

    failed = {**event, "event_id": "synthetic-upgrade-evidence-retry-001", "result": "failure"}
    failed["permission_evidence"] = None
    failed["migration_evidence"] = {
        **event["migration_evidence"],
        "status": "failed",
        "steps": [{"step_id": "settings.copy", "status": "failed", "attempt_count": 1}],
    }
    failed["evidence_signature"] = base64.b64encode(
        installation_key.sign(
            build_install_evidence_payload(PluginInstallEventRequest.model_validate(failed)),
            ec.ECDSA(hashes.SHA256()),
        )
    ).decode()
    failed_response = client.post(
        "/api/v1/desktop/plugins/install-events",
        headers={**developer_headers, "Idempotency-Key": failed["event_id"]},
        json=failed,
    )
    assert failed_response.status_code == 202, failed_response.text
    with client.app.state.database.session_factory() as db:
        failed_row = db.scalar(
            select(DesktopPluginInstallEvent).where(
                DesktopPluginInstallEvent.event_id == failed["event_id"]
            )
        )
        assert failed_row is not None
        assert failed_row.migration_retry_status == "scheduled"
        failed_row.migration_retry_next_at = utc_now() - timedelta(seconds=1)
        db.commit()
        assert schedule_due_migration_retries(db) == {"available": 1}
    available = client.get(
        "/api/v1/desktop/plugins/migration-retries",
        headers=developer_headers,
        params={"installation_id": installation_id},
    )
    assert available.status_code == 200, available.text
    assert available.json()["items"][0]["event_id"] == failed["event_id"]

    retry_success = {**event, "event_id": "synthetic-upgrade-evidence-retry-success"}
    retry_success["evidence_signature"] = base64.b64encode(
        installation_key.sign(
            build_install_evidence_payload(PluginInstallEventRequest.model_validate(retry_success)),
            ec.ECDSA(hashes.SHA256()),
        )
    ).decode()
    completed = client.post(
        "/api/v1/desktop/plugins/install-events",
        headers={**developer_headers, "Idempotency-Key": retry_success["event_id"]},
        json=retry_success,
    )
    assert completed.status_code == 202, completed.text
    assert client.get(
        "/api/v1/desktop/plugins/migration-retries",
        headers=developer_headers,
        params={"installation_id": installation_id},
    ).json()["items"] == []

    with client.app.state.database.session_factory() as db:
        version = db.get(DesktopPluginVersion, finalized["id"])
        assert version is not None
        version.manifest_json = {**version.manifest_json, "migration": None}
        db.commit()
    undeclared = {**event, "event_id": "synthetic-upgrade-evidence-004"}
    undeclared["evidence_signature"] = base64.b64encode(
        installation_key.sign(
            build_install_evidence_payload(PluginInstallEventRequest.model_validate(undeclared)),
            ec.ECDSA(hashes.SHA256()),
        )
    ).decode()
    undeclared_rejected = client.post(
        "/api/v1/desktop/plugins/install-events",
        headers={**developer_headers, "Idempotency-Key": undeclared["event_id"]},
        json=undeclared,
    )
    assert undeclared_rejected.status_code == 422
    assert undeclared_rejected.json()["code"] == "desktop_plugin.migration_evidence_invalid"


def test_failed_market_install_event_is_accepted_for_withdrawn_version(client) -> None:
    event = {
        "event_id": "synthetic-market-failure-001",
        "plugin_slug": "com.synthetic.withdrawn-market",
        "semver": "1.0.0",
        "architecture": "windows-x64",
        "source": "market_reviewed",
        "kind": "download_failed",
        "result": "failure",
        "client_version": "0.1.0",
    }
    _, owner_id = _register_verified(client, "market_failure_owner")
    with client.app.state.database.session_factory() as db:
        plugin = DesktopPlugin(
            slug=event["plugin_slug"],
            owner_user_id=owner_id,
            name="Synthetic withdrawn market",
            summary="Synthetic",
            description="Synthetic",
            category="development",
            tags=[],
            status=DesktopPluginStatus.DRAFT,
        )
        db.add(plugin)
        db.commit()
    response = client.post(
        "/api/v1/desktop/plugins/install-events",
        headers={"Idempotency-Key": event["event_id"]},
        json=event,
    )
    assert response.status_code == 202, response.text


def test_signing_key_rotation_and_revocation_publish_signed_cache_fact(client) -> None:
    headers, _ = _register_verified(client, "plugin_key_rotation")
    first_private = Ed25519PrivateKey.generate()
    first_public = base64.b64encode(
        first_private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    ).decode()
    project = client.post(
        "/api/v1/developer/plugins",
        headers={**headers, "Idempotency-Key": f"rotation-project-{uuid4().hex}"},
        json={
            "slug": "com.synthetic.key-rotation",
            "name": "Synthetic key rotation",
            "summary": "Synthetic key rotation",
            "description": "Synthetic key rotation coverage.",
            "category": "development",
            "tags": [],
        },
    )
    assert project.status_code == 201, project.text
    first = client.post(
        "/api/v1/developer/plugins/signing-keys",
        headers={**headers, "Idempotency-Key": f"rotation-key-1-{uuid4().hex}"},
        json={
            "key_id": "synthetic-rotation-v1",
            "public_key_base64": first_public,
            "reauth_token": _reauthenticate(client, headers),
        },
    )
    assert first.status_code == 201, first.text
    second_private = Ed25519PrivateKey.generate()
    second_public = base64.b64encode(
        second_private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    ).decode()
    second = client.post(
        "/api/v1/developer/plugins/signing-keys",
        headers={**headers, "Idempotency-Key": f"rotation-key-2-{uuid4().hex}"},
        json={
            "key_id": "synthetic-rotation-v2",
            "public_key_base64": second_public,
            "rotated_from_id": first.json()["id"],
            "reauth_token": _reauthenticate(client, headers),
        },
    )
    assert second.status_code == 201, second.text
    with client.app.state.database.session_factory() as db:
        old = db.get(DesktopPluginSigningKey, first.json()["id"])
        assert old is not None
        assert old.status == DesktopPluginSigningKeyStatus.ROTATING
    revoked = client.post(
        f"/api/v1/developer/plugins/signing-keys/{second.json()['id']}/revoke",
        headers={**headers, "Idempotency-Key": f"rotation-revoke-{uuid4().hex}"},
        json={"reauth_token": _reauthenticate(client, headers)},
    )
    assert revoked.status_code == 200, revoked.text
    revocations = client.get("/api/v1/desktop/plugins/revocations")
    assert revocations.status_code == 200
    item = next(
        item for item in revocations.json()["items"] if item["scope"] == "signing_key"
    )
    assert item["signing_key_fingerprint"] == revoked.json()["fingerprint"]
    assert item["platform_signature_payload"]["scope"] == "signing_key"
