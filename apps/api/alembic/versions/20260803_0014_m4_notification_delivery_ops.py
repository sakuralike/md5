"""add M4 notification provider, dead-letter and replay metadata

Revision ID: 20260803_0014
Revises: 20260803_0013
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260803_0014"
down_revision = "20260803_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("risk_alert_notifications") as batch_op:
        batch_op.add_column(sa.Column("provider", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("provider_message_id", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("replay_count", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("last_replayed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("last_replayed_by_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_risk_alert_notifications_last_replayed_by_id_users",
            "users",
            ["last_replayed_by_id"],
            ["id"],
            ondelete="SET NULL",
        )

    notifications = sa.table(
        "risk_alert_notifications",
        sa.column("replay_count", sa.Integer()),
    )
    op.execute(notifications.update().values(replay_count=0))
    with op.batch_alter_table("risk_alert_notifications") as batch_op:
        batch_op.alter_column(
            "replay_count",
            existing_type=sa.Integer(),
            existing_nullable=True,
            nullable=False,
        )

    op.create_index(
        "ix_risk_alert_notifications_provider",
        "risk_alert_notifications",
        ["provider"],
    )
    op.create_index(
        "ix_risk_alert_notifications_failed_at",
        "risk_alert_notifications",
        ["failed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_risk_alert_notifications_failed_at",
        table_name="risk_alert_notifications",
    )
    op.drop_index(
        "ix_risk_alert_notifications_provider",
        table_name="risk_alert_notifications",
    )
    with op.batch_alter_table("risk_alert_notifications") as batch_op:
        batch_op.drop_constraint(
            "fk_risk_alert_notifications_last_replayed_by_id_users",
            type_="foreignkey",
        )
        batch_op.drop_column("last_replayed_by_id")
        batch_op.drop_column("last_replayed_at")
        batch_op.drop_column("replay_count")
        batch_op.drop_column("failed_at")
        batch_op.drop_column("provider_message_id")
        batch_op.drop_column("provider")
