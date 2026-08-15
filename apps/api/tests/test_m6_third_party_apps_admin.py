from __future__ import annotations

from sqlalchemy import select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.user import User, UserRole


def _admin_headers(client) -> dict[str, str]:
    registration = {
        "username": "third_party_admin",
        "email": "third-party-admin@synthetic.example.com",
        "password": "SyntheticThirdPartyAdmin123!",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_admin_can_create_draft_and_approve_third_party_app(client) -> None:
    headers = _admin_headers(client)
    created = client.post(
        "/api/v1/admin/third-party-apps",
        headers=headers,
        json={
            "name": "Synthetic Desktop",
            "developer_name": "Synthetic Developer",
            "description": "Synthetic integration",
            "redirect_uris": ["http://127.0.0.1:49152/callback"],
            "scopes": ["profile:read", "hash:read", "desktop:verification"],
        },
    )
    assert created.status_code == 201
    assert created.json()["status"] == "draft"
    assert created.json()["management_secret"]
    app_id = created.json()["id"]

    approved = client.post(
        f"/api/v1/admin/third-party-apps/{app_id}/approve",
        headers=headers,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["management_secret"] is None


def test_admin_app_controls_and_secret_rotation_are_audited(client) -> None:
    headers = _admin_headers(client)
    created = client.post(
        "/api/v1/admin/third-party-apps",
        headers=headers,
        json={
            "name": "Synthetic Controls",
            "developer_name": "Synthetic Developer",
            "redirect_uris": ["https://synthetic.example.com/oauth/callback"],
            "scopes": ["profile:read"],
        },
    )
    assert created.status_code == 201
    app_id = created.json()["id"]
    rotated = client.post(
        f"/api/v1/admin/third-party-apps/{app_id}/rotate-secret",
        headers=headers,
    )
    assert rotated.status_code == 200
    assert rotated.json()["management_secret"]
    assert rotated.json()["status"] == "draft"
    suspended = client.post(
        f"/api/v1/admin/third-party-apps/{app_id}/suspend",
        headers=headers,
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"
    restored = client.post(
        f"/api/v1/admin/third-party-apps/{app_id}/restore",
        headers=headers,
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "draft"
    revoked = client.post(
        f"/api/v1/admin/third-party-apps/{app_id}/revoke",
        headers=headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    with client.app.state.database.session_factory() as db:
        actions = {
            row.action
            for row in db.scalars(select(AuditLog).where(AuditLog.target_id == app_id)).all()
        }
    assert {
        "third_party_app.create",
        "third_party_app.rotate_secret",
        "third_party_app.suspend",
        "third_party_app.restore",
        "third_party_app.revoke",
    } <= actions


def test_admin_app_creation_rejects_duplicate_redirects_and_trusted_scope(client) -> None:
    headers = _admin_headers(client)
    payload = {
        "name": "Synthetic Invalid",
        "developer_name": "Synthetic Developer",
        "redirect_uris": [
            "https://synthetic.example.com/callback",
            "https://synthetic.example.com/callback",
        ],
        "scopes": ["profile:read", "desktop:verification:trusted"],
    }
    response = client.post("/api/v1/admin/third-party-apps", headers=headers, json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "third_party_app.invalid_request"


def test_non_admin_cannot_manage_apps_and_approved_trusted_scope_is_explicit(client) -> None:
    headers = _admin_headers(client)
    ordinary_registration = {
        "username": "third_party_ordinary",
        "email": "third-party-ordinary@synthetic.example.com",
        "password": "SyntheticThirdPartyOrdinary123!",
    }
    assert client.post("/api/v1/auth/register", json=ordinary_registration).status_code == 201
    ordinary_login = client.post(
        "/api/v1/auth/login",
        json={
            "login": ordinary_registration["username"],
            "password": ordinary_registration["password"],
        },
    )
    ordinary_headers = {"Authorization": f"Bearer {ordinary_login.json()['access_token']}"}
    forbidden = client.get("/api/v1/admin/third-party-apps", headers=ordinary_headers)
    assert forbidden.status_code == 403

    created = client.post(
        "/api/v1/admin/third-party-apps",
        headers=headers,
        json={
            "name": "Synthetic Trusted",
            "developer_name": "Synthetic Developer",
            "redirect_uris": ["http://127.0.0.1:49153/callback"],
            "scopes": ["desktop:verification"],
        },
    )
    assert created.status_code == 201
    app_id = created.json()["id"]
    approved = client.post(
        f"/api/v1/admin/third-party-apps/{app_id}/approve",
        headers=headers,
        json={"trusted_verification_enabled": True, "review_note": "Synthetic approval"},
    )
    assert approved.status_code == 200
    assert approved.json()["trusted_verification_enabled"] is True
    assert "desktop:verification:trusted" in approved.json()["approved_scopes"]
