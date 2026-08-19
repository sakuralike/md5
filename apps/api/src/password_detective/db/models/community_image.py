from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.base import Base


class CommunityImageStatus(StrEnum):
    UPLOADED = "uploaded"
    ATTACHED = "attached"
    REMOVED = "removed"


class CommunityPostImage(Base):
    __tablename__ = "community_post_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    post_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("community_posts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    asset_name: Mapped[str] = mapped_column(String(69))
    content_type: Mapped[str] = mapped_column(String(32))
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    status: Mapped[CommunityImageStatus] = mapped_column(
        Enum(CommunityImageStatus, native_enum=False, length=16),
        default=CommunityImageStatus.UPLOADED,
        index=True,
    )
    attached_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
