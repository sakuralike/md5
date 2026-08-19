from __future__ import annotations

from sqlalchemy import select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.registration_invite import (
    RegistrationInvite,
    RegistrationInviteUse,
)
from password_detective.db.models.user import User, UserRole

PASSWORD = "SyntheticInvitePass123!"


def _register(client, suffix: str, *, invite_code: str | None = None):
    payload = {
        "username": f"invite_{suffix}",
        "email": f"invite-{suffix}@synthetic.example.com",
        "password": PASSWORD,
    }
    if invite_code is not None:
        payload["invite_code"] = invite_code
    return client.post("/api/v1/auth/register", json=payload)


def _admin_headers(client) -> dict[str, str]:
    registered = _register(client, "admin")
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": "invite_admin", "password": PASSWORD},
    )
    assert login.status_code == 200
    with client.app.state.database.session_factory() as db:
        admin = db.get(User, registered.json()["id"])
        assert admin is not None
        admin.role = UserRole.ADMIN
        db.commit()
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_registration_invite_policy_creation_consumption_and_revocation(client):
    admin_headers = _admin_headers(client)
    public_config = client.get("/api/v1/site/config")
    assert public_config.status_code == 200
    assert public_config.json()["registration"] == {"mode": "open"}

    saved = client.put(
        "/api/v1/admin/registration/policy",
        headers=admin_headers,
        json={"mode": "invite_only"},
    )
    assert saved.status_code == 200
    assert saved.json() == {"mode": "invite_only"}

    missing = _register(client, "missing")
    assert missing.status_code == 403
    assert missing.json()["message"] == "邀请码无效或已不可用"

    created = client.post(
        "/api/v1/admin/registration/invites",
        headers=admin_headers,
        json={"label": "合成内测批次", "max_uses": 1},
    )
    assert created.status_code == 201
    created_body = created.json()
    code = created_body["code"]
    assert code.startswith("PD-")
    assert created_body["status"] == "active"

    listed = client.get("/api/v1/admin/registration/invites", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert "code" not in listed.json()["items"][0]
    assert code not in listed.text

    accepted = _register(client, "accepted", invite_code=code)
    assert accepted.status_code == 201
    exhausted = _register(client, "exhausted", invite_code=code)
    assert exhausted.status_code == 403
    assert exhausted.json()["message"] == missing.json()["message"]

    second = client.post(
        "/api/v1/admin/registration/invites",
        headers=admin_headers,
        json={"label": "待撤销批次", "max_uses": 2},
    )
    assert second.status_code == 201
    revoked = client.post(
        f"/api/v1/admin/registration/invites/{second.json()['id']}/revoke",
        headers=admin_headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    rejected = _register(client, "revoked", invite_code=second.json()["code"])
    assert rejected.status_code == 403
    assert rejected.json()["message"] == missing.json()["message"]

    with client.app.state.database.session_factory() as db:
        invite = db.get(RegistrationInvite, created_body["id"])
        assert invite is not None
        assert invite.code_hash != code
        assert code not in str(invite.code_hash)
        assert invite.use_count == 1
        uses = db.scalars(
            select(RegistrationInviteUse).where(RegistrationInviteUse.invite_id == invite.id)
        ).all()
        assert len(uses) == 1
        audits = db.scalars(
            select(AuditLog).where(AuditLog.target_type == "registration_invite")
        ).all()
        assert audits
        assert all(code not in str(audit.details) for audit in audits)


def test_registration_invite_admin_routes_reject_non_admin(client):
    registered = _register(client, "ordinary")
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": "invite_ordinary", "password": PASSWORD},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.get("/api/v1/admin/registration/invites", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "auth.forbidden"
