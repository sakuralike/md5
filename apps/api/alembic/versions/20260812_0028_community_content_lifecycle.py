"""add community content lifecycle and cursor hierarchy fields

Revision ID: 20260812_0028
Revises: 20260811_0027
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0028"
down_revision: str | None = "20260811_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("community_posts") as batch:
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("deleted_by_author_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.create_table(
        "community_post_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("post_id", sa.String(36), nullable=False),
        sa.Column("editor_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title_snapshot", sa.String(120), nullable=False),
        sa.Column("content_snapshot", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False, server_default="author_edit"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["community_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["editor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("post_id", "version", name="uq_community_post_revision_version"),
    )
    op.create_index(
        "ix_community_post_revisions_post_id", "community_post_revisions", ["post_id"]
    )
    op.create_index(
        "ix_community_post_revisions_editor_id", "community_post_revisions", ["editor_id"]
    )
    op.create_index(
        "ix_community_post_revisions_created_at", "community_post_revisions", ["created_at"]
    )

    with op.batch_alter_table("community_comments") as batch:
        batch.add_column(sa.Column("root_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("reply_to_user_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("deleted_by_author_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_foreign_key(
            "fk_community_comments_root_id", "community_comments", ["root_id"], ["id"],
            ondelete="SET NULL"
        )
        batch.create_foreign_key(
            "fk_community_comments_reply_to_user_id", "users", ["reply_to_user_id"], ["id"],
            ondelete="SET NULL"
        )
        batch.create_index("ix_community_comments_root_id", ["root_id"])
        batch.create_index("ix_community_comments_reply_to_user_id", ["reply_to_user_id"])

    op.execute(
        sa.text(
            "UPDATE community_comments SET root_id = parent_id, reply_to_user_id = "
            "(SELECT parent.author_id FROM community_comments AS parent "
            "WHERE parent.id = community_comments.parent_id) WHERE parent_id IS NOT NULL"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("community_comments") as batch:
        batch.drop_index("ix_community_comments_reply_to_user_id")
        batch.drop_index("ix_community_comments_root_id")
        batch.drop_constraint("fk_community_comments_reply_to_user_id", type_="foreignkey")
        batch.drop_constraint("fk_community_comments_root_id", type_="foreignkey")
        batch.drop_column("deleted_by_author_at")
        batch.drop_column("edited_at")
        batch.drop_column("version")
        batch.drop_column("reply_to_user_id")
        batch.drop_column("root_id")

    op.drop_index(
        "ix_community_post_revisions_created_at", table_name="community_post_revisions"
    )
    op.drop_index(
        "ix_community_post_revisions_editor_id", table_name="community_post_revisions"
    )
    op.drop_index(
        "ix_community_post_revisions_post_id", table_name="community_post_revisions"
    )
    op.drop_table("community_post_revisions")

    with op.batch_alter_table("community_posts") as batch:
        batch.drop_column("deleted_by_author_at")
        batch.drop_column("edited_at")
        batch.drop_column("version")
