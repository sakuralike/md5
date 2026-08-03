"""add M4 alert SLA, assignment history and notification outbox

Revision ID: 20260803_0013
Revises: 20260803_0012
Create Date: 2026-08-03
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from alembic import op

revision = "20260803_0013"
down_revision = "20260803_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("risk_alerts", sa.Column("sla_rule_version", sa.String(32), nullable=True))
    op.add_column(
        "risk_alerts", sa.Column("acknowledge_due_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "risk_alerts", sa.Column("resolve_due_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "risk_alerts", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True)
    )

    alerts = sa.table(
        "risk_alerts",
        sa.column("id", sa.String(36)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("sla_rule_version", sa.String(32)),
        sa.column("acknowledge_due_at", sa.DateTime(timezone=True)),
        sa.column("resolve_due_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    for row in bind.execute(sa.select(alerts.c.id, alerts.c.created_at)):
        created_at = row.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        bind.execute(
            alerts.update()
            .where(alerts.c.id == row.id)
            .values(
                sla_rule_version="risk-alert-sla-v1",
                acknowledge_due_at=created_at + timedelta(minutes=15),
                resolve_due_at=created_at + timedelta(hours=4),
            )
        )

    with op.batch_alter_table("risk_alerts") as batch_op:
        batch_op.alter_column(
            "sla_rule_version",
            existing_type=sa.String(length=32),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "acknowledge_due_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "resolve_due_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
            nullable=False,
        )
    for column in ("sla_rule_version", "acknowledge_due_at", "resolve_due_at"):
        op.create_index(f"ix_risk_alerts_{column}", "risk_alerts", [column])

    with op.batch_alter_table("risk_alert_events") as batch_op:
        batch_op.add_column(sa.Column("previous_assignee_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("next_assignee_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_risk_alert_events_previous_assignee_id_users",
            "users",
            ["previous_assignee_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_risk_alert_events_next_assignee_id_users",
            "users",
            ["next_assignee_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "risk_alert_notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alert_id", sa.String(36), nullable=False),
        sa.Column("event_id", sa.String(36), nullable=True),
        sa.Column("recipient_user_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("dedupe_key", sa.String(160), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["risk_alerts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["risk_alert_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("dedupe_key", name="uq_risk_alert_notifications_dedupe_key"),
    )
    for column in (
        "alert_id",
        "recipient_user_id",
        "kind",
        "status",
        "available_at",
        "created_at",
    ):
        op.create_index(
            f"ix_risk_alert_notifications_{column}", "risk_alert_notifications", [column]
        )


def downgrade() -> None:
    op.drop_table("risk_alert_notifications")
    with op.batch_alter_table("risk_alert_events") as batch_op:
        batch_op.drop_constraint("fk_risk_alert_events_next_assignee_id_users", type_="foreignkey")
        batch_op.drop_constraint(
            "fk_risk_alert_events_previous_assignee_id_users", type_="foreignkey"
        )
        batch_op.drop_column("next_assignee_id")
        batch_op.drop_column("previous_assignee_id")
    for column in ("resolve_due_at", "acknowledge_due_at", "sla_rule_version"):
        op.drop_index(f"ix_risk_alerts_{column}", table_name="risk_alerts")
    with op.batch_alter_table("risk_alerts") as batch_op:
        batch_op.drop_column("acknowledged_at")
        batch_op.drop_column("resolve_due_at")
        batch_op.drop_column("acknowledge_due_at")
        batch_op.drop_column("sla_rule_version")
