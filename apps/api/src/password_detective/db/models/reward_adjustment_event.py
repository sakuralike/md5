from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class RewardKind(StrEnum):
    CONTRIBUTION = "contribution"
    VERIFICATION = "verification"


class RewardAdjustmentDirection(StrEnum):
    INVALIDATE = "invalidate"
    RESTORE = "restore"


class RewardAdjustmentEvent(Base):
    """Append-only reward reconciliation caused by a candidate state event."""

    __tablename__ = "reward_adjustment_events"
    __table_args__ = (
        UniqueConstraint(
            "state_event_id",
            "user_id",
            "reward_kind",
            "source_reference_id",
            name="uq_reward_adjustment_state_user_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("password_candidates.id", ondelete="CASCADE"), index=True
    )
    state_event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("record_state_events.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    reward_kind: Mapped[RewardKind] = mapped_column(
        Enum(RewardKind, native_enum=False, length=24), index=True
    )
    source_reference_id: Mapped[str] = mapped_column(String(36), index=True)
    direction: Mapped[RewardAdjustmentDirection] = mapped_column(
        Enum(RewardAdjustmentDirection, native_enum=False, length=16), index=True
    )
    points_amount: Mapped[int] = mapped_column(Integer)
    reputation_amount: Mapped[int] = mapped_column(Integer)
    reason_code: Mapped[str] = mapped_column(String(96), index=True)
    rule_version: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
