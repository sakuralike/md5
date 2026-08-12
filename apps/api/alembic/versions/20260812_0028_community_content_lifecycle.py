"""add community content lifecycle and cursor hierarchy fields

Revision ID: 20260812_0028
Revises: 20260811_0027
Create Date: 2026-08-12

The migration is deliberately re-entrant. MySQL applies DDL outside a transaction,
so a failed data backfill can leave the new columns, indexes and constraints in
place while Alembic still records the previous revision. Retrying must therefore
skip objects that already exist and only complete the unfinished backfill.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.engine.reflection import Inspector

from alembic import op

revision: str = "20260812_0028"
down_revision: str | None = "20260811_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_names(inspector: Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector: Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _foreign_key_names(inspector: Inspector, table_name: str) -> set[str]:
    return {
        foreign_key["name"]
        for foreign_key in inspector.get_foreign_keys(table_name)
        if foreign_key.get("name")
    }


def _upgrade_posts(inspector: Inspector) -> None:
    existing_columns = _column_names(inspector, "community_posts")
    missing_columns = [
        column
        for column in (
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by_author_at", sa.DateTime(timezone=True), nullable=True),
        )
        if column.name not in existing_columns
    ]
    if missing_columns:
        with op.batch_alter_table("community_posts") as batch:
            for column in missing_columns:
                batch.add_column(column)


def _upgrade_post_revisions(inspector: Inspector) -> None:
    table_exists = "community_post_revisions" in inspector.get_table_names()
    if not table_exists:
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

    existing_indexes = (
        _index_names(inspector, "community_post_revisions") if table_exists else set()
    )
    indexes = (
        ("ix_community_post_revisions_post_id", ["post_id"]),
        ("ix_community_post_revisions_editor_id", ["editor_id"]),
        ("ix_community_post_revisions_created_at", ["created_at"]),
    )
    for index_name, columns in indexes:
        if index_name not in existing_indexes:
            op.create_index(index_name, "community_post_revisions", columns)


def _upgrade_comments(inspector: Inspector) -> None:
    existing_columns = _column_names(inspector, "community_comments")
    existing_foreign_keys = _foreign_key_names(inspector, "community_comments")
    existing_indexes = _index_names(inspector, "community_comments")
    missing_columns = [
        column
        for column in (
            sa.Column("root_id", sa.String(36), nullable=True),
            sa.Column("reply_to_user_id", sa.String(36), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by_author_at", sa.DateTime(timezone=True), nullable=True),
        )
        if column.name not in existing_columns
    ]
    root_fk = "fk_community_comments_root_id"
    reply_fk = "fk_community_comments_reply_to_user_id"
    root_index = "ix_community_comments_root_id"
    reply_index = "ix_community_comments_reply_to_user_id"
    needs_batch = bool(
        missing_columns
        or root_fk not in existing_foreign_keys
        or reply_fk not in existing_foreign_keys
        or root_index not in existing_indexes
        or reply_index not in existing_indexes
    )
    if not needs_batch:
        return

    with op.batch_alter_table("community_comments") as batch:
        for column in missing_columns:
            batch.add_column(column)
        if root_fk not in existing_foreign_keys:
            batch.create_foreign_key(
                root_fk,
                "community_comments",
                ["root_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if reply_fk not in existing_foreign_keys:
            batch.create_foreign_key(
                reply_fk,
                "users",
                ["reply_to_user_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if root_index not in existing_indexes:
            batch.create_index(root_index, ["root_id"])
        if reply_index not in existing_indexes:
            batch.create_index(reply_index, ["reply_to_user_id"])


def _backfill_comment_hierarchy(bind: Connection) -> None:
    if bind.dialect.name == "mysql":
        op.execute(
            sa.text(
                "UPDATE community_comments AS child "
                "INNER JOIN community_comments AS parent "
                "ON parent.id = child.parent_id "
                "SET child.root_id = child.parent_id, "
                "child.reply_to_user_id = parent.author_id "
                "WHERE child.parent_id IS NOT NULL"
            )
        )
        return

    op.execute(
        sa.text(
            "UPDATE community_comments SET root_id = parent_id, reply_to_user_id = "
            "(SELECT parent.author_id FROM community_comments AS parent "
            "WHERE parent.id = community_comments.parent_id) "
            "WHERE parent_id IS NOT NULL"
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    _upgrade_posts(inspector)
    _upgrade_post_revisions(inspector)
    _upgrade_comments(inspector)
    _backfill_comment_hierarchy(bind)


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
