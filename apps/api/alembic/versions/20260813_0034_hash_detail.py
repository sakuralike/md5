from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260813_0034"
down_revision: str | None = "20260812_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hash_likes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("fingerprint_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["fingerprint_id"], ["archive_fingerprints.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", "fingerprint_id", name="uq_hash_like_user_fingerprint"),
    )
    op.create_index("ix_hash_likes_user_id", "hash_likes", ["user_id"])
    op.create_index("ix_hash_likes_fingerprint_id", "hash_likes", ["fingerprint_id"])

    op.create_table(
        "hash_votes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("fingerprint_id", sa.String(36), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["fingerprint_id"], ["archive_fingerprints.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", "fingerprint_id", name="uq_hash_vote_user_fingerprint"),
    )
    op.create_index("ix_hash_votes_user_id", "hash_votes", ["user_id"])
    op.create_index("ix_hash_votes_fingerprint_id", "hash_votes", ["fingerprint_id"])
    op.create_index("ix_hash_votes_outcome", "hash_votes", ["outcome"])

    op.create_table(
        "hash_comments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fingerprint_id", sa.String(36), nullable=False),
        sa.Column("author_id", sa.String(36), nullable=False),
        sa.Column("parent_id", sa.String(36), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("like_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["fingerprint_id"], ["archive_fingerprints.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_id"], ["hash_comments.id"], ondelete="SET NULL"),
    )
    for column in ("fingerprint_id", "author_id", "parent_id"):
        op.create_index(f"ix_hash_comments_{column}", "hash_comments", [column])
    op.create_index("ix_hash_comments_created_at", "hash_comments", ["created_at"])

    op.create_table(
        "hash_comment_likes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("comment_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["comment_id"], ["hash_comments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "comment_id", name="uq_hash_comment_like_user_comment"),
    )
    op.create_index("ix_hash_comment_likes_user_id", "hash_comment_likes", ["user_id"])
    op.create_index("ix_hash_comment_likes_comment_id", "hash_comment_likes", ["comment_id"])


def downgrade() -> None:
    op.drop_table("hash_comment_likes")
    op.drop_table("hash_comments")
    op.drop_table("hash_votes")
    op.drop_table("hash_likes")
