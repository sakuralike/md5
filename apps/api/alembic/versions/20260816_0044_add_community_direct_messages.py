"""add community direct message persistence

Revision ID: 20260816_0044
Revises: 20260816_0043
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260816_0044"
down_revision: str | None = "20260816_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_direct_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("participant_low_id", sa.String(36), nullable=False),
        sa.Column("participant_high_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["participant_low_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_high_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "participant_low_id",
            "participant_high_id",
            name="uq_community_direct_conversation_pair",
        ),
    )
    op.create_index(
        "ix_community_direct_conversations_participant_low_id",
        "community_direct_conversations",
        ["participant_low_id"],
    )
    op.create_index(
        "ix_community_direct_conversations_participant_high_id",
        "community_direct_conversations",
        ["participant_high_id"],
    )
    op.create_index(
        "ix_community_direct_conversations_created_at",
        "community_direct_conversations",
        ["created_at"],
    )
    op.create_index(
        "ix_community_direct_conversations_updated_at",
        "community_direct_conversations",
        ["updated_at"],
    )

    op.create_table(
        "community_direct_conversation_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("last_read_sequence", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("muted_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["community_direct_conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("conversation_id", "user_id", name="uq_community_direct_member"),
    )
    op.create_index(
        "ix_community_direct_conversation_members_conversation_id",
        "community_direct_conversation_members",
        ["conversation_id"],
    )
    op.create_index(
        "ix_community_direct_conversation_members_user_id",
        "community_direct_conversation_members",
        ["user_id"],
    )
    op.create_index(
        "ix_community_direct_conversation_members_created_at",
        "community_direct_conversation_members",
        ["created_at"],
    )
    op.create_index(
        "ix_community_direct_member_user_updated",
        "community_direct_conversation_members",
        ["user_id", "updated_at"],
    )

    op.create_table(
        "community_direct_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("sender_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("nonce", sa.String(32), nullable=False),
        sa.Column("key_version", sa.String(32), nullable=False),
        sa.Column("client_message_id", sa.String(72), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["community_direct_conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence",
            name="uq_community_direct_message_sequence",
        ),
        sa.UniqueConstraint(
            "sender_id",
            "client_message_id",
            name="uq_community_direct_sender_client_message",
        ),
    )
    op.create_index(
        "ix_community_direct_messages_conversation_id",
        "community_direct_messages",
        ["conversation_id"],
    )
    op.create_index(
        "ix_community_direct_messages_sender_id",
        "community_direct_messages",
        ["sender_id"],
    )
    op.create_index(
        "ix_community_direct_messages_created_at",
        "community_direct_messages",
        ["created_at"],
    )
    op.create_index(
        "ix_community_direct_message_conversation_sequence",
        "community_direct_messages",
        ["conversation_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_table("community_direct_messages")
    op.drop_table("community_direct_conversation_members")
    op.drop_table("community_direct_conversations")
