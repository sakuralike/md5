from __future__ import annotations

import pyotp
from sqlalchemy import select

from password_detective.db.models.audit_log import AuditLog
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

def _smtp_payload(password: str | None = "synthetic-smtp-app-password") -> dict[str, object]:
    return {
        "enabled": True,
        "sender_name": "合成侦探社通知",
        "sender_email": "no-reply@synthetic.example.com",
        "subject_prefix": "[合成侦探社]",
        "footer_text": "此信为合成系统邮件，请不要直接回复。",
        "footer_html": '<a href="https://synthetic.example.com">访问合成网站</a>',
        "smtp_host": "smtp.synthetic.example.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "smtp_username": "synthetic-user",
        "smtp_auth_enabled": True,
        "smtp_timeout_seconds": 10,
        "smtp_password": password,
        "clear_smtp_password": False,
    }


def test_admin_can_save_smtp_settings_without_returning_the_password(client) -> None:
    headers, admin_id = _admin_session(client, "smtpsave")
    saved = client.put(
        "/api/v1/admin/settings/email-delivery",
        headers={**headers, "Idempotency-Key": "smtp-settings-save-0001"},
        json=_smtp_payload(),
    )

    assert saved.status_code == 200
    body = saved.json()
    assert body["sender_name"] == "合成侦探社通知"
    assert body["subject_prefix"] == "[合成侦探社]"
    assert body["smtp_password_configured"] is True
    assert "smtp_password" not in body
    assert "synthetic-smtp-app-password" not in saved.text

    loaded = client.get("/api/v1/admin/settings/email-delivery", headers=headers)
    assert loaded.status_code == 200
    assert loaded.json()["configuration_source"] == "database"
    assert loaded.json()["footer_html"] == '<a href="https://synthetic.example.com">访问合成网站</a>'
    assert "smtp_password" not in loaded.json()

    with client.app.state.database.session_factory() as db:
        stored = db.get(SystemSetting, "smtp_email_delivery")
        assert stored is not None
        assert "synthetic-smtp-app-password" not in str(stored.value_json)
        assert stored.value_json["smtp_password_ciphertext"]
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "admin.email_delivery.settings_saved")
        )
        assert audit is not None
        assert audit.actor_id == admin_id
        assert "synthetic-smtp-app-password" not in str(audit.details)


def test_blank_password_preserves_existing_secret_and_clear_removes_it(client) -> None:
    headers, _ = _admin_session(client, "smtppassword")
    initial = client.put(
        "/api/v1/admin/settings/email-delivery",
        headers={**headers, "Idempotency-Key": "smtp-settings-save-0002"},
        json=_smtp_payload(),
    )
    assert initial.status_code == 200

    preserved = client.put(
        "/api/v1/admin/settings/email-delivery",
        headers={**headers, "Idempotency-Key": "smtp-settings-save-0003"},
        json={**_smtp_payload(password=None), "sender_name": "更新后的合成侦探社"},
    )
    assert preserved.status_code == 200
    assert preserved.json()["smtp_password_configured"] is True

    cleared = client.put(
        "/api/v1/admin/settings/email-delivery",
        headers={**headers, "Idempotency-Key": "smtp-settings-save-0004"},
        json={**_smtp_payload(password=None), "clear_smtp_password": True},
    )
    assert cleared.status_code == 200
    assert cleared.json()["smtp_password_configured"] is False


def test_smtp_settings_reject_invalid_transport_combination(client) -> None:
    headers, _ = _admin_session(client, "smtpinvalid")
    rejected = client.put(
        "/api/v1/admin/settings/email-delivery",
        headers={**headers, "Idempotency-Key": "smtp-settings-invalid-0001"},
        json={**_smtp_payload(), "smtp_auth_enabled": True, "smtp_password": None},
    )

    assert rejected.status_code == 422
    assert rejected.json()["code"] == "admin.email_delivery_invalid_configuration"

def test_footer_content_accepts_multiline_plain_text_and_basic_html() -> None:
    from password_detective.modules.admin.setting_schemas import EmailDeliverySettingsUpdate

    data = _smtp_payload()
    data.update(
        {
            "footer_text": "第一行\n第二行",
            "footer_html": "<p>第一行</p>\n<p><strong>第二行</strong></p>",
        }
    )
    payload = EmailDeliverySettingsUpdate(**data)

    assert payload.footer_text == "第一行\n第二行"
    assert "<strong>第二行</strong>" in payload.footer_html

