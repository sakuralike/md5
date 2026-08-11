"""add user growth events and level projection

Revision ID: 20260811_0025
Revises: 20260811_0024
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0025"
down_revision: str | None = "20260811_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_growth_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("reference_id", sa.String(96), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "event_type", "reference_id", name="uq_user_growth_event_reference"
        ),
    )
    for column in ("user_id", "event_type", "reference_id", "reason_code", "rule_version", "created_at"):
        op.create_index(f"ix_user_growth_events_{column}", "user_growth_events", [column])

    op.create_table(
        "user_level_profiles",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("growth_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("level_code", sa.String(32), nullable=False),
        sa.Column("level_name", sa.String(64), nullable=False),
        sa.Column("level_rule_hash", sa.String(64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_level_profiles_level_code", "user_level_profiles", ["level_code"])
    op.create_index(
        "ix_user_level_profiles_level_rule_hash", "user_level_profiles", ["level_rule_hash"]
    )


def downgrade() -> None:
    op.drop_table("user_level_profiles")
    op.drop_table("user_growth_events")
