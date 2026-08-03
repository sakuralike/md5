from __future__ import annotations

from sqlalchemy import select

from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.submission import Submission
from password_detective.db.models.verification import (
    CandidateFeedback,
    FeedbackOutcome,
    RecordStateEvent,
    VerificationEvidenceEvent,
)
from password_detective.modules.verification.service import summarize_feedbacks

SHA256 = "d" * 64
MD5 = "e" * 32


def _register_and_login(client, suffix: str) -> dict[str, str]:
    payload = {
        "username": f"detective_{suffix}",
        "email": f"detective-{suffix}@synthetic.example.com",
        "password": "SyntheticVerificationPass123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": payload["username"], "password": payload["password"]},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create_candidate(client, headers: dict[str, str], key: str = "verify-submission-0001") -> dict:
    response = client.post(
        "/api/v1/archives/submissions",
        headers={**headers, "Idempotency-Key": key},
        json={
            "fingerprints": [
                {"algorithm": "sha256", "digest": SHA256},
                {"algorithm": "md5", "digest": MD5},
            ],
            "password": "Synthetic-Verification-Candidate!",
            "authorization_confirmed": True,
            "authorization_version": "2026-08-01",
            "optional_size": 8192,
            "optional_format": "zip",
        },
    )
    assert response.status_code == 201
    return response.json()


def _feedback(
    client,
    headers: dict[str, str],
    candidate_id: str,
    outcome: str,
    key: str,
):
    return client.post(
        f"/api/v1/candidates/{candidate_id}/feedback",
        headers={**headers, "Idempotency-Key": key},
        json={"outcome": outcome},
    )


