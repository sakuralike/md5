from __future__ import annotations

from sqlalchemy import select

from password_detective.db.models.reputation_event import ReputationEvent
from password_detective.db.models.user import User
from password_detective.db.models.user_growth_event import UserGrowthEvent
from password_detective.modules.reputation.service import apply_reputation_event

SHA256 = "a" * 64
MD5 = "b" * 32


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], dict[str, str]]:
    registration = {
        "username": f"reputation_{suffix}",
        "email": f"reputation-{suffix}@synthetic.example.com",
        "password": "SyntheticReputationPass123!",
    }
    response = client.post("/api/v1/auth/register", json=registration)
    assert response.status_code == 201
    assert response.json()["reputation_score"] == 50
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    return registration, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create_candidate(client, headers: dict[str, str], suffix: str) -> dict:
    response = client.post(
        "/api/v1/archives/submissions",
        headers={**headers, "Idempotency-Key": f"reputation-submission-{suffix}"},
        json={
            "fingerprints": [
                {"algorithm": "sha256", "digest": SHA256},
                {"algorithm": "md5", "digest": MD5},
            ],
            "password": "Synthetic-Reputation-Candidate!",
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
):
    response = client.post(
        f"/api/v1/candidates/{candidate_id}/feedback",
        headers={**headers, "Idempotency-Key": f"reputation-feedback-{suffix}"},
        json={"outcome": "success"},
    )
    assert response.status_code == 200
    return response


def test_new_user_has_baseline_reputation_and_empty_private_projection(client):
    _, headers = _register_and_login(client, "baseline")

    profile = client.get("/api/v1/me/trust-profile", headers=headers)
    assert profile.status_code == 200
    body = profile.json()
    level = body.pop("level")
    assert body == {
        "reputation_score": 50,
        "reputation_min": 0,
        "reputation_max": 100,
        "points": {"available": 0, "pending": 0, "reversed": 0},
        "feedback": {
            "effective_success": 0,
            "effective_failure": 0,
            "history_events": 0,
        },
        "contributions": {"total": 0, "verified": 0},
    }
    assert level["growth_points"] == 5
    assert level["current"]["code"] == "rookie"
    assert level["current"]["entitlements"] == {
        "daily_reveal_quota": 20,
        "can_submit": True,
    }
    assert level["next"]["code"] == "apprentice"
    assert level["progress_percent"] == 5
    assert level["points_to_next_level"] == 95
    assert client.get("/api/v1/me/points", headers=headers).json()["total"] == 0
    assert client.get("/api/v1/me/reputation", headers=headers).json()["total"] == 0

    assert client.get("/api/v1/me/trust-profile").status_code == 401


def test_daily_login_growth_is_idempotent_and_level_endpoints_are_private(client):
    registration, headers = _register_and_login(client, "daily_growth")
    second_login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert second_login.status_code == 200

    level = client.get("/api/v1/me/level", headers=headers)
    assert level.status_code == 200
    assert level.json()["growth_points"] == 5
    assert level.json()["current"]["name"] == "新手侦探"

    events = client.get("/api/v1/me/growth-events", headers=headers)
    assert events.status_code == 200
    assert events.json()["total"] == 1
    assert events.json()["items"][0]["event_type"] == "activity.login_day"
    assert events.json()["items"][0]["amount"] == 5

    catalog = client.get("/api/v1/me/level-catalog", headers=headers)
    assert catalog.status_code == 200
    assert [item["code"] for item in catalog.json()["items"]] == [
        "rookie",
        "apprentice",
        "senior",
        "expert",
        "chief",
    ]
    assert client.get("/api/v1/me/level").status_code == 401


def test_first_verification_settles_points_and_reputation_once(client):
    _, owner = _register_and_login(client, "owner")
    verifiers = [
        _register_and_login(client, f"verifier_{index}")[1] for index in range(1, 5)
    ]
    verifier_one = verifiers[0]
    created = _create_candidate(client, owner, "0001")

    responses = [
        _feedback(client, headers, created["candidate_id"], f"000{index}")
        for index, headers in enumerate(verifiers, start=1)
    ]
    assert all(response.status_code == 200 for response in responses)
    assert [response.json()["candidate_status"] for response in responses] == [
        "pending",
        "pending",
        "pending",
        "verified",
    ]

    owner_profile = client.get("/api/v1/me/trust-profile", headers=owner).json()
    assert owner_profile["reputation_score"] == 53
    assert owner_profile["points"] == {"available": 1, "pending": 0, "reversed": 0}
    assert owner_profile["contributions"] == {"total": 1, "verified": 1}
    assert owner_profile["level"]["growth_points"] == 105
    assert owner_profile["level"]["current"]["code"] == "apprentice"

    verifier_profile = client.get("/api/v1/me/trust-profile", headers=verifier_one).json()
    assert verifier_profile["reputation_score"] == 52
    assert verifier_profile["points"] == {"available": 1, "pending": 0, "reversed": 0}
    assert verifier_profile["feedback"] == {
        "effective_success": 1,
        "effective_failure": 0,
        "history_events": 1,
    }
    assert verifier_profile["level"]["growth_points"] == 30
    assert verifier_profile["level"]["current"]["code"] == "rookie"

    owner_events = client.get("/api/v1/me/reputation", headers=owner).json()
    assert owner_events["total"] == 1
    assert owner_events["items"][0]["event_type"] == "contribution.verified"
    assert owner_events["items"][0]["previous_score"] == 50
    assert owner_events["items"][0]["next_score"] == 53

    verifier_events = client.get("/api/v1/me/reputation", headers=verifier_one).json()
    assert verifier_events["total"] == 1
    assert verifier_events["items"][0]["event_type"] == "verification.accepted"
    assert verifier_events["items"][0]["amount"] == 2

    replay = client.post(
        f"/api/v1/candidates/{created['candidate_id']}/feedback",
        headers={**verifiers[-1], "Idempotency-Key": "reputation-feedback-0004"},
        json={"outcome": "success"},
    )
    assert replay.status_code == 200
    with client.app.state.database.session_factory() as db:
        assert len(list(db.scalars(select(ReputationEvent)))) == 5
        assert len(list(db.scalars(select(UserGrowthEvent)))) == 10


def test_reputation_projection_is_bounded_and_reference_idempotent(client):
    registration, _ = _register_and_login(client, "bounds")
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        first = apply_reputation_event(
            db,
            user_id=user.id,
            amount=80,
            event_type="synthetic.boundary",
            reference_id="synthetic-reference-1",
            reason_code="synthetic.test",
        )
        assert first is not None
        assert first.amount == 50
        assert first.previous_score == 50
        assert first.next_score == 100
        db.commit()

        replay = apply_reputation_event(
            db,
            user_id=user.id,
            amount=80,
            event_type="synthetic.boundary",
            reference_id="synthetic-reference-1",
            reason_code="synthetic.test",
        )
        assert replay is not None
        assert replay.id == first.id
        assert db.get(User, user.id).reputation_score == 100
        assert len(list(db.scalars(select(ReputationEvent)))) == 1

        saturated = apply_reputation_event(
            db,
            user_id=user.id,
            amount=5,
            event_type="synthetic.boundary",
            reference_id="synthetic-reference-2",
            reason_code="synthetic.test",
        )
        assert saturated is not None
        assert saturated.amount == 0
        assert saturated.previous_score == 100
        assert saturated.next_score == 100
        db.commit()

        decrease = apply_reputation_event(
            db,
            user_id=user.id,
            amount=-10,
            event_type="synthetic.adjustment",
            reference_id="synthetic-reference-3",
            reason_code="synthetic.test",
        )
        assert decrease is not None
        assert decrease.next_score == 90
        db.commit()

        saturated_replay = apply_reputation_event(
            db,
            user_id=user.id,
            amount=5,
            event_type="synthetic.boundary",
            reference_id="synthetic-reference-2",
            reason_code="synthetic.test",
        )
        assert saturated_replay is not None
        assert saturated_replay.id == saturated.id
        assert db.get(User, user.id).reputation_score == 90
        assert len(list(db.scalars(select(ReputationEvent)))) == 3
