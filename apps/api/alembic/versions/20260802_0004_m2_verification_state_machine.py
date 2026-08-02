"""add verification evidence, feedback history and state events

Revision ID: 20260802_0004
Revises: 20260802_0003
Create Date: 2026-08-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260802_0004"
down_revision = "20260802_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_feedbacks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("installation_id_hash", sa.String(64), nullable=True),
        sa.Column("ip_prefix", sa.String(64), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["password_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("candidate_id", "user_id", name="uq_candidate_feedback_candidate_user"),
    )
    op.create_index("ix_candidate_feedbacks_candidate_id", "candidate_feedbacks", ["candidate_id"])
    op.create_index("ix_candidate_feedbacks_user_id", "candidate_feedbacks", ["user_id"])
    op.create_index("ix_candidate_feedbacks_outcome", "candidate_feedbacks", ["outcome"])
    op.create_index(
        "ix_candidate_feedbacks_installation_id_hash",
        "candidate_feedbacks",
        ["installation_id_hash"],
    )
    op.create_index("ix_candidate_feedbacks_ip_prefix", "candidate_feedbacks", ["ip_prefix"])

    op.create_table(
        "verification_evidence_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("feedback_id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("previous_outcome", sa.String(16), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("installation_id_hash", sa.String(64), nullable=True),
        sa.Column("ip_prefix", sa.String(64), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["feedback_id"], ["candidate_feedbacks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["password_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_verification_evidence_events_feedback_id",
        "verification_evidence_events",
        ["feedback_id"],
    )
    op.create_index(
        "ix_verification_evidence_events_candidate_id",
        "verification_evidence_events",
        ["candidate_id"],
    )
    op.create_index(
        "ix_verification_evidence_events_user_id",
        "verification_evidence_events",
        ["user_id"],
    )
    op.create_index(
        "ix_verification_evidence_events_outcome",
        "verification_evidence_events",
        ["outcome"],
    )
    op.create_index(
        "ix_verification_evidence_events_rule_version",
        "verification_evidence_events",
        ["rule_version"],
    )

    op.create_table(
        "record_state_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("previous_status", sa.String(16), nullable=False),
        sa.Column("next_status", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("trigger_evidence_id", sa.String(36), nullable=True),
        sa.Column("independent_success_count", sa.Integer(), nullable=False),
        sa.Column("independent_failure_count", sa.Integer(), nullable=False),
        sa.Column("success_weight", sa.Float(), nullable=False),
        sa.Column("failure_weight", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["password_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["trigger_evidence_id"],
            ["verification_evidence_events.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_record_state_events_candidate_id", "record_state_events", ["candidate_id"])
    op.create_index("ix_record_state_events_next_status", "record_state_events", ["next_status"])
    op.create_index("ix_record_state_events_reason_code", "record_state_events", ["reason_code"])
    op.create_index("ix_record_state_events_rule_version", "record_state_events", ["rule_version"])


def downgrade() -> None:
    op.drop_table("record_state_events")
    op.drop_table("verification_evidence_events")
    op.drop_table("candidate_feedbacks")
