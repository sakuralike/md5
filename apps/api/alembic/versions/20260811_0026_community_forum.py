"""add community posts and comments

Revision ID: 20260811_0026
Revises: 20260811_0025
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260811_0026"
down_revision: str | None = "20260811_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_posts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "board_code",
            sa.Enum(
                "GENERAL",
                "RECOVERY_GUIDES",
                "VERIFICATION",
                "SECURITY",
                name="communityboardcode",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("author_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PUBLISHED",
                "REMOVED",
                name="communitycontentstatus",
                native_enum=False,
                length=16,
            ),
            nullable=False,
            server_default="PUBLISHED",
        ),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reply_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
    )
    for column in (
        "board_code",
        "author_id",
        "status",
        "is_pinned",
        "is_locked",
        "last_activity_at",
        "created_at",
    ):
        op.create_index(f"ix_community_posts_{column}", "community_posts", [column])

    op.create_table(
        "community_comments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("post_id", sa.String(36), nullable=False),
        sa.Column("author_id", sa.String(36), nullable=False),
        sa.Column("parent_id", sa.String(36), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PUBLISHED",
                "REMOVED",
                name="communitycontentstatus",
                native_enum=False,
                length=16,
            ),
            nullable=False,
            server_default="PUBLISHED",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["community_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_id"], ["community_comments.id"], ondelete="SET NULL"),
    )
    for column in ("post_id", "author_id", "status", "created_at"):
        op.create_index(f"ix_community_comments_{column}", "community_comments", [column])


def downgrade() -> None:
    op.drop_table("community_comments")
    op.drop_table("community_posts")
