from __future__ import annotations

import hashlib

from sqlalchemy import func, select

from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.registration_invite import (
    RegistrationInvite,
    RegistrationInviteUse,
)
from password_detective.db.models.system_setting import SystemSetting
from password_detective.db.models.user import User
from password_detective.db.models.user_referral import UserReferralProfile, UserReferralUse

PASSWORD = "SyntheticReferralPass123!"


def _register(
    client,
    suffix: str,
    *,
    referral_code: str | None = None,
    invite_code: str | None = None,
):
    payload = {
        "username": f"referral_{suffix}",
        "email": f"referral-{suffix}@synthetic.example.com",
        "password": PASSWORD,
    }
    if referral_code is not None:
        payload["referral_code"] = referral_code
    if invite_code is not None:
        payload["invite_code"] = invite_code
    return client.post("/api/v1/auth/register", json=payload)


def _login_headers(client, suffix: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"login": f"referral_{suffix}", "password": PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_referral_profile_and_registration_rewards_are_once_per_new_user(client):
    inviter = _register(client, "inviter")
    assert inviter.status_code == 201
    inviter_headers = _login_headers(client, "inviter")

    profile = client.get("/api/v1/referrals/me", headers=inviter_headers)
    assert profile.status_code == 200
    profile_body = profile.json()
    assert profile_body["code"].startswith("pd-")
    assert profile_body["referral_url"] == f"/register?ref={profile_body['code']}"
    assert profile_body["reward_points"] == 10
    assert profile_body["referral_count"] == 0

    with client.app.state.database.session_factory() as db:
        setting = db.get(SystemSetting, "referral_reward_points")
        if setting is None:
            db.add(SystemSetting(key="referral_reward_points", value_json={"value": 23}))
        else:
            setting.value_json = {"value": 23}
        db.commit()

    accepted = _register(client, "invitee", referral_code=profile_body["code"])
    assert accepted.status_code == 201
    repeated = _register(client, "invitee_again", referral_code=profile_body["code"])
    assert repeated.status_code == 201

    with client.app.state.database.session_factory() as db:
        inviter_id = db.scalar(select(User.id).where(User.username == "referral_inviter"))
        invitee_id = db.scalar(select(User.id).where(User.username == "referral_invitee"))
        assert inviter_id is not None and invitee_id is not None
        profile_row = db.scalar(
            select(UserReferralProfile).where(UserReferralProfile.user_id == inviter_id)
        )
        assert profile_row is not None
        assert db.scalar(
            select(func.count(UserReferralUse.id)).where(
                UserReferralUse.referral_profile_id == profile_row.id
            )
        ) == 2
        ledger_rows = db.scalars(
            select(PointsLedger).where(
                PointsLedger.event_type.in_(
                    {"referral.inviter_reward", "referral.invitee_reward"}
                )
            )
        ).all()
        assert len(ledger_rows) == 4
        assert {row.amount for row in ledger_rows} == {23}
        assert {row.status for row in ledger_rows} == {PointsLedgerStatus.POSTED}

    refreshed = client.get("/api/v1/referrals/me", headers=inviter_headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["reward_points"] == 23
    assert refreshed.json()["referral_count"] == 2
    assert refreshed.json()["total_points_earned"] == 46


def test_invalid_referral_code_does_not_register_account(client):
    response = _register(client, "invalid", referral_code="pd-00000000000000000000")
    assert response.status_code == 422
    assert response.json()["code"] == "auth.referral_invalid"


def test_registration_invite_mode_has_priority_over_referral_link(client):
    inviter = _register(client, "priority_inviter")
    assert inviter.status_code == 201
    inviter_headers = _login_headers(client, "priority_inviter")
    profile = client.get("/api/v1/referrals/me", headers=inviter_headers)
    assert profile.status_code == 200
    referral_code = profile.json()["code"]
    invite_code = "PD-SYNTHETIC-PRIORITY"

    with client.app.state.database.session_factory() as db:
        db.add(
            SystemSetting(
                key="registration_policy",
                value_json={"value": {"mode": "invite_only"}},
            )
        )
        db.add(
            RegistrationInvite(
                code_hash=hashlib.sha256(invite_code.encode("utf-8")).hexdigest(),
                label="synthetic priority invite",
                max_uses=2,
                created_by=inviter.json()["id"],
            )
        )
        db.commit()

    accepted = _register(
        client,
        "priority_accepted",
        invite_code=invite_code,
        referral_code=referral_code,
    )
    assert accepted.status_code == 201

    referral_only = _register(
        client,
        "priority_referral_only",
        referral_code=referral_code,
    )
    assert referral_only.status_code == 403
    assert referral_only.json()["code"] == "auth.registration_invite_invalid"
    disabled_profile = client.get("/api/v1/referrals/me", headers=inviter_headers)
    assert disabled_profile.status_code == 409
    assert disabled_profile.json()["code"] == "auth.referral_disabled"

    with client.app.state.database.session_factory() as db:
        assert db.scalar(select(func.count(UserReferralUse.id))) == 0
        assert db.scalar(
            select(func.count(PointsLedger.id)).where(
                PointsLedger.event_type.like("referral.%")
            )
        ) == 0
        assert db.scalar(select(func.count(RegistrationInviteUse.id))) == 1
