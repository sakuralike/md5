from __future__ import annotations

import pyotp
from sqlalchemy import func, select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.trust_case import (
    TrustCase,
    TrustCaseEvent,
    TrustCaseKind,
    TrustCaseSubjectType,
)
from password_detective.db.models.user import User, UserRole


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], dict[str, str]]:
    registration = {
        "username": f"account_appeal_{suffix}",
        "email": f"account-appeal-{suffix}@synthetic.example.com",
        "password": "SyntheticAccountAppealPass123!",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    return registration, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _admin_headers(client) -> dict[str, str]:
    registration, headers = _register_and_login(client, "admin")
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()
    setup = client.post("/api/v1/admin/totp/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    confirmation = client.post(
        "/api/v1/admin/totp/confirm",
        headers=headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert confirmation.status_code == 200
    login = client.post(
        "/api/v1/auth/login",
        json={
            "login": registration["username"],
            "password": registration["password"],
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_account_appeal_is_self_scoped_idempotent_and_minimum_disclosure(client):
    registration, owner_headers = _register_and_login(client, "owner")
    _, outsider_headers = _register_and_login(client, "outsider")
    headers = {
        **owner_headers,
        "Idempotency-Key": "account-appeal-create-0001",
        "X-Request-ID": "synthetic-account-appeal-request",
    }
    payload = {
        "requested_action": "review_restriction",
        "reason_code": "account_appeal.restriction_incorrect",
        "description": "  合成账号申诉说明：请求复核当前限制。  ",
        "evidence_summary": "  合成证据摘要：仅描述时间线，不含令牌或真实个人信息。  ",
    }

    first = client.post("/api/v1/trust/account-appeals", headers=headers, json=payload)
    repeated = client.post("/api/v1/trust/account-appeals", headers=headers, json=payload)

    assert first.status_code == repeated.status_code == 201
    assert first.json()["id"] == repeated.json()["id"]
    case = first.json()
    case_id = case["id"]
    assert case["kind"] == "account_appeal"
    assert case["subject_type"] == "account"
    assert case["candidate_id"] is None
    assert case["risk_alert_id"] is None
    assert case["requested_action"] == "review_restriction"
    assert case["description"] == "合成账号申诉说明：请求复核当前限制。"
    assert case["evidence_summary"] == "合成证据摘要：仅描述时间线，不含令牌或真实个人信息。"
    assert case["events"][0]["action"] == "account_appeal.created"
    assert case["events"][0]["request_id"] == "synthetic-account-appeal-request"

    own_detail = client.get(f"/api/v1/trust/cases/{case_id}", headers=owner_headers)
    assert own_detail.status_code == 200
    assert own_detail.json()["id"] == case["id"]
    assert own_detail.json()["events"][0]["id"] == case["events"][0]["id"]
    assert client.get(f"/api/v1/trust/cases/{case_id}", headers=outsider_headers).status_code == 404
    assert client.get(f"/api/v1/trust/cases/{case_id}").status_code == 401

    mine = client.get(
        "/api/v1/trust/cases",
        headers=owner_headers,
        params={"kind": "account_appeal"},
    )
    assert mine.status_code == 200
    assert mine.json()["total"] == 1
    assert mine.json()["items"][0]["id"] == case_id

    admin_headers = _admin_headers(client)
    queue = client.get(
        "/api/v1/admin/trust-cases",
        headers=admin_headers,
        params={"kind": "account_appeal", "query": registration["username"]},
    )
    assert queue.status_code == 200
    assert queue.json()["items"][0]["id"] == case_id
    transition = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/transition",
        headers={
            **admin_headers,
            "Idempotency-Key": "account-appeal-review-0001",
            "X-Request-ID": "synthetic-account-appeal-review",
        },
        json={
            "target_status": "in_review",
            "resolution_code": "admin.review_started",
            "resolution_note": "合成处理说明：开始复核账号限制。",
        },
    )
    assert transition.status_code == 200

    premature_resolution = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/transition",
        headers={
            **admin_headers,
            "Idempotency-Key": "account-appeal-resolution-0001",
        },
        json={
            "target_status": "resolved",
            "resolution_code": "admin.appeal_upheld",
            "resolution_note": "本轮不得通过通用状态转换执行账号恢复。",
        },
    )
    assert premature_resolution.status_code == 422
    assert premature_resolution.json()["code"] == "trust.resolution_not_allowed"

    with client.app.state.database.session_factory() as db:
        owner = db.scalar(select(User).where(User.username == registration["username"]))
        stored = db.get(TrustCase, case_id)
        assert owner is not None and stored is not None
        assert stored.kind == TrustCaseKind.ACCOUNT_APPEAL
        assert stored.subject_type == TrustCaseSubjectType.ACCOUNT
        assert stored.reporter_id == stored.target_user_id == owner.id
        assert db.scalar(select(func.count(TrustCase.id))) == 1
        assert db.scalar(select(func.count(TrustCaseEvent.id))) == 2
        audits = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.target_id == case_id)
                .order_by(AuditLog.created_at)
            )
        )
        assert len(audits) == 2
        assert audits[0].action == "trust_case.account_appeal.create"
        assert audits[0].details["target_user_id"] == owner.id
        assert all("description" not in audit.details for audit in audits)
        assert all("evidence_summary" not in audit.details for audit in audits)
        assert all("resolution_note" not in audit.details for audit in audits)


def test_account_appeal_rejects_idempotency_conflicts_and_client_selected_target(client):
    _, headers = _register_and_login(client, "conflict")
    request_headers = {**headers, "Idempotency-Key": "account-appeal-conflict-0001"}
    payload = {
        "requested_action": "restore_access",
        "reason_code": "account_appeal.account_recovered",
        "description": "合成账号申诉说明。",
    }
    created = client.post(
        "/api/v1/trust/account-appeals", headers=request_headers, json=payload
    )
    assert created.status_code == 201

    conflict = client.post(
        "/api/v1/trust/account-appeals",
        headers=request_headers,
        json={**payload, "reason_code": "account_appeal.context_missing"},
    )
    assert conflict.status_code == 409

    selected_target = client.post(
        "/api/v1/trust/account-appeals",
        headers={**headers, "Idempotency-Key": "account-appeal-target-0001"},
        json={**payload, "target_user_id": "synthetic-other-user"},
    )
    assert selected_target.status_code == 422
