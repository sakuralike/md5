from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0038"
down_revision: str | None = "20260814_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "desktop_announcements",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(16), nullable=False),
        sa.Column("image_urls_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("action_label", sa.String(64), nullable=True),
        sa.Column("action_url", sa.String(2000), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_desktop_announcements_status", "desktop_announcements", ["status"])
    op.create_index("ix_desktop_announcements_sort_order", "desktop_announcements", ["sort_order"])
    op.create_index("ix_desktop_announcements_created_by", "desktop_announcements", ["created_by"])
    op.create_index(
        "ix_desktop_announcements_published_at", "desktop_announcements", ["published_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_desktop_announcements_published_at", table_name="desktop_announcements")
    op.drop_index("ix_desktop_announcements_created_by", table_name="desktop_announcements")
    op.drop_index("ix_desktop_announcements_sort_order", table_name="desktop_announcements")
    op.drop_index("ix_desktop_announcements_status", table_name="desktop_announcements")
    op.drop_table("desktop_announcements")
