from __future__ import annotations

from sqlalchemy import select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.third_party_app import (
    ThirdPartyApp,
    ThirdPartyAppSource,
    ThirdPartyAppStatus,
)
from password_detective.db.models.user import User, UserRole


def _register_login(client, username: str) -> dict[str, str]:
    payload = {
        "username": username,
        "email": f"{username}@example.com",
        "password": "SyntheticDeveloperPass123!",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    response = client.post(
        "/api/v1/auth/login",
        json={"login": username, "password": payload["password"]},
    )
    assert response.status_code == 200
    return response.json()


def _headers(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _admin_headers(client) -> dict[str, str]:
    tokens = _register_login(client, "self_service_admin")
    with client.app.state.database.session_factory() as db:
        user = db.get(User, tokens["user"]["id"])
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()
    return _headers(tokens)


def _application_payload(name: str = "Synthetic Developer Desktop") -> dict[str, object]:
    return {
        "name": name,
        "developer_name": "Synthetic Developer Team",
        "description": "Synthetic developer self-service application.",
        "website_url": "https://developer.synthetic.example.com",
        "privacy_policy_url": "https://developer.synthetic.example.com/privacy",
        "redirect_uris": ["http://127.0.0.1:49201/callback"],
        "scopes": ["profile:read", "desktop:verification"],
        "windows_release_info": "Windows 10/11 x64 signed synthetic installer",
        "use_case": "本地压缩包密码验证桌面客户端。",
    }


def test_developer_can_edit_rejected_request_and_only_approval_creates_app(client) -> None:
    developer = _register_login(client, "self_service_developer")
    headers = _headers(developer)
    created = client.post(
        "/api/v1/me/third-party-applications",
        headers=headers,
        json=_application_payload(),
    )
    assert created.status_code == 201, created.text
    request_body = created.json()
    request_id = request_body["id"]
    assert request_body["status"] == "draft"
    assert request_body["approved_application"] is None
    assert "client_id" not in request_body

    submitted = client.post(
        f"/api/v1/me/third-party-applications/{request_id}/submit",
        headers={**headers, "Idempotency-Key": "self-service-submit-001"},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending_review"

    locked = client.patch(
        f"/api/v1/me/third-party-applications/{request_id}",
        headers={**headers, "Idempotency-Key": "self-service-patch-pending-001"},
        json={"description": "This must not be accepted while pending."},
    )
    assert locked.status_code == 409
    assert locked.json()["code"] == "third_party_application.not_editable"

    admin_headers = _admin_headers(client)
    rejected = client.post(
        f"/api/v1/admin/third-party-applications/requests/{request_id}/reject",
        headers={**admin_headers, "Idempotency-Key": "self-service-reject-001"},
        json={"review_note": "请补充发行签名与隐私政策说明。"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["review_note"] == "请补充发行签名与隐私政策说明。"

    edited = client.patch(
        f"/api/v1/me/third-party-applications/{request_id}",
        headers={**headers, "Idempotency-Key": "self-service-patch-rejected-001"},
        json={
            "windows_release_info": "Windows 10/11 x64; Authenticode signer: Synthetic Team",
            "use_case": "补充说明后的本地压缩包密码验证桌面客户端。",
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "draft"
    assert edited.json()["resubmission_count"] == 1

    resubmitted = client.post(
        f"/api/v1/me/third-party-applications/{request_id}/submit",
        headers={**headers, "Idempotency-Key": "self-service-submit-002"},
    )
    assert resubmitted.status_code == 200
    assert resubmitted.json()["status"] == "pending_review"

    approved = client.post(
        f"/api/v1/admin/third-party-applications/requests/{request_id}/approve",
        headers={**admin_headers, "Idempotency-Key": "self-service-approve-001"},
        json={
            "review_note": "Synthetic approval",
            "approved_scopes": ["profile:read"],
            "trusted_verification_enabled": False,
        },
    )
    assert approved.status_code == 200, approved.text
    approved_body = approved.json()
    assert approved_body["application"]["status"] == "approved"
    assert approved_body["created_app"]["status"] == "approved"
    assert approved_body["created_app"]["application_source"] == "developer_self_service"
    assert approved_body["created_app"]["management_secret"]
    assert approved_body["created_app"]["approved_scopes"] == ["profile:read"]

    listed = client.get("/api/v1/me/third-party-applications", headers=headers)
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["status"] == "approved"
    assert item["approved_application"]["client_id"] == approved_body["created_app"]["client_id"]
    assert "management_secret" not in item["approved_application"]

    double_approval = client.post(
        f"/api/v1/admin/third-party-applications/requests/{request_id}/approve",
        headers={**admin_headers, "Idempotency-Key": "self-service-approve-002"},
        json={"approved_scopes": ["profile:read"], "trusted_verification_enabled": False},
    )
    assert double_approval.status_code == 409

    with client.app.state.database.session_factory() as db:
        apps = list(
            db.scalars(
                select(ThirdPartyApp).where(
                    ThirdPartyApp.application_source == ThirdPartyAppSource.DEVELOPER_SELF_SERVICE
                )
            ).all()
        )
        assert len(apps) == 1
        assert apps[0].status == ThirdPartyAppStatus.APPROVED
        actions = set(
            db.scalars(select(AuditLog.action).where(AuditLog.target_id == request_id)).all()
        )
    assert {
        "third_party_application.created",
        "third_party_application.submitted",
        "third_party_application.rejected",
        "third_party_application.resubmitted",
        "third_party_application.approved",
    } <= actions


def test_developer_application_requests_are_isolated_and_rejection_requires_reason(client) -> None:
    owner = _register_login(client, "self_service_owner")
    other = _register_login(client, "self_service_other")
    created = client.post(
        "/api/v1/me/third-party-applications",
        headers=_headers(owner),
        json=_application_payload("Synthetic Isolation Application"),
    )
    assert created.status_code == 201
    request_id = created.json()["id"]

    denied = client.get(
        f"/api/v1/me/third-party-applications/{request_id}",
        headers=_headers(other),
    )
    assert denied.status_code == 404

    assert (
        client.post(
            f"/api/v1/me/third-party-applications/{request_id}/submit",
            headers={**_headers(owner), "Idempotency-Key": "self-service-isolation-submit"},
        ).status_code
        == 200
    )
    admin_headers = _admin_headers(client)
    invalid_rejection = client.post(
        f"/api/v1/admin/third-party-applications/requests/{request_id}/reject",
        headers={**admin_headers, "Idempotency-Key": "self-service-empty-reject"},
        json={"review_note": "   "},
    )
    assert invalid_rejection.status_code == 422
