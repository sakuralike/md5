"""add immutable reward adjustment events

Revision ID: 20260802_0010
Revises: 20260802_0009
Create Date: 2026-08-02
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260802_0010"
down_revision = "20260802_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reward_adjustment_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("state_event_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("reward_kind", sa.String(24), nullable=False),
        sa.Column("source_reference_id", sa.String(36), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("points_amount", sa.Integer(), nullable=False),
        sa.Column("reputation_amount", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(96), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["password_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["state_event_id"], ["record_state_events.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "state_event_id",
            "user_id",
            "reward_kind",
            "source_reference_id",
            name="uq_reward_adjustment_state_user_source",
        ),
    )
    for column in (
        "candidate_id",
        "state_event_id",
        "user_id",
        "reward_kind",
        "source_reference_id",
        "direction",
        "reason_code",
        "rule_version",
        "created_at",
    ):
        op.create_index(
            f"ix_reward_adjustment_events_{column}",
            "reward_adjustment_events",
            [column],
        )


def downgrade() -> None:
    # Dropping the table also drops its indexes. MySQL may use an explicit
    # index to enforce a foreign key and rejects dropping that index first.
    op.drop_table("reward_adjustment_events")
