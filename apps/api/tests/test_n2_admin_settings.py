from __future__ import annotations

import pyotp
from sqlalchemy import select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.reauthentication_grant import ReauthenticationGrant
from password_detective.db.models.setting_version import SettingVersionStatus, SystemSettingVersion
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
    return {"Authorization": f"Bearer {authenticated.json()['access_token']}"}, user_id, secret


def _snapshot(
    quota: int, *, user_levels: list[dict[str, object]] | None = None
) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "daily_reveal_quota": quota,
        "reauthentication_ttl_minutes": 5,
        "privacy_deletion_grace_hours": 168,
        "desktop_min_client_version": "0.1.0",
        "desktop_update_download_cache_seconds": 86400,
    }
    if user_levels is not None:
        snapshot["user_levels"] = user_levels
    return snapshot


def _reauth(client, headers: dict[str, str], secret: str) -> str:
    response = client.post(
        "/api/v1/admin/auth/reauthenticate",
        headers=headers,
        json={
            "purpose": "admin_settings_governance",
            "current_password": PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["purpose"] == "admin_settings_governance"
    return response.json()["reauth_token"]


def _create(client, headers: dict[str, str], *, base: str | None, quota: int, key: str):
    return client.post(
        "/api/v1/admin/settings/versions",
        headers={**headers, "Idempotency-Key": key},
        json={
            "expected_base_version_id": base,
            "reason_code": "product_policy",
            "snapshot": _snapshot(quota),
        },
    )


def test_setting_versions_require_admin_and_publish_immutable_projection(client):
    moderator_headers, _, _ = _admin_session(client, "moderator", UserRole.MODERATOR)
    assert (
        client.get("/api/v1/admin/settings/versions", headers=moderator_headers).status_code == 403
    )

    headers, admin_id, secret = _admin_session(client, "publisher")
    created = _create(client, headers, base=None, quota=9, key="settings-create-0001")
    assert created.status_code == 201
    draft = created.json()["version"]
    assert draft["status"] == "draft"
    assert draft["differences"][0]["previous"] is None

    replay = _create(client, headers, base=None, quota=9, key="settings-create-0001")
    assert replay.status_code == 201
    assert replay.json() == created.json()

    token = _reauth(client, headers, secret)
    published = client.post(
        f"/api/v1/admin/settings/versions/{draft['id']}/publish",
        headers={**headers, "Idempotency-Key": "settings-publish-0001"},
        json={
            "expected_published_version_id": None,
            "reason_code": "product_policy",
            "reauth_token": token,
        },
    )
    assert published.status_code == 200
    body = published.json()
    assert body["version"]["status"] == "published"
    assert body["version"]["effective_at"] is not None

    with client.app.state.database.session_factory() as db:
        projection = db.get(SystemSetting, "daily_reveal_quota")
        assert projection is not None
        assert projection.value_json == {"value": 9}
        assert projection.updated_by == admin_id
        record = db.get(SystemSettingVersion, draft["id"])
        assert record is not None and record.status == SettingVersionStatus.PUBLISHED
        grant = db.scalar(
            select(ReauthenticationGrant).where(ReauthenticationGrant.user_id == admin_id)
        )
        assert grant is not None and grant.purpose == "admin_settings_governance"
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "admin.settings.published"))
        assert audit is not None
        assert "reauth_token" not in str(audit.details)


