from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class PointsLedgerStatus(StrEnum):
    PENDING = "pending"
    POSTED = "posted"
    REVERSED = "reversed"


class PointsLedger(Base):
    __tablename__ = "points_ledger"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "event_type", "reference_id", name="uq_points_ledger_event_reference"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    reference_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[PointsLedgerStatus] = mapped_column(
        Enum(PointsLedgerStatus, native_enum=False, length=16),
        default=PointsLedgerStatus.PENDING,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
