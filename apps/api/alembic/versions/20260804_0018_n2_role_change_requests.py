"""add dual-control role change requests

Revision ID: 20260804_0018
Revises: 20260803_0017
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0018"
down_revision: str | None = "20260803_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "role_change_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("target_user_id", sa.String(length=36), nullable=False),
        sa.Column("expected_role", sa.String(length=32), nullable=False),
        sa.Column("requested_role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requested_by", sa.String(length=36), nullable=False),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.Column("review_reason_code", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_role_change_requests_status", "role_change_requests", ["status"])
    op.create_index("ix_role_change_requests_requested_by", "role_change_requests", ["requested_by"])
    op.create_index("ix_role_change_requests_target_user_id", "role_change_requests", ["target_user_id"])
    op.create_index(
        "ix_role_change_requests_status_created", "role_change_requests", ["status", "created_at"]
    )
    op.create_index(
        "ix_role_change_requests_target_status", "role_change_requests", ["target_user_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_role_change_requests_target_status", table_name="role_change_requests")
    op.drop_index("ix_role_change_requests_status_created", table_name="role_change_requests")
    op.drop_index("ix_role_change_requests_target_user_id", table_name="role_change_requests")
    op.drop_index("ix_role_change_requests_requested_by", table_name="role_change_requests")
    op.drop_index("ix_role_change_requests_status", table_name="role_change_requests")
    op.drop_table("role_change_requests")
