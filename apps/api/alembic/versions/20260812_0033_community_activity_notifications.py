"""add community activity feeds and notification preferences

Revision ID: 20260812_0033
Revises: 20260812_0032
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0033"
down_revision: str | None = "20260812_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOTIFICATION_KINDS = (
    "MENTION",
    "REPLY",
    "FOLLOW",
    "LIKE_SUMMARY",
    "GROUP_APPLICATION",
    "GROUP_DECISION",
    "GROUP_ROLE_CHANGE",
)
_ACTIVITY_KINDS = (
    "POST_PUBLISHED",
    "COMMENT_PUBLISHED",
    "GROUP_JOINED",
    "USER_FOLLOWED",
)
_ACTIVITY_SOURCES = ("POST", "COMMENT", "GROUP_MEMBERSHIP", "USER_FOLLOW")


def upgrade() -> None:
    with op.batch_alter_table("community_notifications") as batch_op:
        batch_op.alter_column(
            "post_id", existing_type=sa.String(36), nullable=True
        )

    op.create_table(
        "community_notification_preferences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                *_NOTIFICATION_KINDS,
                name="communitynotificationkind",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False),
        sa.Column("email_digest_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "kind", name="uq_community_notification_preference"
        ),
    )
    for column in ("user_id", "kind"):
        op.create_index(
            f"ix_community_notification_preferences_{column}",
            "community_notification_preferences",
            [column],
        )

    op.create_table(
        "community_activity_preferences",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("share_group_joins", sa.Boolean(), nullable=False),
        sa.Column("share_follows", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "community_activity_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                *_ACTIVITY_KINDS,
                name="communityactivitykind",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            sa.Enum(
                *_ACTIVITY_SOURCES,
                name="communityactivitysource",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("post_id", sa.String(36), nullable=True),
        sa.Column("comment_id", sa.String(36), nullable=True),
        sa.Column("group_id", sa.String(36), nullable=True),
        sa.Column("target_user_id", sa.String(36), nullable=True),
        sa.Column("preview", sa.String(180), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["post_id"], ["community_posts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["comment_id"], ["community_comments.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["group_id"], ["community_groups.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "kind", "source_type", "source_id", name="uq_community_activity_source"
        ),
    )
    for column in (
        "actor_id",
        "kind",
        "source_type",
        "post_id",
        "comment_id",
        "group_id",
        "target_user_id",
        "is_public",
        "created_at",
    ):
        op.create_index(
            f"ix_community_activity_events_{column}",
            "community_activity_events",
            [column],
        )


def downgrade() -> None:
    op.drop_table("community_activity_events")
    op.drop_table("community_activity_preferences")
    op.drop_table("community_notification_preferences")
    with op.batch_alter_table("community_notifications") as batch_op:
        batch_op.alter_column(
            "post_id", existing_type=sa.String(36), nullable=False
        )
