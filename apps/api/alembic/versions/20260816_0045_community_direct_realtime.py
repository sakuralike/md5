"""add durable community direct message realtime events

Revision ID: 20260816_0045
Revises: 20260816_0044
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260816_0045"
down_revision: str | None = "20260816_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_direct_stream_positions",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("last_sequence", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "community_direct_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recipient_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("message_id", sa.String(36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["community_direct_conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["community_direct_messages.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "recipient_id",
            "sequence",
            name="uq_community_direct_event_recipient_sequence",
        ),
    )
    op.create_index(
        "ix_community_direct_event_recipient_sequence",
        "community_direct_events",
        ["recipient_id", "sequence"],
    )
    op.create_index(
        "ix_community_direct_event_conversation_created",
        "community_direct_events",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("community_direct_events")
    op.drop_table("community_direct_stream_positions")