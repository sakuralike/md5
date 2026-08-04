from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class ReauthenticationPurpose(StrEnum):
    PASSWORD_CHANGE = "password_change"
    TOTP_DISABLE = "totp_disable"
    ACCOUNT_DELETION = "account_deletion"
    ADMIN_USER_GOVERNANCE = "admin_user_governance"
    ADMIN_SETTINGS_GOVERNANCE = "admin_settings_governance"


class ReauthenticationGrant(Base):
    __tablename__ = "reauthentication_grants"
    __table_args__ = (
        Index(
            "ix_reauth_grants_user_session_purpose_active",
            "user_id",
            "session_family_id",
            "purpose",
            "consumed_at",
            "expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    session_family_id: Mapped[str] = mapped_column(String(36), index=True)
    purpose: Mapped[ReauthenticationPurpose] = mapped_column(
        Enum(ReauthenticationPurpose, native_enum=False, length=32), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
