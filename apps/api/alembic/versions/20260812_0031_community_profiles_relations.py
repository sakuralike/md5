"""add community public profiles and relation graph

Revision ID: 20260812_0031
Revises: 20260812_0030
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0031"
down_revision: str | None = "20260812_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_relation_table(
    table_name: str,
    owner_column: str,
    target_column: str,
    unique_name: str,
    *,
    expires: bool = False,
) -> None:
    columns: list[sa.Column[object]] = [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(owner_column, sa.String(36), nullable=False),
        sa.Column(target_column, sa.String(36), nullable=False),
    ]
    if expires:
        columns.append(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    columns.append(sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table(
        table_name,
        *columns,
        sa.ForeignKeyConstraint([owner_column], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint([target_column], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(owner_column, target_column, name=unique_name),
    )
    op.create_index(f"ix_{table_name}_{owner_column}", table_name, [owner_column])
    op.create_index(f"ix_{table_name}_{target_column}", table_name, [target_column])
    op.create_index(f"ix_{table_name}_created_at", table_name, ["created_at"])
    if expires:
        op.create_index(f"ix_{table_name}_expires_at", table_name, ["expires_at"])


def upgrade() -> None:
    op.create_table(
        "community_public_profiles",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.String(48), nullable=False),
        sa.Column("bio", sa.String(300), nullable=False, server_default=""),
        sa.Column("avatar_seed", sa.String(32), nullable=False),
        sa.Column("follower_visibility", sa.String(16), nullable=False, server_default="PUBLIC"),
        sa.Column("following_visibility", sa.String(16), nullable=False, server_default="PUBLIC"),
        sa.Column("message_policy", sa.String(16), nullable=False, server_default="FOLLOWING"),
        sa.Column("mention_policy", sa.String(16), nullable=False, server_default="EVERYONE"),
        sa.Column("follower_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("following_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    _create_relation_table(
        "community_user_follows", "follower_id", "followed_id", "uq_community_user_follow_pair"
    )
    _create_relation_table(
        "community_user_blocks", "blocker_id", "blocked_id", "uq_community_user_block_pair"
    )
    _create_relation_table(
        "community_user_mutes",
        "user_id",
        "muted_user_id",
        "uq_community_user_mute_pair",
        expires=True,
    )


def downgrade() -> None:
    op.drop_table("community_user_mutes")
    op.drop_table("community_user_blocks")
    op.drop_table("community_user_follows")
    op.drop_table("community_public_profiles")
