"""add manual candidate moderation metadata

Revision ID: 20260802_0007
Revises: 20260802_0006
Create Date: 2026-08-02
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260802_0007"
down_revision = "20260802_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("record_state_events") as batch_op:
        batch_op.add_column(sa.Column("reason_note", sa.String(500), nullable=True))
        batch_op.add_column(
            sa.Column(
                "transition_source",
                sa.String(16),
                nullable=False,
                server_default="AUTOMATIC",
            )
        )
        batch_op.add_column(sa.Column("actor_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("request_id", sa.String(128), nullable=True))
        batch_op.create_foreign_key(
            "fk_record_state_events_actor_id_users",
            "users",
            ["actor_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_record_state_events_transition_source", ["transition_source"])
        batch_op.create_index("ix_record_state_events_actor_id", ["actor_id"])
        batch_op.create_index("ix_record_state_events_request_id", ["request_id"])


def downgrade() -> None:
    with op.batch_alter_table("record_state_events") as batch_op:
        batch_op.drop_constraint("fk_record_state_events_actor_id_users", type_="foreignkey")
        batch_op.drop_index("ix_record_state_events_request_id")
        batch_op.drop_index("ix_record_state_events_actor_id")
        batch_op.drop_index("ix_record_state_events_transition_source")
        batch_op.drop_column("request_id")
        batch_op.drop_column("actor_id")
        batch_op.drop_column("transition_source")
        batch_op.drop_column("reason_note")
