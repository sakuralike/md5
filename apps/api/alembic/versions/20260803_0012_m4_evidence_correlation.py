"""add M4 evidence correlation assessments

Revision ID: 20260803_0012
Revises: 20260802_0011
Create Date: 2026-08-03
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260803_0012"
down_revision = "20260802_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_correlation_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("trigger_evidence_id", sa.String(36), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("feedback_count", sa.Integer(), nullable=False),
        sa.Column("independent_group_count", sa.Integer(), nullable=False),
        sa.Column("correlated_group_count", sa.Integer(), nullable=False),
        sa.Column("downweighted_feedback_count", sa.Integer(), nullable=False),
        sa.Column("raw_success_weight", sa.Float(), nullable=False),
        sa.Column("effective_success_weight", sa.Float(), nullable=False),
        sa.Column("raw_failure_weight", sa.Float(), nullable=False),
        sa.Column("effective_failure_weight", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["password_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["trigger_evidence_id"],
            ["verification_evidence_events.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "trigger_evidence_id",
            name="uq_evidence_correlation_assessments_trigger_evidence_id",
        ),
    )
    for column in ("candidate_id", "rule_version", "created_at"):
        op.create_index(
            f"ix_evidence_correlation_assessments_{column}",
            "evidence_correlation_assessments",
            [column],
        )


def downgrade() -> None:
    op.drop_table("evidence_correlation_assessments")
