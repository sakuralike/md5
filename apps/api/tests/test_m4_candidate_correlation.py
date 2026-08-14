from __future__ import annotations

from datetime import UTC, datetime

import pyotp
from sqlalchemy import select

from password_detective.db.models.evidence_correlation import EvidenceCorrelationAssessment
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.user import User, UserRole
from password_detective.db.models.verification import (
    CandidateFeedback,
    FeedbackOutcome,
    VerificationSource,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.correlation.analysis import analyze_feedback_correlations
from password_detective.modules.verification.service import apply_candidate_evidence

SHA256 = "c" * 64
MD5 = "d" * 32


def _feedback(
    feedback_id: str,
    user_id: str,
    *,
    outcome: FeedbackOutcome,
    installation: str | None,
    ip_prefix: str | None,
    weight: float = 1.0,
) -> CandidateFeedback:
    return CandidateFeedback(
        id=feedback_id,
        candidate_id="candidate-synthetic",
        user_id=user_id,
        outcome=outcome,
        source=VerificationSource.WEB_FEEDBACK,
        weight=weight,
        rule_version="verification-v2",
        installation_id_hash=installation,
        ip_prefix=ip_prefix,
        revision=1,
        created_at=datetime(2026, 8, 3, tzinfo=UTC),
    )


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], dict[str, str]]:
    registration = {
        "username": f"correlation_{suffix}",
        "email": f"correlation-{suffix}@synthetic.example.com",
        "password": "SyntheticCorrelationPass123!",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    return registration, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _admin_headers(client) -> dict[str, str]:
    registration, initial_headers = _register_and_login(client, "admin")
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()
    setup = client.post("/api/v1/admin/totp/setup", headers=initial_headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert (
        client.post(
            "/api/v1/admin/totp/confirm",
            headers=initial_headers,
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
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create_candidate(client, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/archives/submissions",
        headers={**headers, "Idempotency-Key": "correlation-submission-synthetic-0001"},
        json={
            "fingerprints": [
                {"algorithm": "sha256", "digest": SHA256},
                {"algorithm": "md5", "digest": MD5},
            ],
            "password": "Synthetic-Correlation-Candidate!",
            "authorization_confirmed": True,
            "authorization_version": "2026-08-03",
            "optional_size": 32768,
            "optional_format": "zip",
        },
    )
    assert response.status_code == 201
    return response.json()["candidate_id"]


def test_connected_components_apply_transitive_installation_and_ip_downweighting():
    feedbacks = [
        _feedback(
            "feedback-01",
            "user-01",
            outcome=FeedbackOutcome.SUCCESS,
            installation="installation-a",
            ip_prefix="192.0.2.0/24",
        ),
        _feedback(
            "feedback-02",
            "user-02",
            outcome=FeedbackOutcome.SUCCESS,
            installation="installation-b",
            ip_prefix="192.0.2.0/24",
            weight=1.25,
        ),
        _feedback(
            "feedback-03",
            "user-03",
            outcome=FeedbackOutcome.SUCCESS,
            installation="installation-b",
            ip_prefix="198.51.100.0/24",
        ),
        _feedback(
            "feedback-04",
            "user-04",
            outcome=FeedbackOutcome.FAILURE,
            installation=None,
            ip_prefix=None,
        ),
    ]

    analysis = analyze_feedback_correlations(feedbacks)

    assert analysis.feedback_count == 4
    assert analysis.independent_group_count == 2
    assert analysis.correlated_group_count == 1
    assert analysis.downweighted_feedback_count == 2
    assert analysis.independent_success_count == 1
    assert analysis.independent_failure_count == 1
    assert analysis.raw_success_weight == 3.25
    assert analysis.effective_success_weight == 1.25
    correlated = next(group for group in analysis.groups if group.member_count == 3)
    assert correlated.shared_signals == ("installation", "ip_prefix")
    assert correlated.user_ids == ("user-01", "user-02", "user-03")


def test_correlation_group_caps_success_and_failure_weights_independently():
    feedbacks = [
        _feedback(
            "feedback-success-01",
            "user-success-01",
            outcome=FeedbackOutcome.SUCCESS,
            installation=None,
            ip_prefix="203.0.113.0/24",
        ),
        _feedback(
            "feedback-success-02",
            "user-success-02",
            outcome=FeedbackOutcome.SUCCESS,
            installation=None,
            ip_prefix="203.0.113.0/24",
            weight=1.25,
        ),
        _feedback(
            "feedback-failure-01",
            "user-failure-01",
            outcome=FeedbackOutcome.FAILURE,
            installation=None,
            ip_prefix="203.0.113.0/24",
        ),
        _feedback(
            "feedback-failure-02",
            "user-failure-02",
            outcome=FeedbackOutcome.FAILURE,
            installation=None,
            ip_prefix="203.0.113.0/24",
            weight=1.5,
        ),
    ]

    analysis = analyze_feedback_correlations(feedbacks)

    assert analysis.independent_group_count == 1
    assert analysis.independent_success_count == 1
    assert analysis.independent_failure_count == 1
    assert analysis.downweighted_feedback_count == 2
    assert analysis.raw_success_weight == 2.25
    assert analysis.effective_success_weight == 1.25
    assert analysis.raw_failure_weight == 2.5
    assert analysis.effective_failure_weight == 1.5



def test_correlation_assessments_are_persisted_and_exposed_without_raw_signals(client):
    owner_registration, owner_headers = _register_and_login(client, "owner")
    voter_registrations = [
        _register_and_login(client, f"voter_{index}")[0] for index in range(1, 6)
    ]
    candidate_id = _create_candidate(client, owner_headers)

    with client.app.state.database.session_factory() as db:
        candidate = db.get(PasswordCandidate, candidate_id)
        assert candidate is not None
        voters = [
            db.scalar(select(User).where(User.username == registration["username"]))
            for registration in voter_registrations
        ]
        assert all(voter is not None for voter in voters)
        for index, voter in enumerate(voters, start=1):
            assert voter is not None
            context = ClientContext(
                request_id=f"correlation-request-{index}",
                ip_prefix=(
                    "203.0.113.0/24"
                    if index < 3
                    else f"198.51.{index - 3}.0/24"
                ),
                user_agent="synthetic-correlation-test",
            )
            mutation = apply_candidate_evidence(
                db,
                client.app.state.settings,
                candidate=candidate,
                outcome=FeedbackOutcome.SUCCESS,
                source=VerificationSource.WEB_FEEDBACK,
                principal=Principal(
                    user=voter,
                    session_family_id=f"synthetic-family-{index}",
                    mfa_verified=False,
                ),
                context=context,
            )
            db.commit()
            assert mutation.changed is True

        db.refresh(candidate)
        assert candidate.status == CandidateStatus.VERIFIED
        assessments = list(
            db.scalars(
                select(EvidenceCorrelationAssessment).where(
                    EvidenceCorrelationAssessment.candidate_id == candidate_id
                )
            )
        )
        assert len(assessments) == 5
        latest = max(assessments, key=lambda item: item.created_at)
        assert latest.correlated_group_count == 1
        assert latest.downweighted_feedback_count == 1
        assert latest.raw_success_weight == 5.0
        assert latest.effective_success_weight == 4.0

        owner = db.scalar(select(User).where(User.username == owner_registration["username"]))
        assert owner is not None

    detail = client.get(
        f"/api/v1/admin/candidates/{candidate_id}",
        headers=_admin_headers(client),
    )
    assert detail.status_code == 200
    body = detail.json()
    snapshot = body["correlation_snapshot"]
    assert snapshot == {
        "rule_version": "correlation-v1",
        "feedback_count": 5,
        "independent_group_count": 4,
        "correlated_group_count": 1,
        "downweighted_feedback_count": 1,
        "raw_success_weight": 5.0,
        "effective_success_weight": 4.0,
        "raw_failure_weight": 0.0,
        "effective_failure_weight": 0.0,
    }
    correlated_group = next(
        group for group in body["correlation_groups"] if group["member_count"] == 2
    )
    assert correlated_group["shared_signals"] == ["ip_prefix"]
    assert len(correlated_group["user_ids"]) == 2
    assert len(body["correlation_assessments"]) == 5
    serialized = str(body)
    assert "203.0.113.0/24" not in serialized
    assert "198.51.100.0/24" not in serialized
    assert "installation_id_hash" not in serialized
