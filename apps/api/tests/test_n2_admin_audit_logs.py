from __future__ import annotations

import csv
import io

import pyotp
from sqlalchemy import select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.user import User, UserRole

PASSWORD = "SyntheticAuditPass123!"


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], dict[str, str]]:
    registration = {
        "username": f"audit_{suffix}",
        "email": f"audit-{suffix}@synthetic.example.com",
        "password": PASSWORD,
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": PASSWORD},
    )
    assert login.status_code == 200
    return registration, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _admin_headers(client) -> tuple[dict[str, str], str]:
    registration, initial_headers = _register_and_login(client, "admin")
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()
        admin_id = user.id

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
            "password": PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert authenticated.status_code == 200
    return {"Authorization": f"Bearer {authenticated.json()['access_token']}"}, admin_id


def _seed_audit_events(client, actor_id: str) -> tuple[str, str]:
    with client.app.state.database.session_factory() as db:
        first = AuditLog(
            actor_id=actor_id,
            action="synthetic.audit.review",
            target_type="synthetic_case",
            target_id="=2+2",
            result="success",
            ip_prefix="203.0.113.0/24",
            request_id="synthetic-audit-request-1",
            details={
                "reason_code": "synthetic_review",
                "password": "must-never-be-returned",
                "digest": "must-never-be-returned-either",
            },
        )
        second = AuditLog(
            actor_id=None,
            action="synthetic.audit.review",
            target_type="synthetic_case",
            target_id="case-safe-2",
            result="blocked",
            request_id="synthetic-audit-request-2",
            details={"reason_code": "synthetic_policy_block"},
        )
        db.add_all([first, second])
        db.commit()
        return first.id, second.id


def test_admin_audit_workbench_filters_details_and_export(client):
    _, ordinary_headers = _register_and_login(client, "ordinary")
    admin_headers, admin_id = _admin_headers(client)
    first_id, second_id = _seed_audit_events(client, admin_id)

    forbidden = client.get("/api/v1/admin/audit-logs", headers=ordinary_headers)
    assert forbidden.status_code == 403

    listed = client.get(
        "/api/v1/admin/audit-logs",
        headers=admin_headers,
        params={
            "action": "synthetic.audit.review",
            "result": "success",
            "query": "audit_admin",
            "page": 1,
            "page_size": 10,
        },
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == first_id
    assert body["items"][0]["actor_username"] == "audit_admin"
    assert body["items"][0]["actor_role"] == "admin"
    assert body["items"][0]["details"]["reason_code"] == "synthetic_review"
    assert body["items"][0]["details"]["password"] == "[redacted]"
    assert body["items"][0]["details"]["digest"] == "[redacted]"
    assert "must-never-be-returned" not in listed.text

    blocked = client.get(
        "/api/v1/admin/audit-logs",
        headers=admin_headers,
        params={"request_id": "synthetic-audit-request-2"},
    )
    assert blocked.status_code == 200
    assert blocked.json()["items"][0]["id"] == second_id
    assert blocked.json()["items"][0]["actor_username"] is None

    detail = client.get(f"/api/v1/admin/audit-logs/{first_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["request_id"] == "synthetic-audit-request-1"
    missing = client.get("/api/v1/admin/audit-logs/missing-synthetic", headers=admin_headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "admin.audit_log_not_found"

    invalid_range = client.get(
        "/api/v1/admin/audit-logs",
        headers=admin_headers,
        params={
            "created_from": "2026-08-03T12:00:00Z",
            "created_to": "2026-08-03T11:00:00Z",
        },
    )
    assert invalid_range.status_code == 422
    assert invalid_range.json()["code"] == "admin.audit.invalid_time_range"

    exported = client.get(
        "/api/v1/admin/audit-logs/export",
        headers=admin_headers,
        params={"action": "synthetic.audit.review"},
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "attachment;" in exported.headers["content-disposition"]
    assert exported.headers["x-exported-rows"] == "2"
    assert exported.content.startswith(b"\xef\xbb\xbf")
    decoded = exported.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(decoded)))
    assert len(rows) == 2
    first_row = next(row for row in rows if row["id"] == first_id)
    assert first_row["target_id"] == "'=2+2"
    assert "must-never-be-returned" not in decoded
    assert '"password":"[redacted]"' in first_row["details_json"]

    with client.app.state.database.session_factory() as db:
        export_log = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "admin.audit.export")
            .order_by(AuditLog.created_at.desc())
        )
        assert export_log is not None
        assert export_log.actor_id == admin_id
        assert export_log.details["exported_rows"] == 2
        assert export_log.details["filter_count"] == 1


def test_admin_audit_export_rejects_unbounded_result_set(client, monkeypatch):
    admin_headers, admin_id = _admin_headers(client)
    _seed_audit_events(client, admin_id)
    monkeypatch.setattr(
        "password_detective.modules.admin.audit_logs.EXPORT_LIMIT",
        1,
    )

    response = client.get(
        "/api/v1/admin/audit-logs/export",
        headers=admin_headers,
        params={"action": "synthetic.audit.review"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "admin.audit_export_too_large"
    assert response.json()["details"] == {"total": 2, "max_rows": 1}
