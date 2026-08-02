"""add immutable reputation events and baseline score

Revision ID: 20260802_0009
Revises: 20260802_0008
Create Date: 2026-08-02
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260802_0009"
down_revision = "20260802_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE users SET reputation_score = 50 WHERE reputation_score = 0"))
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "reputation_score",
            existing_type=sa.Integer(),
            nullable=False,
            server_default=sa.text("50"),
        )

    op.create_table(
        "reputation_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("reference_id", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("previous_score", sa.Integer(), nullable=False),
        sa.Column("next_score", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "event_type", "reference_id", name="uq_reputation_event_reference"
        ),
    )
    for column in (
        "user_id",
        "event_type",
        "reference_id",
        "reason_code",
        "rule_version",
        "created_at",
    ):
        op.create_index(f"ix_reputation_events_{column}", "reputation_events", [column])


def downgrade() -> None:
    for column in (
        "created_at",
        "rule_version",
        "reason_code",
        "reference_id",
        "event_type",
        "user_id",
    ):
        op.drop_index(f"ix_reputation_events_{column}", table_name="reputation_events")
    op.drop_table("reputation_events")
    op.execute(sa.text("UPDATE users SET reputation_score = 0"))
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "reputation_score",
            existing_type=sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        )
