from __future__ import annotations

import pyotp
from sqlalchemy import func, select

from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.points_ledger import PointsLedger
from password_detective.db.models.reputation_event import ReputationEvent
from password_detective.db.models.reward_adjustment_event import RewardAdjustmentEvent
from password_detective.db.models.user import User, UserRole
from password_detective.db.models.user_growth_event import UserGrowthEvent


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], dict[str, str]]:
    registration = {
        "username": f"reward_{suffix}",
        "email": f"reward-{suffix}@synthetic.example.com",
        "password": "SyntheticRewardPass123!",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    return registration, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _admin_headers(client, suffix: str) -> dict[str, str]:
    registration, initial_headers = _register_and_login(client, suffix)
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


def _submit(client, headers: dict[str, str], suffix: str) -> dict:
    digit = str((int(suffix[-1]) % 8) + 1)
    response = client.post(
        "/api/v1/archives/submissions",
        headers={**headers, "Idempotency-Key": f"reward-submission-{suffix}"},
        json={
            "fingerprints": [
                {"algorithm": "sha256", "digest": digit * 64},
                {"algorithm": "md5", "digest": digit * 32},
            ],
            "password": f"Synthetic-Reward-Candidate-{suffix}!",
            "authorization_confirmed": True,
            "authorization_version": "2026-08-01",
        },
    )
    assert response.status_code == 201
    return response.json()


def _feedback(
    client,
    headers: dict[str, str],
    candidate_id: str,
    suffix: str,
    outcome: str = "success",
):
    response = client.post(
        f"/api/v1/candidates/{candidate_id}/feedback",
        headers={**headers, "Idempotency-Key": f"reward-feedback-{suffix}"},
        json={"outcome": outcome},
    )
    assert response.status_code == 200
    return response


def _transition(
    client,
    headers: dict[str, str],
    candidate_id: str,
    *,
    suffix: str,
    target_status: str,
    reason_code: str,
):
    return client.post(
        f"/api/v1/admin/candidates/{candidate_id}/transition",
        headers={**headers, "Idempotency-Key": f"reward-transition-{suffix}"},
        json={
            "target_status": target_status,
            "reason_code": reason_code,
            "reason_note": "合成奖励校正审核说明。",
        },
    )


def test_manual_quarantine_restores_and_reinvalidates_rewards_append_only(client):
    _, owner = _register_and_login(client, "manual_owner")
    verifiers = [
        _register_and_login(client, f"manual_verifier_{index}")[1]
        for index in range(1, 5)
    ]
    admin = _admin_headers(client, "manual_admin")
    created = _submit(client, owner, "1001")
    candidate_id = created["candidate_id"]
    verified = None
    for index, headers in enumerate(verifiers, start=1):
        verified = _feedback(client, headers, candidate_id, f"manual-{index}")
    assert verified is not None
    assert verified.json()["candidate_status"] == "verified"

    quarantine = _transition(
        client,
        admin,
        candidate_id,
        suffix="manual-quarantine",
        target_status="quarantined",
        reason_code="manual.security_hold",
    )
    assert quarantine.status_code == 200
    adjustment = quarantine.json()["reward_adjustment"]
    assert adjustment == {
        "rule_version": "reward-compensation-v1",
        "direction": "invalidate",
        "affected_users": 5,
        "points_entries": 5,
        "reputation_events": 5,
        "points_amount": -5,
        "reputation_amount": -11,
    }
    for headers in (owner, *verifiers):
        profile = client.get("/api/v1/me/trust-profile", headers=headers).json()
        assert profile["points"]["available"] == 0
        assert profile["reputation_score"] == 50

    replay = _transition(
        client,
        admin,
        candidate_id,
        suffix="manual-quarantine",
        target_status="quarantined",
        reason_code="manual.security_hold",
    )
    assert replay.status_code == 200
    assert replay.json() == quarantine.json()

    detail = client.get(f"/api/v1/admin/candidates/{candidate_id}", headers=admin)
    assert detail.status_code == 200
    assert len(detail.json()["reward_adjustments"]) == 5
    assert {item["direction"] for item in detail.json()["reward_adjustments"]} == {
        "invalidate"
    }
    serialized = str(detail.json()).lower()
    for forbidden_field in ("password", "ciphertext", "nonce", "secret"):
        assert forbidden_field not in serialized

    restore = _transition(
        client,
        admin,
        candidate_id,
        suffix="manual-restore",
        target_status="verified",
        reason_code="manual.quarantine_cleared",
    )
    assert restore.status_code == 200
    assert restore.json()["reward_adjustment"] == {
        "rule_version": "reward-compensation-v1",
        "direction": "restore",
        "affected_users": 5,
        "points_entries": 5,
        "reputation_events": 5,
        "points_amount": 5,
        "reputation_amount": 11,
    }

    reject = _transition(
        client,
        admin,
        candidate_id,
        suffix="manual-reject",
        target_status="rejected",
        reason_code="manual.policy_violation",
    )
    assert reject.status_code == 200
    assert reject.json()["reward_adjustment"]["points_amount"] == -5
    assert reject.json()["reward_adjustment"]["reputation_amount"] == -11

    with client.app.state.database.session_factory() as db:
        assert db.scalar(select(func.count(RewardAdjustmentEvent.id))) == 15
        assert db.scalar(select(func.count(PointsLedger.id))) == 20
        assert db.scalar(select(func.count(ReputationEvent.id))) == 20
        original_point_events = list(
            db.scalars(
                select(PointsLedger).where(
                    PointsLedger.event_type.in_(
                        ["submission.pending", "verification.accepted"]
                    )
                )
            )
        )
        assert len(original_point_events) == 5
        assert sum(item.amount for item in original_point_events) == 5
        growth_adjustments = list(
            db.scalars(
                select(UserGrowthEvent).where(
                    UserGrowthEvent.event_type.like("growth.reward.%")
                )
            )
        )
        assert len(growth_adjustments) == 15
        assert sum(item.amount for item in growth_adjustments) == -200


def test_manual_first_verification_settles_original_rewards(client):
    _, owner = _register_and_login(client, "first_owner")
    admin = _admin_headers(client, "first_admin")
    created = _submit(client, owner, "1002")

    response = _transition(
        client,
        admin,
        created["candidate_id"],
        suffix="first-verified",
        target_status="verified",
        reason_code="manual.verified_by_review",
    )
    assert response.status_code == 200
    assert response.json()["reward_adjustment"] == {
        "rule_version": "reward-compensation-v1",
        "direction": None,
        "affected_users": 0,
        "points_entries": 0,
        "reputation_events": 0,
        "points_amount": 0,
        "reputation_amount": 0,
    }
    profile = client.get("/api/v1/me/trust-profile", headers=owner).json()
    assert profile["points"] == {"available": 1, "pending": 0, "reversed": 0}
    assert profile["reputation_score"] == 53


def test_automatic_quarantine_and_reverification_reconcile_rewards(client):
    _, owner = _register_and_login(client, "auto_owner")
    verifiers = [
        _register_and_login(client, f"auto_verifier_{index}")[1]
        for index in range(1, 5)
    ]
    created = _submit(client, owner, "1003")
    candidate_id = created["candidate_id"]
    for index, headers in enumerate(verifiers, start=1):
        verified = _feedback(client, headers, candidate_id, f"auto-{index}-success")
    assert verified.json()["candidate_status"] == "verified"

    for index, headers in enumerate(verifiers[:3], start=1):
        quarantined = _feedback(
            client, headers, candidate_id, f"auto-{index}-failure", "failure"
        )
    assert quarantined.json()["candidate_status"] == "quarantined"

    for index, headers in enumerate(verifiers[:3], start=1):
        restored = _feedback(
            client, headers, candidate_id, f"auto-{index}-restored", "success"
        )
    assert restored.json()["candidate_status"] == "verified"

    with client.app.state.database.session_factory() as db:
        candidate = db.get(PasswordCandidate, candidate_id)
        assert candidate is not None
        assert candidate.status == CandidateStatus.VERIFIED
        adjustments = list(
            db.scalars(
                select(RewardAdjustmentEvent)
                .where(RewardAdjustmentEvent.candidate_id == candidate_id)
                .order_by(RewardAdjustmentEvent.created_at, RewardAdjustmentEvent.id)
            )
        )
        assert len(adjustments) == 10
        assert sum(item.points_amount for item in adjustments) == 0
        assert sum(item.reputation_amount for item in adjustments) == 0
        assert {item.direction.value for item in adjustments} == {"invalidate", "restore"}
        growth_adjustments = list(
            db.scalars(
                select(UserGrowthEvent).where(
                    UserGrowthEvent.event_type.like("growth.reward.%")
                )
            )
        )
        assert len(growth_adjustments) == 10
        assert sum(item.amount for item in growth_adjustments) == 0
