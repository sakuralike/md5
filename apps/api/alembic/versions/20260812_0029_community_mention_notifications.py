"""add community mention notifications

Revision ID: 20260812_0029
Revises: 20260812_0028
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0029"
down_revision: str | None = "20260812_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recipient_id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "MENTION",
                name="communitynotificationkind",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            sa.Enum(
                "POST",
                "COMMENT",
                name="communitynotificationsource",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("post_id", sa.String(36), nullable=False),
        sa.Column("comment_id", sa.String(36), nullable=True),
        sa.Column("preview", sa.String(180), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["post_id"], ["community_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["comment_id"], ["community_comments.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "recipient_id",
            "kind",
            "source_type",
            "source_id",
            name="uq_community_notification_delivery",
        ),
    )
    for column in (
        "recipient_id",
        "actor_id",
        "kind",
        "source_type",
        "post_id",
        "comment_id",
        "read_at",
        "created_at",
    ):
        op.create_index(
            f"ix_community_notifications_{column}",
            "community_notifications",
            [column],
        )


def downgrade() -> None:
    op.drop_table("community_notifications")
