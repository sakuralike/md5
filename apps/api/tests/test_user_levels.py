from __future__ import annotations

from sqlalchemy import select

from password_detective.db.models.system_setting import SystemSetting
from password_detective.db.models.user import User
from password_detective.db.models.user_level_profile import UserLevelProfile
from password_detective.modules.reputation.levels import (
    daily_reveal_quota_for_user,
    get_user_level_profile,
    rebuild_all_level_profiles,
    record_growth_event,
)


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], dict[str, str]]:
    registration = {
        "username": f"level_{suffix}",
        "email": f"level-{suffix}@synthetic.example.com",
        "password": "SyntheticLevelPass123!",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    return registration, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _custom_levels(*, can_submit: bool = True) -> list[dict[str, object]]:
    return [
        {
            "code": "rookie",
            "name": "新手侦探",
            "description": "合成测试基础等级。",
            "min_growth_points": 0,
            "daily_reveal_quota": 12,
            "can_submit": can_submit,
        },
        {
            "code": "advanced",
            "name": "进阶侦探",
            "description": "合成测试进阶等级。",
            "min_growth_points": 50,
            "daily_reveal_quota": 40,
            "can_submit": True,
        },
    ]


def test_growth_projection_rebuilds_from_append_only_events_and_current_rules(client):
    registration, _ = _register_and_login(client, "projection")
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        event = record_growth_event(
            db,
            user_id=user.id,
            amount=95,
            event_type="synthetic.growth",
            reference_id="synthetic-growth-projection",
            reason_code="synthetic.test",
        )
        replay = record_growth_event(
            db,
            user_id=user.id,
            amount=95,
            event_type="synthetic.growth",
            reference_id="synthetic-growth-projection",
            reason_code="synthetic.test",
        )
        assert replay.id == event.id
        assert get_user_level_profile(db, user_id=user.id).growth_points == 100

        db.add(
            SystemSetting(
                key="user_levels",
                value_json={"value": _custom_levels()},
                version=1,
                updated_by=user.id,
            )
        )
        db.flush()
        assert rebuild_all_level_profiles(db) == 1
        projection = db.get(UserLevelProfile, user.id)
        assert projection is not None
        assert projection.growth_points == 100
        assert projection.level_code == "advanced"
        db.commit()


def test_level_entitlements_gate_submission_and_raise_reveal_quota(client):
    registration, headers = _register_and_login(client, "entitlements")
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        db.add(
            SystemSetting(
                key="user_levels",
                value_json={"value": _custom_levels(can_submit=False)},
                version=1,
                updated_by=user.id,
            )
        )
        db.commit()

        assert daily_reveal_quota_for_user(db, user_id=user.id, baseline=5) == 12
        assert daily_reveal_quota_for_user(db, user_id=user.id, baseline=20) == 20

    denied = client.post(
        "/api/v1/archives/submissions",
        headers={**headers, "Idempotency-Key": "level-submit-denied-0001"},
        json={
            "fingerprints": [{"algorithm": "sha256", "digest": "d" * 64}],
            "password": "Synthetic-Level-Gated-Candidate!",
            "authorization_confirmed": True,
            "authorization_version": "2026-08-01",
        },
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "level.submission_not_allowed"
    assert denied.json()["details"] == {"level_code": "rookie"}
