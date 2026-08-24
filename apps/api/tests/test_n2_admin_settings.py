from __future__ import annotations

import pyotp
from sqlalchemy import select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.setting_version import SystemSettingVersion
from password_detective.db.models.system_setting import SystemSetting
from password_detective.db.models.user import User, UserRole

PASSWORD = "SyntheticSettingsPass123!"


def _admin_session(client, suffix: str, role: UserRole = UserRole.ADMIN):
    registration = {
        "username": f"settings_{suffix}",
        "email": f"settings-{suffix}@synthetic.example.com",
        "password": PASSWORD,
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login", json={"login": registration["username"], "password": PASSWORD}
    )
    initial_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = role
        user_id = user.id
        db.commit()
    setup = client.post("/api/v1/admin/totp/setup", headers=initial_headers)
    secret = setup.json()["secret"]
    assert (
        client.post(
            "/api/v1/admin/totp/confirm",
            headers=initial_headers,
            json={"code": pyotp.TOTP(secret).now()},
        ).status_code
        == 200
    )
    authenticated = client.post(
        "/api/v1/auth/login",
        json={
            "login": registration["username"],
            "password": PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    return {"Authorization": f"Bearer {authenticated.json()['access_token']}"}, user_id


def _snapshot(quota: int) -> dict[str, object]:
    return {
        "site_name": "合成侦探站",
        "site_logo_url": "/api/v1/site/assets/logo/synthetic.png",
        "site_navigation": [
            {"label": "首页", "path": "/", "enabled": True, "requires_auth": False},
            {"label": "社区", "path": "/community", "enabled": True, "requires_auth": False},
        ],
        "icp_record": "合成 ICP 备 00000000 号",
        "public_security_record": "合成公网安备 00000000000000 号",
        "copyright_text": "2026 合成侦探站",
        "public_contact_email": "contact@synthetic.example.com",
        "maintenance_enabled": False,
        "maintenance_message": "系统正在维护，请稍后再试。",
        "maintenance_allowed_ip_cidrs": ["192.0.2.0/24", "2001:db8::/48"],
        "max_active_sessions": 2,
        "session_overflow_policy": "deny_new",
        "referral_reward_points": 10,
        "daily_reveal_quota": quota,
        "reauthentication_ttl_minutes": 5,
        "privacy_deletion_grace_hours": 168,
        "desktop_min_client_version": "0.1.0",
        "desktop_update_download_cache_seconds": 86400,
        "user_levels": [
            {
                "code": "rookie",
                "name": "新手侦探",
                "description": "合成用户等级",
                "min_growth_points": 0,
                "daily_reveal_quota": quota,
                "can_submit": True,
            }
        ],
    }


def test_current_settings_require_admin_and_save_directly(client) -> None:
    moderator_headers, _ = _admin_session(client, "moderator", UserRole.MODERATOR)
    assert (
        client.get("/api/v1/admin/settings/current", headers=moderator_headers).status_code == 403
    )

    headers, admin_id = _admin_session(client, "directsave")
    initial = client.get("/api/v1/admin/settings/current", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["settings"]["site_name"] == "密码侦探社"

    snapshot = _snapshot(9)
    saved = client.put(
        "/api/v1/admin/settings/current",
        headers={**headers, "Idempotency-Key": "settings-current-save-0001"},
        json=snapshot,
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["settings"] == snapshot
    assert body["updated_by"] == admin_id

    replay = client.put(
        "/api/v1/admin/settings/current",
        headers={**headers, "Idempotency-Key": "settings-current-save-0001"},
        json=snapshot,
    )
    assert replay.status_code == 200
    assert replay.json() == body

    current = client.get("/api/v1/admin/settings/current", headers=headers)
    assert current.status_code == 200
    assert current.json()["settings"] == snapshot

    site_config = client.get("/api/v1/site/config")
    assert site_config.status_code == 200
    assert site_config.json()["site_name"] == "合成侦探站"
    assert [item["path"] for item in site_config.json()["navigation"]] == ["/", "/community"]
    assert site_config.json()["legal"] == {
        "icp_record": "合成 ICP 备 00000000 号",
        "public_security_record": "合成公网安备 00000000000000 号",
        "copyright_text": "2026 合成侦探站",
        "public_contact_email": "contact@synthetic.example.com",
    }
    assert site_config.json()["maintenance"]["active"] is False

    with client.app.state.database.session_factory() as db:
        persisted = db.get(SystemSetting, "daily_reveal_quota")
        assert persisted is not None and persisted.value_json == {"value": 9}
        assert db.scalar(select(SystemSettingVersion)) is None
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "admin.settings.saved"))
        assert audit is not None
        assert audit.target_type == "system_settings"
        assert audit.actor_id == admin_id


def test_current_settings_validate_input_and_retire_version_routes(client) -> None:
    headers, _ = _admin_session(client, "validation")
    invalid = _snapshot(9)
    invalid["site_navigation"] = [
        {
            "label": "外部入口",
            "path": "https://synthetic.example.com",
            "enabled": True,
            "requires_auth": False,
        }
    ]
    rejected = client.put(
        "/api/v1/admin/settings/current",
        headers={**headers, "Idempotency-Key": "settings-current-invalid"},
        json=invalid,
    )
    assert rejected.status_code == 422

    assert client.get("/api/v1/admin/settings/versions", headers=headers).status_code == 404
    assert (
        client.post(
            "/api/v1/admin/settings/versions",
            headers={**headers, "Idempotency-Key": "retired-version-endpoint"},
            json={"snapshot": _snapshot(9)},
        ).status_code
        == 404
    )


def test_admin_can_upload_and_serve_content_addressed_site_logo(client) -> None:
    headers, _ = _admin_session(client, "logo")
    payload = b"\x89PNG\r\n\x1a\n" + b"synthetic-logo-payload"

    uploaded = client.post(
        "/api/v1/admin/settings/logo",
        headers={**headers, "Content-Type": "image/png"},
        content=payload,
    )
    assert uploaded.status_code == 201
    body = uploaded.json()
    assert body["url"].startswith("/api/v1/site/assets/logo/")
    assert body["content_type"] == "image/png"
    assert body["size_bytes"] == len(payload)
    assert len(body["sha256"]) == 64

    duplicate = client.post(
        "/api/v1/admin/settings/logo",
        headers={**headers, "Content-Type": "image/png"},
        content=payload,
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["url"] == body["url"]

    public_asset = client.get(body["url"])
    assert public_asset.status_code == 200
    assert public_asset.content == payload
    assert public_asset.headers["content-type"].startswith("image/png")
    assert public_asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert public_asset.headers["x-content-type-options"] == "nosniff"

    with client.app.state.database.session_factory() as db:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "admin.settings.site_logo_uploaded",
                AuditLog.target_id == body["sha256"],
            )
        )
        assert audit is not None
        assert audit.details["content_type"] == "image/png"
        assert audit.details["size_bytes"] == len(payload)


def test_site_logo_upload_rejects_type_and_signature_mismatch(client) -> None:
    headers, _ = _admin_session(client, "logoinvalid")
    response = client.post(
        "/api/v1/admin/settings/logo",
        headers={**headers, "Content-Type": "image/jpeg"},
        content=b"\x89PNG\r\n\x1a\nsynthetic-mismatch",
    )
    assert response.status_code == 422
    assert response.json()["code"] == "admin.site_logo_signature_invalid"

    unsupported = client.post(
        "/api/v1/admin/settings/logo",
        headers={**headers, "Content-Type": "image/svg+xml"},
        content=b"<svg></svg>",
    )
    assert unsupported.status_code == 415
    assert unsupported.json()["code"] == "admin.site_logo_content_type_invalid"
