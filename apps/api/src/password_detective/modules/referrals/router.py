from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from password_detective.db.dependencies import get_db
from password_detective.modules.auth.dependencies import Principal, get_current_principal
from password_detective.modules.referrals.schemas import ReferralProfileResponse
from password_detective.modules.referrals.service import get_referral_profile

router = APIRouter(prefix="/referrals", tags=["邀请奖励"])


@router.get("/me", response_model=ReferralProfileResponse)
def referral_profile(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> ReferralProfileResponse:
    return get_referral_profile(db, user_id=principal.user.id)
