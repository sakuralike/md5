from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.time import utc_now
from password_detective.db.base import Base


class UserLevelProfile(Base):
    """Current level projection rebuilt from append-only growth events."""

    __tablename__ = "user_level_profiles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    growth_points: Mapped[int] = mapped_column(Integer, default=0)
    level_code: Mapped[str] = mapped_column(String(32), index=True)
    level_name: Mapped[str] = mapped_column(String(64))
    level_rule_hash: Mapped[str] = mapped_column(String(64), index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
