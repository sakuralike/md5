"""add trust case SLA escalation fields

Revision ID: 20260808_0023
Revises: 20260808_0022
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260808_0023"
down_revision: str | None = "20260808_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trust_cases", sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "trust_cases",
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "trust_cases",
        sa.Column("escalation_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "trust_cases", sa.Column("last_escalation_reason", sa.String(length=64), nullable=True)
    )
    op.create_index("ix_trust_cases_sla_due_at", "trust_cases", ["sla_due_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trust_cases_sla_due_at", table_name="trust_cases")
    op.drop_column("trust_cases", "last_escalation_reason")
    op.drop_column("trust_cases", "escalation_count")
    op.drop_column("trust_cases", "escalated_at")
    op.drop_column("trust_cases", "sla_due_at")