def test_two_independent_success_feedbacks_verify_and_settle_points(client):
    owner = _register_and_login(client, "owner")
    verifier_one = _register_and_login(client, "verifier_one")
    verifier_two = _register_and_login(client, "verifier_two")
    created = _create_candidate(client, owner)

    first = _feedback(
        client,
        verifier_one,
        created["candidate_id"],
        "success",
        "verification-feedback-0001",
    )
    assert first.status_code == 200
    assert first.json()["candidate_status"] == "pending"
    assert first.json()["snapshot"]["independent_success_count"] == 1
    assert first.json()["snapshot"]["needs_more_independent_success"] == 1

    second = _feedback(
        client,
        verifier_two,
        created["candidate_id"],
        "success",
        "verification-feedback-0002",
    )
    assert second.status_code == 200
    assert second.json()["candidate_status"] == "verified"
    assert second.json()["snapshot"]["independent_success_count"] == 2
    assert second.json()["snapshot"]["rule_version"] == "verification-v2"

    cached = _feedback(
        client,
        verifier_two,
        created["candidate_id"],
        "success",
        "verification-feedback-0002",
    )
    assert cached.status_code == 200
    assert cached.json() == second.json()

    unchanged = _feedback(
        client,
        verifier_two,
        created["candidate_id"],
        "success",
        "verification-feedback-unchanged-0001",
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["changed"] is False
    assert unchanged.json()["evidence_event_id"] is None

    with client.app.state.database.session_factory() as db:
        candidate = db.get(PasswordCandidate, created["candidate_id"])
        assert candidate is not None and candidate.status == CandidateStatus.VERIFIED
        assert db.query(CandidateFeedback).count() == 2
        assert db.query(VerificationEvidenceEvent).count() == 2
        transitions = list(db.scalars(select(RecordStateEvent)))
        assert len(transitions) == 1
        assert transitions[0].previous_status == CandidateStatus.PENDING
        assert transitions[0].next_status == CandidateStatus.VERIFIED
        ledgers = list(db.scalars(select(PointsLedger)))
        assert len(ledgers) == 3
        assert sum(item.amount for item in ledgers if item.status == PointsLedgerStatus.POSTED) == 3
        assert all(item.settled_at is not None for item in ledgers)

    reveal = client.post(f"/api/v1/archives/{created['archive_id']}/reveal", headers=owner)
    assert reveal.status_code == 200
    assert reveal.json()["password"] == "Synthetic-Verification-Candidate!"


def test_feedback_change_keeps_one_current_record_and_append_only_history(client):
    owner = _register_and_login(client, "history_owner")
    verifier = _register_and_login(client, "history_verifier")
    created = _create_candidate(client, owner, "verify-submission-history-0001")

    first = _feedback(
        client,
        verifier,
        created["candidate_id"],
        "success",
        "verification-history-feedback-0001",
    )
    changed = _feedback(
        client,
        verifier,
        created["candidate_id"],
        "failure",
        "verification-history-feedback-0002",
    )
    assert first.status_code == changed.status_code == 200
    assert changed.json()["revision"] == 2
    assert changed.json()["changed"] is True
    assert changed.json()["snapshot"]["independent_success_count"] == 0
    assert changed.json()["snapshot"]["independent_failure_count"] == 1

    history = client.get("/api/v1/me/feedback", headers=verifier)
    assert history.status_code == 200
    assert history.json()["total"] == 2
    newest, oldest = history.json()["items"]
    assert newest["previous_outcome"] == "success"
    assert newest["outcome"] == "failure"
    assert newest["revision"] == 2
    assert oldest["previous_outcome"] is None
    assert oldest["revision"] == 1

    search = client.get(
        "/api/v1/archives/search",
        params={"fingerprint": SHA256},
        headers=verifier,
    )
    assert search.status_code == 200
    candidate = search.json()["archive"]["candidates"][0]
    assert candidate["my_feedback"] == "failure"
    assert candidate["success_evidence_count"] == 0
    assert candidate["failure_evidence_count"] == 1

    with client.app.state.database.session_factory() as db:
        feedback = db.scalar(select(CandidateFeedback))
        assert feedback is not None
        assert feedback.outcome == FeedbackOutcome.FAILURE
        assert feedback.revision == 2
        events = list(
            db.scalars(
                select(VerificationEvidenceEvent).order_by(VerificationEvidenceEvent.revision)
            )
        )
        assert [item.outcome for item in events] == [
            FeedbackOutcome.SUCCESS,
            FeedbackOutcome.FAILURE,
        ]


def test_three_independent_failures_quarantine_verified_candidate_and_pause_reveal(client):
    owner = _register_and_login(client, "quarantine_owner")
    success_one = _register_and_login(client, "quarantine_success_one")
    success_two = _register_and_login(client, "quarantine_success_two")
    failure_headers = [
        _register_and_login(client, f"quarantine_failure_{index}") for index in range(1, 4)
    ]
    created = _create_candidate(client, owner, "verify-submission-quarantine-0001")

    assert (
        _feedback(
            client,
            success_one,
            created["candidate_id"],
            "success",
            "verification-quarantine-success-0001",
        ).status_code
        == 200
    )
    verified = _feedback(
        client,
        success_two,
        created["candidate_id"],
        "success",
        "verification-quarantine-success-0002",
    )
    assert verified.json()["candidate_status"] == "verified"

    for index, headers in enumerate(failure_headers, start=1):
        response = _feedback(
            client,
            headers,
            created["candidate_id"],
            "failure",
            f"verification-quarantine-failure-000{index}",
        )
        assert response.status_code == 200
    assert response.json()["candidate_status"] == "quarantined"
    assert response.json()["snapshot"]["independent_failure_count"] == 3

    reveal = client.post(f"/api/v1/archives/{created['archive_id']}/reveal", headers=owner)
    assert reveal.status_code == 409
    assert reveal.json()["code"] == "archive.no_revealable_candidate"

    with client.app.state.database.session_factory() as db:
        transitions = list(
            db.scalars(select(RecordStateEvent).order_by(RecordStateEvent.created_at))
        )
        assert [item.next_status for item in transitions] == [
            CandidateStatus.VERIFIED,
            CandidateStatus.QUARANTINED,
        ]
        assert transitions[-1].reason_code == "automatic.failure_threshold_reached"


def test_first_contributor_posts_and_duplicate_submission_points_reverse(client):
    owner = _register_and_login(client, "points_owner")
    verifier_one = _register_and_login(client, "points_verifier_one")
    verifier_two = _register_and_login(client, "points_verifier_two")
    created = _create_candidate(client, owner, "verify-submission-points-0001")
    duplicate = _create_candidate(client, owner, "verify-submission-points-0002")
    assert duplicate["candidate_id"] == created["candidate_id"]

    _feedback(
        client,
        verifier_one,
        created["candidate_id"],
        "success",
        "verification-points-feedback-0001",
    )
    _feedback(
        client,
        verifier_two,
        created["candidate_id"],
        "success",
        "verification-points-feedback-0002",
    )

    with client.app.state.database.session_factory() as db:
        submissions = list(
            db.scalars(select(Submission).order_by(Submission.created_at, Submission.id))
        )
        ledgers = {
            item.reference_id: item
            for item in db.scalars(
                select(PointsLedger).where(PointsLedger.event_type == "submission.pending")
            )
        }
        assert ledgers[submissions[0].id].status == PointsLedgerStatus.POSTED
        assert ledgers[submissions[1].id].status == PointsLedgerStatus.REVERSED


def test_submission_after_first_verification_is_immediately_non_rewardable(client):
    owner = _register_and_login(client, "late_owner")
    verifier_one = _register_and_login(client, "late_verify_one")
    verifier_two = _register_and_login(client, "late_verify_two")
    created = _create_candidate(client, owner, "verify-submission-late-points-0001")
    _feedback(
        client,
        verifier_one,
        created["candidate_id"],
        "success",
        "verification-late-points-feedback-0001",
    )
    _feedback(
        client,
        verifier_two,
        created["candidate_id"],
        "success",
        "verification-late-points-feedback-0002",
    )

    late = _create_candidate(client, owner, "verify-submission-late-points-0002")
    assert late["candidate_status"] == "verified"
    assert late["pending_points"] == 0
    with client.app.state.database.session_factory() as db:
        latest_submission = db.scalar(
            select(Submission).order_by(Submission.created_at.desc(), Submission.id.desc())
        )
        assert latest_submission is not None
        ledger = db.scalar(
            select(PointsLedger).where(PointsLedger.reference_id == latest_submission.id)
        )
        assert ledger is not None
        assert ledger.status == PointsLedgerStatus.REVERSED
        assert ledger.settled_at is not None


def test_same_ip_prefix_is_counted_as_one_independent_signal():
    feedbacks = [
        CandidateFeedback(
            candidate_id="candidate-synthetic",
            user_id=f"user-{index}",
            outcome=FeedbackOutcome.SUCCESS,
            weight=1.0,
            rule_version="verification-v1",
            ip_prefix="192.0.2.0/24",
        )
        for index in range(2)
    ]
    totals = summarize_feedbacks(feedbacks)
    assert totals.independent_success_count == 1
    assert totals.success_weight == 1.0
