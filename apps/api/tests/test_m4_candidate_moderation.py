from __future__ import annotations

import pyotp
from sqlalchemy import func, select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.user import User, UserRole
from password_detective.db.models.verification import RecordStateEvent, StateTransitionSource

SHA256 = "7" * 64
MD5 = "8" * 32


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], dict[str, str]]:
    registration = {
        "username": f"moderation_{suffix}",
        "email": f"moderation-{suffix}@synthetic.example.com",
        "password": "SyntheticModerationPass123!",
    }
    response = client.post("/api/v1/auth/register", json=registration)
    assert response.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    return registration, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _admin_headers(client, suffix: str = "admin") -> dict[str, str]:
    registration, initial_headers = _register_and_login(client, suffix)
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()

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
            "password": registration["password"],
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert authenticated.status_code == 200
    return {"Authorization": f"Bearer {authenticated.json()['access_token']}"}


def _create_candidate(client, headers: dict[str, str], suffix: str = "0001") -> dict:
    response = client.post(
        "/api/v1/archives/submissions",
        headers={**headers, "Idempotency-Key": f"moderation-submission-{suffix}"},
        json={
            "fingerprints": [
                {"algorithm": "sha256", "digest": SHA256},
                {"algorithm": "md5", "digest": MD5},
            ],
            "password": "Synthetic-Moderation-Candidate!",
            "authorization_confirmed": True,
            "authorization_version": "2026-08-01",
            "optional_size": 16384,
            "optional_format": "7z",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_candidate_review_requires_admin_mfa_and_never_exposes_secret_material(client):
    _, owner_headers = _register_and_login(client, "owner")
    created = _create_candidate(client, owner_headers)

    forbidden = client.get("/api/v1/admin/candidates", headers=owner_headers)
    assert forbidden.status_code == 403

    admin_headers = _admin_headers(client)
    review = client.get(
        "/api/v1/admin/candidates",
        headers=admin_headers,
        params={"status": "pending", "query": SHA256[:20]},
    )
    assert review.status_code == 200
    body = review.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == created["candidate_id"]
    serialized = str(body).lower()
    for forbidden_field in ("password", "ciphertext", "nonce", "dedup", "secret"):
        assert forbidden_field not in serialized

    detail = client.get(
        f"/api/v1/admin/candidates/{created['candidate_id']}",
        headers=admin_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["evidence_snapshot"]["independent_success_count"] == 0
    assert detail.json()["fingerprints"][0]["digest"] in {SHA256, MD5}


def test_manual_transition_is_idempotent_audited_and_locks_rejected_feedback(client):
    _, owner_headers = _register_and_login(client, "transition_owner")
    _, verifier_headers = _register_and_login(client, "transition_verifier")
    created = _create_candidate(client, owner_headers, "0002")
    admin_headers = _admin_headers(client, "transition_admin")
    candidate_id = created["candidate_id"]
    request_headers = {
        **admin_headers,
        "Idempotency-Key": "moderation-transition-0001",
        "X-Request-ID": "synthetic-moderation-request-0001",
    }
    payload = {
        "target_status": "rejected",
        "reason_code": "manual.invalid_candidate",
        "reason_note": "合成审核说明：候选与指纹证据不一致。",
    }

    first = client.post(
        f"/api/v1/admin/candidates/{candidate_id}/transition",
        headers=request_headers,
        json=payload,
    )
    assert first.status_code == 200
    assert first.json()["previous_status"] == "pending"
    assert first.json()["current_status"] == "rejected"
    assert first.json()["request_id"] == "synthetic-moderation-request-0001"

    cached = client.post(
        f"/api/v1/admin/candidates/{candidate_id}/transition",
        headers=request_headers,
        json=payload,
    )
    assert cached.status_code == 200
    assert cached.json() == first.json()

    with client.app.state.database.session_factory() as db:
        candidate = db.get(PasswordCandidate, candidate_id)
        assert candidate is not None
        assert candidate.status == CandidateStatus.REJECTED
        manual_events = list(
            db.scalars(
                select(RecordStateEvent).where(
                    RecordStateEvent.candidate_id == candidate_id,
                    RecordStateEvent.transition_source == StateTransitionSource.MANUAL,
                )
            )
        )
        assert len(manual_events) == 1
        event = manual_events[0]
        assert event.reason_note == payload["reason_note"]
        assert event.request_id == "synthetic-moderation-request-0001"
        audit_count = db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == "candidate.manual_transition",
                AuditLog.target_id == candidate_id,
                AuditLog.request_id == "synthetic-moderation-request-0001",
            )
        )
        assert audit_count == 1
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "candidate.manual_transition",
                AuditLog.target_id == candidate_id,
            )
        )
        assert audit is not None
        assert "reason_note" not in audit.details
        assert "password" not in str(audit.details).lower()

    feedback = client.post(
        f"/api/v1/candidates/{candidate_id}/feedback",
        headers={**verifier_headers, "Idempotency-Key": "moderation-feedback-0001"},
        json={"outcome": "success"},
    )
    assert feedback.status_code == 409
    assert feedback.json()["code"] == "verification.rejected_candidate_locked"


def test_manual_transition_rejects_key_reuse_and_invalid_reason_target(client):
    _, owner_headers = _register_and_login(client, "conflict_owner")
    created = _create_candidate(client, owner_headers, "0003")
    admin_headers = _admin_headers(client, "conflict_admin")
    candidate_id = created["candidate_id"]
    headers = {**admin_headers, "Idempotency-Key": "moderation-transition-conflict"}

    quarantined = client.post(
        f"/api/v1/admin/candidates/{candidate_id}/transition",
        headers=headers,
        json={
            "target_status": "quarantined",
            "reason_code": "manual.evidence_conflict",
        },
    )
    assert quarantined.status_code == 200

    reused = client.post(
        f"/api/v1/admin/candidates/{candidate_id}/transition",
        headers=headers,
        json={
            "target_status": "pending",
            "reason_code": "manual.review_reopened",
        },
    )
    assert reused.status_code == 409
    assert reused.json()["code"] == "request.idempotency_conflict"

    mismatch = client.post(
        f"/api/v1/admin/candidates/{candidate_id}/transition",
        headers={**admin_headers, "Idempotency-Key": "moderation-transition-mismatch"},
        json={
            "target_status": "verified",
            "reason_code": "manual.invalid_candidate",
        },
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["code"] == "moderation.reason_target_mismatch"
