"""add reward fulfillment leases and trust case priority

Revision ID: 20260820_0053
Revises: 20260820_0052
Create Date: 2026-08-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260820_0053"
down_revision: str | None = "20260820_0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reward_fulfillments",
        sa.Column("lease_owner", sa.String(128), nullable=True),
    )
    op.add_column(
        "reward_fulfillments",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_reward_fulfillments_lease_owner", "reward_fulfillments", ["lease_owner"])
    op.create_index(
        "ix_reward_fulfillments_lease_expires_at",
        "reward_fulfillments",
        ["lease_expires_at"],
    )
    op.add_column(
        "trust_cases",
        sa.Column("priority_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "trust_cases",
        sa.Column("priority_reason", sa.String(64), nullable=True),
    )
    op.execute(sa.text("UPDATE trust_cases SET priority_score = 0 WHERE priority_score IS NULL"))
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("trust_cases") as batch_op:
            batch_op.alter_column(
                "priority_score",
                existing_type=sa.Integer(),
                existing_nullable=True,
                nullable=False,
            )
    else:
        op.alter_column("trust_cases", "priority_score", existing_type=sa.Integer(), nullable=False)
    op.create_index("ix_trust_cases_priority_score", "trust_cases", ["priority_score"])


def downgrade() -> None:
    op.drop_index("ix_trust_cases_priority_score", table_name="trust_cases")
    op.drop_column("trust_cases", "priority_reason")
    op.drop_column("trust_cases", "priority_score")
    op.drop_index("ix_reward_fulfillments_lease_expires_at", table_name="reward_fulfillments")
    op.drop_index("ix_reward_fulfillments_lease_owner", table_name="reward_fulfillments")
    op.drop_column("reward_fulfillments", "lease_expires_at")
    op.drop_column("reward_fulfillments", "lease_owner")
