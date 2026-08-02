"""add M4 failure-surge risk alerts

Revision ID: 20260802_0011
Revises: 20260802_0010
Create Date: 2026-08-02
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260802_0011"
down_revision = "20260802_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "risk_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("trigger_evidence_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("independent_failure_count", sa.Integer(), nullable=False),
        sa.Column("failure_weight", sa.Float(), nullable=False),
        sa.Column("assigned_to_id", sa.String(36), nullable=True),
        sa.Column("resolved_by_id", sa.String(36), nullable=True),
        sa.Column("resolution_code", sa.String(64), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["password_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["trigger_evidence_id"],
            ["verification_evidence_events.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("trigger_evidence_id", name="uq_risk_alerts_trigger_evidence_id"),
    )
    for column in (
        "candidate_id",
        "kind",
        "severity",
        "status",
        "rule_version",
        "assigned_to_id",
        "resolved_by_id",
        "created_at",
    ):
        op.create_index(f"ix_risk_alerts_{column}", "risk_alerts", [column])

    op.create_table(
        "risk_alert_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alert_id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("previous_status", sa.String(16), nullable=True),
        sa.Column("next_status", sa.String(16), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["risk_alerts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    for column in ("alert_id", "actor_id", "request_id", "created_at"):
        op.create_index(f"ix_risk_alert_events_{column}", "risk_alert_events", [column])


def downgrade() -> None:
    # Direct table drops are compatible with MySQL foreign-key-backed indexes.
    op.drop_table("risk_alert_events")
    op.drop_table("risk_alerts")
