from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class ThirdPartyAuthorization(Base):
    __tablename__ = "third_party_authorizations"
    __table_args__ = (
        UniqueConstraint("app_id", "user_id", name="uq_third_party_authorization_app_user"),
        Index("ix_third_party_authorizations_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    app_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("third_party_apps.id", ondelete="CASCADE")
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    scope_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthAuthorizationCode(Base):
    __tablename__ = "third_party_authorization_codes"
    __table_args__ = (Index("ix_third_party_authorization_codes_app_id", "app_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    app_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("third_party_apps.id", ondelete="CASCADE")
    )
    authorization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("third_party_authorizations.id", ondelete="CASCADE")
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    redirect_uri: Mapped[str] = mapped_column(String(2_000))
    code_challenge: Mapped[str] = mapped_column(String(128))
    code_challenge_method: Mapped[str] = mapped_column(String(8), default="S256")
    scope_json: Mapped[str] = mapped_column(Text, default="[]")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OAuthTokenSession(Base):
    __tablename__ = "third_party_token_sessions"
    __table_args__ = (
        Index("ix_third_party_token_sessions_app_id", "app_id"),
        Index("ix_third_party_token_sessions_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    app_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("third_party_apps.id", ondelete="CASCADE")
    )
    authorization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("third_party_authorizations.id", ondelete="CASCADE")
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    token_family_id: Mapped[str] = mapped_column(String(36), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    scope_json: Mapped[str] = mapped_column(Text, default="[]")
    refresh_issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    refresh_rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
