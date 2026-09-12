"""add direct message reports and redaction metadata

Revision ID: 20260912_0065
Revises: 20260902_0064
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260912_0065"
down_revision: str | None = "20260902_0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    message_columns = {column["name"] for column in inspector.get_columns("community_direct_messages")}
    if "removed_at" not in message_columns:
        with op.batch_alter_table("community_direct_messages") as batch:
            batch.add_column(sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))

    tables = set(inspector.get_table_names())
    if "community_direct_message_reports" not in tables:
        op.create_table(
            "community_direct_message_reports",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("reporter_id", sa.String(length=36), nullable=False),
            sa.Column("message_id", sa.String(length=36), nullable=True),
            sa.Column("conversation_id", sa.String(length=36), nullable=True),
            sa.Column("sender_id", sa.String(length=36), nullable=True),
            sa.Column("reason", sa.String(length=24), nullable=False),
            sa.Column("details", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("decision", sa.String(length=24), nullable=True),
            sa.Column("resolved_by_id", sa.String(length=36), nullable=True),
            sa.Column("resolution_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(
                ["message_id"],
                ["community_direct_messages.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["conversation_id"],
                ["community_direct_conversations.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "community_direct_message_cooldowns" not in tables:
        op.create_table(
            "community_direct_message_cooldowns",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("reason", sa.String(length=64), nullable=False),
            sa.Column("until", sa.DateTime(timezone=True), nullable=False),
            sa.Column("triggered_message_count", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )
    indexes = {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("community_direct_message_reports")
    }
    if "ix_community_direct_message_report_reporter_message_status" not in indexes:
        op.create_index(
            "ix_community_direct_message_report_reporter_message_status",
            "community_direct_message_reports",
            ["reporter_id", "message_id", "status"],
        )
    if "ix_community_direct_message_report_status_created" not in indexes:
        op.create_index(
            "ix_community_direct_message_report_status_created",
            "community_direct_message_reports",
            ["status", "created_at"],
        )
    for index_name, columns in (
        ("ix_community_direct_message_reports_reporter_id", ["reporter_id"]),
        ("ix_community_direct_message_reports_message_id", ["message_id"]),
        ("ix_community_direct_message_reports_conversation_id", ["conversation_id"]),
        ("ix_community_direct_message_reports_sender_id", ["sender_id"]),
        ("ix_community_direct_message_reports_reason", ["reason"]),
        ("ix_community_direct_message_reports_status", ["status"]),
        ("ix_community_direct_message_reports_resolved_by_id", ["resolved_by_id"]),
        ("ix_community_direct_message_reports_created_at", ["created_at"]),
    ):
        if index_name not in indexes:
            op.create_index(index_name, "community_direct_message_reports", columns)
    cooldown_indexes = {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes("community_direct_message_cooldowns")
    }
    if "ix_community_direct_message_cooldown_until" not in cooldown_indexes:
        op.create_index(
            "ix_community_direct_message_cooldown_until",
            "community_direct_message_cooldowns",
            ["until"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "community_direct_message_cooldowns" in inspector.get_table_names():
        cooldown_indexes = {
            index["name"]
            for index in sa.inspect(op.get_bind()).get_indexes("community_direct_message_cooldowns")
        }
        if "ix_community_direct_message_cooldown_until" in cooldown_indexes:
            op.drop_index(
                "ix_community_direct_message_cooldown_until",
                table_name="community_direct_message_cooldowns",
            )
        op.drop_table("community_direct_message_cooldowns")
    if "community_direct_message_reports" in inspector.get_table_names():
        indexes = {
            index["name"]
            for index in sa.inspect(op.get_bind()).get_indexes("community_direct_message_reports")
        }
        for index_name in (
            "ix_community_direct_message_reports_created_at",
            "ix_community_direct_message_reports_resolved_by_id",
            "ix_community_direct_message_reports_status",
            "ix_community_direct_message_reports_reason",
            "ix_community_direct_message_reports_sender_id",
            "ix_community_direct_message_reports_conversation_id",
            "ix_community_direct_message_reports_message_id",
            "ix_community_direct_message_reports_reporter_id",
            "ix_community_direct_message_report_status_created",
            "ix_community_direct_message_report_reporter_message_status",
        ):
            if index_name in indexes:
                op.drop_index(index_name, table_name="community_direct_message_reports")
        op.drop_table("community_direct_message_reports")

    message_columns = {column["name"] for column in inspector.get_columns("community_direct_messages")}
    if "removed_at" in message_columns:
        with op.batch_alter_table("community_direct_messages") as batch:
            batch.drop_column("removed_at")
