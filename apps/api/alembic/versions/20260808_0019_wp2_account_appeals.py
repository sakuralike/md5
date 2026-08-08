"""extend trust cases with account appeal subjects

Revision ID: 20260808_0019
Revises: 20260804_0018
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0019"
down_revision: str | None = "20260804_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SUBJECT_CHECK = (
    "(subject_type = 'CANDIDATE' AND candidate_id IS NOT NULL "
    "AND target_user_id IS NULL AND risk_alert_id IS NULL) OR "
    "(subject_type = 'ACCOUNT' AND candidate_id IS NULL "
    "AND target_user_id IS NOT NULL AND risk_alert_id IS NULL) OR "
    "(subject_type = 'RISK_ALERT' AND candidate_id IS NULL "
    "AND target_user_id IS NULL AND risk_alert_id IS NOT NULL)"
)


def upgrade() -> None:
    with op.batch_alter_table("trust_cases") as batch_op:
        batch_op.add_column(
            sa.Column(
                "subject_type",
                sa.String(length=16),
                nullable=False,
                server_default="CANDIDATE",
            )
        )
        batch_op.add_column(sa.Column("target_user_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("risk_alert_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("requested_action", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("evidence_summary", sa.Text(), nullable=True))
        batch_op.alter_column(
            "candidate_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch_op.create_foreign_key(
            "fk_trust_cases_target_user_id_users",
            "users",
            ["target_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_trust_cases_risk_alert_id_risk_alerts",
            "risk_alerts",
            ["risk_alert_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_check_constraint("ck_trust_cases_single_subject", _SUBJECT_CHECK)
        batch_op.create_index("ix_trust_cases_subject_type", ["subject_type"])
        batch_op.create_index("ix_trust_cases_target_user_id", ["target_user_id"])
        batch_op.create_index("ix_trust_cases_risk_alert_id", ["risk_alert_id"])
        batch_op.create_index("ix_trust_cases_requested_action", ["requested_action"])

    with op.batch_alter_table("trust_cases") as batch_op:
        batch_op.alter_column(
            "subject_type",
            existing_type=sa.String(length=16),
            nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM trust_cases WHERE subject_type <> 'CANDIDATE'"))
    with op.batch_alter_table("trust_cases") as batch_op:
        batch_op.drop_index("ix_trust_cases_requested_action")
        batch_op.drop_index("ix_trust_cases_risk_alert_id")
        batch_op.drop_index("ix_trust_cases_target_user_id")
        batch_op.drop_index("ix_trust_cases_subject_type")
        batch_op.drop_constraint("ck_trust_cases_single_subject", type_="check")
        batch_op.drop_constraint(
            "fk_trust_cases_risk_alert_id_risk_alerts", type_="foreignkey"
        )
        batch_op.drop_constraint("fk_trust_cases_target_user_id_users", type_="foreignkey")
        batch_op.alter_column(
            "candidate_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch_op.drop_column("evidence_summary")
        batch_op.drop_column("requested_action")
        batch_op.drop_column("risk_alert_id")
        batch_op.drop_column("target_user_id")
        batch_op.drop_column("subject_type")
