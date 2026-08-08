"""add trust case resolution side effect ledger

Revision ID: 20260808_0021
Revises: 20260808_0020
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260808_0021"
down_revision: str | None = "20260808_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trust_case_effects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column(
            "effect_type",
            sa.Enum(
                "ACCOUNT_STATUS",
                "CANDIDATE_STATUS",
                "REWARD_RECONCILIATION",
                name="trustcaseeffecttype",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("previous_value", sa.String(length=64), nullable=True),
        sa.Column("next_value", sa.String(length=64), nullable=True),
        sa.Column("reference_id", sa.String(length=36), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["trust_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "case_id",
            "case_version",
            "effect_type",
            name="uq_trust_case_effect_version_type",
        ),
    )
    op.create_index(
        op.f("ix_trust_case_effects_case_id"), "trust_case_effects", ["case_id"]
    )
    op.create_index(
        op.f("ix_trust_case_effects_effect_type"),
        "trust_case_effects",
        ["effect_type"],
    )
    op.create_index(
        op.f("ix_trust_case_effects_target_id"), "trust_case_effects", ["target_id"]
    )
    op.create_index(
        op.f("ix_trust_case_effects_reference_id"),
        "trust_case_effects",
        ["reference_id"],
    )
    op.create_index(
        op.f("ix_trust_case_effects_created_at"), "trust_case_effects", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_trust_case_effects_created_at"), table_name="trust_case_effects")
    op.drop_index(op.f("ix_trust_case_effects_reference_id"), table_name="trust_case_effects")
    op.drop_index(op.f("ix_trust_case_effects_target_id"), table_name="trust_case_effects")
    op.drop_index(op.f("ix_trust_case_effects_effect_type"), table_name="trust_case_effects")
    op.drop_index(op.f("ix_trust_case_effects_case_id"), table_name="trust_case_effects")
    op.drop_table("trust_case_effects")
