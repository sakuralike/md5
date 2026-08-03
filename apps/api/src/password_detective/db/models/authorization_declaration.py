from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class AuthorizationSource(StrEnum):
    WEB = "web"
    DESKTOP = "desktop"
    API = "api"


class AuthorizationDeclaration(Base):
    __tablename__ = "authorization_declarations"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "declaration_version",
            "purpose",
            "source",
            name="uq_authorization_declarations_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    declaration_version: Mapped[str] = mapped_column(String(32), index=True)
    purpose: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[AuthorizationSource] = mapped_column(
        Enum(AuthorizationSource, native_enum=False, length=16), index=True
    )
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
