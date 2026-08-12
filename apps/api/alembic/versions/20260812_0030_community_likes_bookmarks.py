"""add community likes bookmarks and count projections

Revision ID: 20260812_0030
Revises: 20260812_0029
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0030"
down_revision: str | None = "20260812_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_relation_table(
    table_name: str,
    target_column: str,
    target_table: str,
    unique_name: str,
) -> None:
    op.create_table(
        table_name,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column(target_column, sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            [target_column],
            [f"{target_table}.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", target_column, name=unique_name),
    )
    op.create_index(f"ix_{table_name}_user_id", table_name, ["user_id"])
    op.create_index(f"ix_{table_name}_{target_column}", table_name, [target_column])
    op.create_index(f"ix_{table_name}_created_at", table_name, ["created_at"])


def upgrade() -> None:
    with op.batch_alter_table("community_posts") as batch:
        batch.add_column(sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("community_comments") as batch:
        batch.add_column(sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"))

    _create_relation_table(
        "community_post_likes",
        "post_id",
        "community_posts",
        "uq_community_post_like_user_post",
    )
    _create_relation_table(
        "community_comment_likes",
        "comment_id",
        "community_comments",
        "uq_community_comment_like_user_comment",
    )
    _create_relation_table(
        "community_post_bookmarks",
        "post_id",
        "community_posts",
        "uq_community_post_bookmark_user_post",
    )


def downgrade() -> None:
    op.drop_table("community_post_bookmarks")
    op.drop_table("community_comment_likes")
    op.drop_table("community_post_likes")
    with op.batch_alter_table("community_comments") as batch:
        batch.drop_column("like_count")
    with op.batch_alter_table("community_posts") as batch:
        batch.drop_column("like_count")
