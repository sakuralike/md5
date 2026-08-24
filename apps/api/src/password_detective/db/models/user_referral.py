from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class UserReferralProfile(Base):
    __tablename__ = "user_referral_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_referral_profiles_user_id"),
        UniqueConstraint("code", name="uq_user_referral_profiles_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserReferralUse(Base):
    __tablename__ = "user_referral_uses"
    __table_args__ = (
        UniqueConstraint("invitee_id", name="uq_user_referral_uses_invitee_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    referral_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("user_referral_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    invitee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    points_awarded: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
