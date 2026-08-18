from __future__ import annotations

import pyotp
from sqlalchemy import select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.setting_version import SystemSettingVersion
from password_detective.db.models.system_setting import SystemSetting
from password_detective.db.models.user import User, UserRole

PASSWORD = "SyntheticSeoPass123!"


def _admin_session(client, suffix: str, role: UserRole = UserRole.ADMIN):
    registration = {
        "username": f"seo_{suffix}",
        "email": f"seo-{suffix}@synthetic.example.com",
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


def _seo_payload() -> dict[str, object]:
    return {
        "enabled": True,
        "indexing_enabled": True,
        "home_title": "合成侦探社首页",
        "keywords": ["密码恢复", "社区验证", "密码恢复"],
        "description": "用于合成环境的公开站点简介。",
        "title_separator": "|",
        "default_image_url": "/api/v1/site/assets/logo/synthetic.png",
        "open_graph_enabled": True,
        "sitemap_enabled": True,
    }


def test_seo_settings_require_admin_and_default_to_safe_non_indexing(client) -> None:
    moderator_headers, _ = _admin_session(client, "moderator", UserRole.MODERATOR)
    assert client.get("/api/v1/admin/settings/seo", headers=moderator_headers).status_code == 403

    headers, _ = _admin_session(client, "defaults")
    response = client.get("/api/v1/admin/settings/seo", headers=headers)
    assert response.status_code == 200
    assert response.json()["settings"] == {
        "enabled": True,
        "indexing_enabled": False,
        "home_title": "",
        "keywords": [],
        "description": "",
        "title_separator": "-",
        "default_image_url": "",
        "open_graph_enabled": True,
        "sitemap_enabled": True,
    }


def test_seo_settings_save_directly_is_idempotent_and_has_minimal_audit(client) -> None:
    headers, admin_id = _admin_session(client, "directsave")
    payload = _seo_payload()
    saved = client.put(
        "/api/v1/admin/settings/seo",
        headers={**headers, "Idempotency-Key": "seo-settings-save-0001"},
        json=payload,
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["settings"]["keywords"] == ["密码恢复", "社区验证"]
    assert body["settings"]["home_title"] == payload["home_title"]
    assert body["updated_by"] == admin_id

    replay = client.put(
        "/api/v1/admin/settings/seo",
        headers={**headers, "Idempotency-Key": "seo-settings-save-0001"},
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json() == body

    current = client.get("/api/v1/admin/settings/seo", headers=headers)
    assert current.status_code == 200
    assert current.json() == body

    with client.app.state.database.session_factory() as db:
        persisted = db.get(SystemSetting, "seo_settings")
        assert persisted is not None
        assert persisted.value_json["value"]["indexing_enabled"] is True
        assert db.scalar(select(SystemSettingVersion)) is None
        audits = db.scalars(
            select(AuditLog).where(AuditLog.action == "admin.settings.seo.saved")
        ).all()
        assert len(audits) == 1
        assert audits[0].actor_id == admin_id
        assert audits[0].target_type == "seo_settings"
        assert "description" not in audits[0].details
        assert "keywords" not in audits[0].details


def test_seo_settings_reject_unsafe_text_and_image_url(client) -> None:
    headers, _ = _admin_session(client, "validation")
    payload = _seo_payload()
    payload["home_title"] = "<script>alert(1)</script>"
    invalid_title = client.put(
        "/api/v1/admin/settings/seo",
        headers={**headers, "Idempotency-Key": "seo-invalid-title-0001"},
        json=payload,
    )
    assert invalid_title.status_code == 422

    payload = _seo_payload()
    payload["default_image_url"] = "javascript:alert(1)"
    invalid_image = client.put(
        "/api/v1/admin/settings/seo",
        headers={**headers, "Idempotency-Key": "seo-invalid-image-0001"},
        json=payload,
    )
    assert invalid_image.status_code == 422

    payload = _seo_payload()
    payload["description"] = "不允许的\n换行"
    invalid_control_character = client.put(
        "/api/v1/admin/settings/seo",
        headers={**headers, "Idempotency-Key": "seo-invalid-control-0001"},
        json=payload,
    )
    assert invalid_control_character.status_code == 422

    payload = _seo_payload()
    payload["home_title"] = "x" * 121
    invalid_length = client.put(
        "/api/v1/admin/settings/seo",
        headers={**headers, "Idempotency-Key": "seo-invalid-length-0001"},
        json=payload,
    )
    assert invalid_length.status_code == 422


def test_public_site_config_exposes_clean_seo_fields_only(client) -> None:
    headers, _ = _admin_session(client, "public")
    saved = client.put(
        "/api/v1/admin/settings/seo",
        headers={**headers, "Idempotency-Key": "seo-settings-public-0001"},
        json=_seo_payload(),
    )
    assert saved.status_code == 200

    response = client.get("/api/v1/site/config")
    assert response.status_code == 200
    body = response.json()
    assert body["seo"] == {
        "enabled": True,
        "indexing_enabled": True,
        "home_title": "合成侦探社首页",
        "keywords": ["密码恢复", "社区验证"],
        "description": "用于合成环境的公开站点简介。",
        "title_separator": "|",
        "default_image_url": "/api/v1/site/assets/logo/synthetic.png",
        "open_graph_enabled": True,
    }
    assert "sitemap_enabled" not in body["seo"]
    assert "smtp_password" not in body
    assert "token" not in body


def test_public_site_config_uses_safe_seo_defaults_for_malformed_storage(client) -> None:
    with client.app.state.database.session_factory() as db:
        db.add(SystemSetting(key="seo_settings", value_json={"value": {"keywords": "not-a-list"}}))
        db.commit()

    response = client.get("/api/v1/site/config")
    assert response.status_code == 200
    assert response.json()["seo"] == {
        "enabled": True,
        "indexing_enabled": False,
        "home_title": "",
        "keywords": [],
        "description": "",
        "title_separator": "-",
        "default_image_url": "",
        "open_graph_enabled": True,
    }


def test_public_site_config_hides_custom_fields_when_seo_is_disabled(client) -> None:
    headers, _ = _admin_session(client, "disabled")
    payload = _seo_payload()
    payload["enabled"] = False
    saved = client.put(
        "/api/v1/admin/settings/seo",
        headers={**headers, "Idempotency-Key": "seo-settings-disabled-0001"},
        json=payload,
    )
    assert saved.status_code == 200

    response = client.get("/api/v1/site/config")
    assert response.status_code == 200
    assert response.json()["seo"] == {
        "enabled": False,
        "indexing_enabled": False,
        "home_title": "",
        "keywords": [],
        "description": "",
        "title_separator": "|",
        "default_image_url": "",
        "open_graph_enabled": False,
    }
