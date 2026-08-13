from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class UserStatus(StrEnum):
    ACTIVE = "active"
    LOCKED = "locked"
    DISABLED = "disabled"


class UserRole(StrEnum):
    USER = "user"
    TRUSTED_CONTRIBUTOR = "trusted_contributor"
    MODERATOR = "moderator"
    ADMIN = "admin"
    SERVICE = "service"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    account_password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, native_enum=False, length=16), default=UserStatus.ACTIVE, index=True
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=32), default=UserRole.USER, index=True
    )
    reputation_score: Mapped[int] = mapped_column(Integer, default=50)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    totp_pending_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    account_tokens = relationship(
        "AccountActionToken", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def uid(self) -> str:
        """对外展示的稳定用户标识，与主键保持一致。"""
        return self.id

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def totp_enabled(self) -> bool:
        return self.totp_enabled_at is not None
