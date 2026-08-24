from __future__ import annotations

import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.operational_settings import get_operational_setting
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.user import User, UserStatus
from password_detective.db.models.user_referral import UserReferralProfile, UserReferralUse
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.referrals.schemas import ReferralProfileResponse

REFERRAL_REWARD_SETTING_KEY = "referral_reward_points"
DEFAULT_REFERRAL_REWARD_POINTS = 10
_REFERRAL_CODE_PREFIX = "pd-"
_REFERRAL_INVALID_MESSAGE = "邀请链接无效或已失效"


def _new_referral_code(db: Session) -> str:
    for _ in range(5):
        code = f"{_REFERRAL_CODE_PREFIX}{secrets.token_hex(10)}"
        if not db.scalar(select(UserReferralProfile.id).where(UserReferralProfile.code == code)):
            return code
    raise RuntimeError("unable to allocate a referral code")


def _reward_points(db: Session) -> int:
    configured = get_operational_setting(
        db,
        REFERRAL_REWARD_SETTING_KEY,
        DEFAULT_REFERRAL_REWARD_POINTS,
    )
    return max(0, min(10_000, configured))


def ensure_referral_profile(db: Session, *, user_id: str) -> UserReferralProfile:
    profile = db.scalar(
        select(UserReferralProfile).where(UserReferralProfile.user_id == user_id)
    )
    if profile is not None:
        return profile
    profile = UserReferralProfile(user_id=user_id, code=_new_referral_code(db))
    db.add(profile)
    db.flush()
    return profile


def resolve_referral_code(
    db: Session,
    *,
    referral_code: str | None,
    context: ClientContext,
) -> UserReferralProfile | None:
    if referral_code is None or not referral_code.strip():
        return None
    normalized = referral_code.strip().lower()
    profile = db.scalar(
        select(UserReferralProfile)
        .join(User, User.id == UserReferralProfile.user_id)
        .where(
            UserReferralProfile.code == normalized,
            User.status == UserStatus.ACTIVE,
        )
    )
    if profile is not None:
        return profile
    write_audit_log(
        db,
        actor_id=None,
        action="auth.referral.resolve",
        target_type="user_referral_profile",
        result="blocked",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"reason": "unknown", "code_present": True},
    )
    db.commit()
    raise AppError("auth.referral_invalid", _REFERRAL_INVALID_MESSAGE, status_code=422)


def award_referral_rewards(
    db: Session,
    *,
    profile: UserReferralProfile,
    invitee_id: str,
    context: ClientContext,
) -> UserReferralUse:
    existing = db.scalar(
        select(UserReferralUse).where(UserReferralUse.invitee_id == invitee_id)
    )
    if existing is not None:
        return existing

    points = _reward_points(db)
    now = utc_now()
    use = UserReferralUse(
        referral_profile_id=profile.id,
        invitee_id=invitee_id,
        points_awarded=points,
        created_at=now,
    )
    db.add(use)
    db.flush()
    if points > 0:
        db.add_all(
            [
                PointsLedger(
                    user_id=profile.user_id,
                    amount=points,
                    event_type="referral.inviter_reward",
                    reference_id=use.id,
                    status=PointsLedgerStatus.POSTED,
                    created_at=now,
                    settled_at=now,
                ),
                PointsLedger(
                    user_id=invitee_id,
                    amount=points,
                    event_type="referral.invitee_reward",
                    reference_id=use.id,
                    status=PointsLedgerStatus.POSTED,
                    created_at=now,
                    settled_at=now,
                ),
            ]
        )
    write_audit_log(
        db,
        actor_id=invitee_id,
        action="auth.referral.rewarded",
        target_type="user_referral_use",
        target_id=use.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "referrer_id": profile.user_id,
            "points_awarded": points,
        },
    )
    return use


def get_referral_profile(db: Session, *, user_id: str) -> ReferralProfileResponse:
    profile = ensure_referral_profile(db, user_id=user_id)
    referral_count = int(
        db.scalar(
            select(func.count(UserReferralUse.id)).where(
                UserReferralUse.referral_profile_id == profile.id
            )
        )
        or 0
    )
    total_points = int(
        db.scalar(
            select(func.coalesce(func.sum(PointsLedger.amount), 0)).where(
                PointsLedger.user_id == user_id,
                PointsLedger.event_type == "referral.inviter_reward",
                PointsLedger.status == PointsLedgerStatus.POSTED,
            )
        )
        or 0
    )
    db.commit()
    return ReferralProfileResponse(
        code=profile.code,
        referral_url=f"/register?ref={profile.code}",
        reward_points=_reward_points(db),
        referral_count=referral_count,
        total_points_earned=total_points,
        created_at=profile.created_at,
    )
