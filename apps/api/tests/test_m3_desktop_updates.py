from __future__ import annotations

import hashlib
from pathlib import Path

import pyotp
from sqlalchemy import select

from password_detective.db.models.desktop_update import DesktopRelease
from password_detective.db.models.user import User, UserRole


def _admin_headers(client) -> dict[str, str]:
    registration = {
        "username": "update_admin",
        "email": "update-admin@synthetic.example.com",
        "password": "SyntheticUpdateAdmin123!",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    initial_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()

    setup = client.post("/api/v1/admin/totp/setup", headers=initial_headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    confirm = client.post(
        "/api/v1/admin/totp/confirm",
        headers=initial_headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert confirm.status_code == 200
    authenticated = client.post(
        "/api/v1/auth/login",
        json={
            "login": registration["username"],
            "password": registration["password"],
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert authenticated.status_code == 200
    return {"Authorization": f"Bearer {authenticated.json()['access_token']}"}


def _release_payload(artifact: bytes, *, version: str = "0.2.0", signature: str = "test_signed"):
    return {
        "channel": "stable",
        "platform": "windows",
        "architecture": "x64",
        "version": version,
        "minimum_supported_version": "0.1.0",
        "mandatory": False,
        "release_notes": "合成发布说明：改进更新检查。",
        "artifact_filename": f"password-detective-{version}-x64.msix",
        "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
        "artifact_size_bytes": len(artifact),
        "content_type": "application/msix",
        "code_signature_status": signature,
    }


def test_desktop_update_release_upload_publish_check_download_and_withdraw(client):
    empty = client.get(
        "/api/v1/desktop/updates/check",
        params={"current_version": "0.1.0", "architecture": "x64"},
    )
    assert empty.status_code == 200
    assert empty.json()["update_available"] is False

    admin_headers = _admin_headers(client)
    artifact = b"synthetic-msix-artifact-for-update-channel"
    created = client.post(
        "/api/v1/admin/desktop-releases",
        headers=admin_headers,
        json=_release_payload(artifact),
    )
    assert created.status_code == 201
    release_id = created.json()["id"]
    assert created.json()["artifact_uploaded"] is False

    rejected = client.put(
        f"/api/v1/admin/desktop-releases/{release_id}/artifact",
        headers={**admin_headers, "Content-Type": "application/octet-stream"},
        content=b"wrong",
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "desktop.update.artifact_integrity_mismatch"

    uploaded = client.put(
        f"/api/v1/admin/desktop-releases/{release_id}/artifact",
        headers={**admin_headers, "Content-Type": "application/octet-stream"},
        content=artifact,
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["artifact_uploaded"] is True

    published = client.post(
        f"/api/v1/admin/desktop-releases/{release_id}/publish",
        headers=admin_headers,
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    update = client.get(
        "/api/v1/desktop/updates/check",
        params={"current_version": "0.1.0", "channel": "stable", "architecture": "x64"},
    )
    assert update.status_code == 200
    update_body = update.json()
    assert update_body["update_available"] is True
    assert update_body["latest_version"] == "0.2.0"
    assert update_body["artifact_sha256"] == hashlib.sha256(artifact).hexdigest()
    assert update_body["download_url"].endswith(f"/api/v1/desktop/updates/{release_id}/download")

    downloaded = client.get(f"/api/v1/desktop/updates/{release_id}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == artifact
    assert downloaded.headers["digest"].startswith("sha-256=")
    assert "immutable" in downloaded.headers["cache-control"]

    current = client.get(
        "/api/v1/desktop/updates/check",
        params={"current_version": "0.2.0", "architecture": "x64"},
    )
    assert current.status_code == 200
    assert current.json()["update_available"] is False

    listed = client.get("/api/v1/admin/desktop-releases", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["download_count"] == 1

    with client.app.state.database.session_factory() as db:
        release = db.get(DesktopRelease, release_id)
        assert release is not None
        assert release.artifact_storage_key is not None
        artifact_path = (
            Path(client.app.state.settings.desktop_update_storage_path)
            / release.artifact_storage_key
        )
        artifact_path.write_bytes(b"tampered-synthetic-artifact")
    corrupted = client.get(f"/api/v1/desktop/updates/{release_id}/download")
    assert corrupted.status_code == 409
    assert corrupted.json()["code"] == "desktop.update.artifact_integrity_mismatch"

    withdrawn = client.post(
        f"/api/v1/admin/desktop-releases/{release_id}/withdraw",
        headers=admin_headers,
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "withdrawn"
    assert client.get(f"/api/v1/desktop/updates/{release_id}/download").status_code == 404


def test_update_channel_rejects_invalid_versions_and_unsigned_production_release(client):
    invalid = client.get(
        "/api/v1/desktop/updates/check",
        params={"current_version": "latest", "architecture": "x64"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "desktop.update.invalid_version"

    admin_headers = _admin_headers(client)
    artifact = b"synthetic-unsigned-production-artifact"
    created = client.post(
        "/api/v1/admin/desktop-releases",
        headers=admin_headers,
        json=_release_payload(artifact, version="0.3.0", signature="unsigned"),
    )
    assert created.status_code == 201
    release_id = created.json()["id"]
    assert (
        client.put(
            f"/api/v1/admin/desktop-releases/{release_id}/artifact",
            headers=admin_headers,
            content=artifact,
        ).status_code
        == 200
    )

    client.app.state.settings.app_env = "production"
    try:
        publish = client.post(
            f"/api/v1/admin/desktop-releases/{release_id}/publish",
            headers=admin_headers,
        )
    finally:
        client.app.state.settings.app_env = "test"
    assert publish.status_code == 409
    assert publish.json()["code"] == "desktop.update.verified_signature_required"

    with client.app.state.database.session_factory() as db:
        release = db.get(DesktopRelease, release_id)
        assert release is not None
        assert release.status.value == "draft"
