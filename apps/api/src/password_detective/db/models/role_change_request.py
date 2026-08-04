from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base
from password_detective.db.models.user import UserRole


class RoleChangeRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RoleChangeRequest(Base):
    __tablename__ = "role_change_requests"
    __table_args__ = (
        Index("ix_role_change_requests_status_created", "status", "created_at"),
        Index("ix_role_change_requests_target_status", "target_user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expected_role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=32)
    )
    requested_role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=32)
    )
    status: Mapped[RoleChangeRequestStatus] = mapped_column(
        Enum(RoleChangeRequestStatus, native_enum=False, length=16),
        default=RoleChangeRequestStatus.PENDING,
        index=True,
    )
    requested_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    reason_code: Mapped[str] = mapped_column(String(32))
    review_reason_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
