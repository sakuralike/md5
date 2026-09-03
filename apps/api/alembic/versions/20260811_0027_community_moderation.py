"""add community content reports and moderation workflow

Revision ID: 20260811_0027
Revises: 20260811_0026
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260811_0027"
down_revision: str | None = "20260811_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("reporter_id", sa.String(length=36), nullable=False),
        sa.Column("post_id", sa.String(length=36), nullable=False),
        sa.Column("comment_id", sa.String(length=36), nullable=True),
        sa.Column(
            "reason",
            sa.Enum(
                "SPAM",
                "HARASSMENT",
                "PRIVACY",
                "UNSAFE",
                "OTHER",
                name="communityreportreason",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN",
                "RESOLVED",
                "DISMISSED",
                name="communityreportstatus",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            "decision",
            sa.Enum(
                "DISMISS",
                "REMOVE_CONTENT",
                "REMOVE_AND_LOCK",
                name="communityreportdecision",
                native_enum=False,
                length=24,
            ),
            nullable=True,
        ),
        sa.Column("resolved_by_id", sa.String(length=36), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["comment_id"], ["community_comments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["community_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_community_reports_reporter_id", "community_reports", ["reporter_id"])
    op.create_index("ix_community_reports_post_id", "community_reports", ["post_id"])
    op.create_index("ix_community_reports_comment_id", "community_reports", ["comment_id"])
    op.create_index("ix_community_reports_reason", "community_reports", ["reason"])
    op.create_index("ix_community_reports_status", "community_reports", ["status"])
    op.create_index("ix_community_reports_resolved_by_id", "community_reports", ["resolved_by_id"])
    op.create_index("ix_community_reports_created_at", "community_reports", ["created_at"])


def downgrade() -> None:
    op.drop_table("community_reports")
