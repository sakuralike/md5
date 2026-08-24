from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ReferralProfileResponse(BaseModel):
    code: str
    referral_url: str
    reward_points: int = Field(ge=0)
    referral_count: int = Field(ge=0)
    total_points_earned: int = Field(ge=0)
    created_at: datetime
