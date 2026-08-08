"""add trust case version and assignment event snapshots

Revision ID: 20260808_0020
Revises: 20260808_0019
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0020"
down_revision: str | None = "20260808_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("trust_cases") as batch_op:
        batch_op.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="1")
        )

    with op.batch_alter_table("trust_cases") as batch_op:
        batch_op.alter_column("version", existing_type=sa.Integer(), server_default=None)

    with op.batch_alter_table("trust_case_events") as batch_op:
        batch_op.add_column(sa.Column("previous_assignee_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("next_assignee_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_trust_case_events_previous_assignee_id_users",
            "users",
            ["previous_assignee_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_trust_case_events_next_assignee_id_users",
            "users",
            ["next_assignee_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_trust_case_events_previous_assignee_id", ["previous_assignee_id"]
        )
        batch_op.create_index("ix_trust_case_events_next_assignee_id", ["next_assignee_id"])


def downgrade() -> None:
    with op.batch_alter_table("trust_case_events") as batch_op:
        batch_op.drop_index("ix_trust_case_events_next_assignee_id")
        batch_op.drop_index("ix_trust_case_events_previous_assignee_id")
        batch_op.drop_constraint(
            "fk_trust_case_events_next_assignee_id_users", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_trust_case_events_previous_assignee_id_users", type_="foreignkey"
        )
        batch_op.drop_column("next_assignee_id")
        batch_op.drop_column("previous_assignee_id")

    with op.batch_alter_table("trust_cases") as batch_op:
        batch_op.drop_column("version")
