from __future__ import annotations

import pyotp
from sqlalchemy import func, select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.trust_case import TrustCase, TrustCaseEvent
from password_detective.db.models.user import User, UserRole


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], dict[str, str]]:
    registration = {
        "username": f"trust_{suffix}",
        "email": f"trust-{suffix}@synthetic.example.com",
        "password": "SyntheticTrustCasePass123!",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    return registration, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _admin_headers(client, suffix: str = "admin") -> dict[str, str]:
    registration, headers = _register_and_login(client, suffix)
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()
    setup = client.post("/api/v1/admin/totp/setup", headers=headers)
    secret = setup.json()["secret"]
    assert (
        client.post(
            "/api/v1/admin/totp/confirm",
            headers=headers,
            json={"code": pyotp.TOTP(secret).now()},
        ).status_code
        == 200
    )
    login = client.post(
        "/api/v1/auth/login",
        json={
            "login": registration["username"],
            "password": registration["password"],
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create_candidate(client, headers: dict[str, str], suffix: str) -> str:
    digit = str((int(suffix) % 8) + 1)
    response = client.post(
        "/api/v1/archives/submissions",
        headers={**headers, "Idempotency-Key": f"trust-submission-{suffix.zfill(4)}"},
        json={
            "fingerprints": [{"algorithm": "sha256", "digest": digit * 64}],
            "password": f"Synthetic-Trust-Candidate-{suffix}!",
            "authorization_confirmed": True,
            "authorization_version": "2026-08-02",
        },
    )
    assert response.status_code == 201
    return response.json()["candidate_id"]


def test_report_creation_is_idempotent_private_and_admin_audited(client):
    reporter, reporter_headers = _register_and_login(client, "reporter")
    _, other_headers = _register_and_login(client, "other")
    candidate_id = _create_candidate(client, reporter_headers, "1")
    request_headers = {
        **reporter_headers,
        "Idempotency-Key": "trust-report-create-0001",
        "X-Request-ID": "synthetic-trust-report-request",
    }
    payload = {
        "candidate_id": candidate_id,
        "reason_code": "report.invalid_candidate",
        "description": "合成举报说明：候选与测试样本不一致。",
    }
    first = client.post("/api/v1/trust/reports", headers=request_headers, json=payload)
    second = client.post("/api/v1/trust/reports", headers=request_headers, json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    case_id = first.json()["id"]

    mine = client.get("/api/v1/trust/cases", headers=reporter_headers)
    assert mine.status_code == 200
    assert mine.json()["total"] == 1
    assert mine.json()["items"][0]["reporter_username"] == reporter["username"]
    assert client.get("/api/v1/trust/cases", headers=other_headers).json()["total"] == 0
    assert client.get("/api/v1/admin/trust-cases", headers=reporter_headers).status_code == 403

    admin_headers = _admin_headers(client)
    queue = client.get(
        "/api/v1/admin/trust-cases",
        headers=admin_headers,
        params={"kind": "report", "status": "open", "query": reporter["username"]},
    )
    assert queue.status_code == 200
    assert queue.json()["items"][0]["id"] == case_id

    transition_headers = {
        **admin_headers,
        "Idempotency-Key": "trust-case-transition-0001",
        "X-Request-ID": "synthetic-trust-transition-request",
    }
    transition_payload = {
        "expected_version": 1,
        "target_status": "in_review",
        "resolution_code": "admin.review_started",
        "resolution_note": "合成处理说明：进入人工核查。",
    }
    first_transition = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/transition",
        headers=transition_headers,
        json=transition_payload,
    )
    repeated_transition = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/transition",
        headers=transition_headers,
        json=transition_payload,
    )
    assert first_transition.status_code == repeated_transition.status_code == 200
    assert first_transition.json()["event_id"] == repeated_transition.json()["event_id"]

    with client.app.state.database.session_factory() as db:
        assert db.scalar(select(func.count(TrustCase.id))) == 1
        assert db.scalar(select(func.count(TrustCaseEvent.id))) == 2
        audits = list(
            db.scalars(
                select(AuditLog).where(AuditLog.target_id == case_id).order_by(AuditLog.created_at)
            )
        )
        assert len(audits) == 2
        assert all("description" not in audit.details for audit in audits)
        assert all("resolution_note" not in audit.details for audit in audits)


def test_only_contributor_can_appeal_rejected_or_quarantined_candidate(client):
    _, owner_headers = _register_and_login(client, "appeal_owner")
    _, outsider_headers = _register_and_login(client, "appeal_outsider")
    candidate_id = _create_candidate(client, owner_headers, "2")
    admin_headers = _admin_headers(client, "appeal_admin")

    pending_appeal = client.post(
        "/api/v1/trust/appeals",
        headers={**owner_headers, "Idempotency-Key": "trust-appeal-pending-0001"},
        json={
            "candidate_id": candidate_id,
            "reason_code": "appeal.new_evidence",
            "description": "合成申诉说明。",
        },
    )
    assert pending_appeal.status_code == 409

    rejected = client.post(
        f"/api/v1/admin/candidates/{candidate_id}/transition",
        headers={**admin_headers, "Idempotency-Key": "trust-reject-candidate-0001"},
        json={
            "target_status": "rejected",
            "reason_code": "manual.invalid_candidate",
            "reason_note": "合成审核说明。",
        },
    )
    assert rejected.status_code == 200

    outsider = client.post(
        "/api/v1/trust/appeals",
        headers={**outsider_headers, "Idempotency-Key": "trust-appeal-outsider-0001"},
        json={
            "candidate_id": candidate_id,
            "reason_code": "appeal.decision_incorrect",
            "description": "合成越权申诉。",
        },
    )
    assert outsider.status_code == 403

    owner = client.post(
        "/api/v1/trust/appeals",
        headers={**owner_headers, "Idempotency-Key": "trust-appeal-owner-0001"},
        json={
            "candidate_id": candidate_id,
            "reason_code": "appeal.new_evidence",
            "description": "合成申诉说明：已补充新的验证证据。",
        },
    )
    assert owner.status_code == 201
    assert owner.json()["kind"] == "appeal"


def test_case_transition_rejects_code_mismatch_and_idempotency_payload_conflict(client):
    _, headers = _register_and_login(client, "conflict_owner")
    candidate_id = _create_candidate(client, headers, "3")
    created = client.post(
        "/api/v1/trust/reports",
        headers={**headers, "Idempotency-Key": "trust-report-conflict-0001"},
        json={"candidate_id": candidate_id, "reason_code": "report.policy_violation"},
    )
    case_id = created.json()["id"]
    admin_headers = _admin_headers(client, "conflict_admin")

    mismatch = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/transition",
        headers={**admin_headers, "Idempotency-Key": "trust-transition-mismatch-0001"},
        json={
            "expected_version": 1,
            "target_status": "resolved",
            "resolution_code": "admin.review_started",
        },
    )
    assert mismatch.status_code == 422

    wrong_case_kind = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/transition",
        headers={**admin_headers, "Idempotency-Key": "trust-transition-kind-0001"},
        json={
            "expected_version": 1,
            "target_status": "resolved",
            "resolution_code": "admin.appeal_upheld",
        },
    )
    assert wrong_case_kind.status_code == 422
    assert wrong_case_kind.json()["code"] == "trust.resolution_not_allowed"

    key_headers = {**admin_headers, "Idempotency-Key": "trust-transition-conflict-0001"}
    first = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/transition",
        headers=key_headers,
        json={
            "expected_version": 1,
            "target_status": "dismissed",
            "resolution_code": "admin.no_violation",
        },
    )
    assert first.status_code == 200
    conflict = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/transition",
        headers=key_headers,
        json={"expected_version": 1, "target_status": "open", "resolution_code": "admin.reopened"},
    )
    assert conflict.status_code == 409
