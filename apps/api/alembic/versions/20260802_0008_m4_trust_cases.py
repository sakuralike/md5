"""add report and appeal trust cases

Revision ID: 20260802_0008
Revises: 20260802_0007
Create Date: 2026-08-02
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260802_0008"
down_revision = "20260802_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trust_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reporter_id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("related_case_id", sa.String(36), nullable=True),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assigned_to_id", sa.String(36), nullable=True),
        sa.Column("resolved_by_id", sa.String(36), nullable=True),
        sa.Column("resolution_code", sa.String(64), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["candidate_id"], ["password_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["related_case_id"], ["trust_cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    for column in (
        "kind",
        "status",
        "reporter_id",
        "candidate_id",
        "related_case_id",
        "reason_code",
        "assigned_to_id",
        "resolved_by_id",
        "created_at",
    ):
        op.create_index(f"ix_trust_cases_{column}", "trust_cases", [column])

    op.create_table(
        "trust_case_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("previous_status", sa.String(16), nullable=True),
        sa.Column("next_status", sa.String(16), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["trust_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    for column in ("case_id", "actor_id", "request_id", "created_at"):
        op.create_index(f"ix_trust_case_events_{column}", "trust_case_events", [column])


def downgrade() -> None:
    op.drop_table("trust_case_events")
    op.drop_table("trust_cases")