def test_setting_publish_conflict_preserves_grant_and_rollback_creates_new_version(client):
    headers, _, secret = _admin_session(client, "rollback")
    first = _create(client, headers, base=None, quota=7, key="settings-create-first")
    first_id = first.json()["version"]["id"]
    token = _reauth(client, headers, secret)
    assert (
        client.post(
            f"/api/v1/admin/settings/versions/{first_id}/publish",
            headers={**headers, "Idempotency-Key": "settings-publish-first"},
            json={
                "expected_published_version_id": None,
                "reason_code": "product_policy",
                "reauth_token": token,
            },
        ).status_code
        == 200
    )

    second = _create(client, headers, base=first_id, quota=13, key="settings-create-second")
    second_id = second.json()["version"]["id"]
    token = _reauth(client, headers, secret)
    conflict = client.post(
        f"/api/v1/admin/settings/versions/{second_id}/publish",
        headers={**headers, "Idempotency-Key": "settings-publish-conflict"},
        json={
            "expected_published_version_id": None,
            "reason_code": "capacity_adjustment",
            "reauth_token": token,
        },
    )
    assert conflict.status_code == 409
    published = client.post(
        f"/api/v1/admin/settings/versions/{second_id}/publish",
        headers={**headers, "Idempotency-Key": "settings-publish-second"},
        json={
            "expected_published_version_id": first_id,
            "reason_code": "capacity_adjustment",
            "reauth_token": token,
        },
    )
    assert published.status_code == 200

    rollback_token = _reauth(client, headers, secret)
    rolled_back = client.post(
        f"/api/v1/admin/settings/versions/{first_id}/rollback",
        headers={**headers, "Idempotency-Key": "settings-rollback-first"},
        json={
            "expected_published_version_id": second_id,
            "reason_code": "rollback",
            "reauth_token": rollback_token,
        },
    )
    assert rolled_back.status_code == 200
    rollback_version = rolled_back.json()["version"]
    assert rollback_version["id"] not in {first_id, second_id}
    assert rollback_version["rollback_of_id"] == first_id
    assert rollback_version["snapshot"]["daily_reveal_quota"] == 7

    versions = client.get("/api/v1/admin/settings/versions", headers=headers)
    assert versions.status_code == 200
    assert versions.json()["published_version_id"] == rollback_version["id"]
    with client.app.state.database.session_factory() as db:
        assert db.get(SystemSetting, "daily_reveal_quota").value_json == {"value": 7}


def test_level_rules_publish_rebuilds_profiles_and_rejects_invalid_thresholds(client):
    headers, admin_id, secret = _admin_session(client, "level_rules")
    levels = [
        {
            "code": "rookie",
            "name": "新手侦探",
            "description": "合成测试基础等级。",
            "min_growth_points": 0,
            "daily_reveal_quota": 10,
            "can_submit": True,
        },
        {
            "code": "active",
            "name": "活跃侦探",
            "description": "完成当日活跃后的合成测试等级。",
            "min_growth_points": 5,
            "daily_reveal_quota": 35,
            "can_submit": True,
        },
    ]
    created = client.post(
        "/api/v1/admin/settings/versions",
        headers={**headers, "Idempotency-Key": "settings-level-create-0001"},
        json={
            "expected_base_version_id": None,
            "reason_code": "product_policy",
            "snapshot": _snapshot(20, user_levels=levels),
        },
    )
    assert created.status_code == 201
    draft = created.json()["version"]
    level_difference = next(
        item for item in draft["differences"] if item["key"] == "user_levels"
    )
    assert level_difference["current"] == levels

    published = client.post(
        f"/api/v1/admin/settings/versions/{draft['id']}/publish",
        headers={**headers, "Idempotency-Key": "settings-level-publish-0001"},
        json={
            "expected_published_version_id": None,
            "reason_code": "product_policy",
            "reauth_token": _reauth(client, headers, secret),
        },
    )
    assert published.status_code == 200
    profile = client.get("/api/v1/me/level", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["growth_points"] == 5
    assert profile.json()["current"]["code"] == "active"
    with client.app.state.database.session_factory() as db:
        stored = db.get(SystemSetting, "user_levels")
        assert stored is not None
        assert stored.value_json == {"value": levels}
        audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "admin.settings.published")
            .order_by(AuditLog.created_at.desc())
        )
        assert audit is not None
        assert audit.details["rebuilt_level_profiles"] >= 1
        assert db.get(User, admin_id) is not None

    invalid_levels = [levels[1], levels[0]]
    invalid = client.post(
        "/api/v1/admin/settings/versions",
        headers={**headers, "Idempotency-Key": "settings-level-invalid-0001"},
        json={
            "expected_base_version_id": draft["id"],
            "reason_code": "product_policy",
            "snapshot": _snapshot(20, user_levels=invalid_levels),
        },
    )
    assert invalid.status_code == 422
