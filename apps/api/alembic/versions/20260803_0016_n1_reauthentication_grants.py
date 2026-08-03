"""add one-time reauthentication grants

Revision ID: 20260803_0016
Revises: 20260803_0015
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260803_0016"
down_revision = "20260803_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reauthentication_grants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("session_family_id", sa.String(36), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("mfa_verified", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_reauth_grants_user_session_purpose_active",
        "reauthentication_grants",
        ["user_id", "session_family_id", "purpose", "consumed_at", "expires_at"],
    )
    for column in ("user_id", "session_family_id", "purpose", "token_hash", "expires_at"):
        op.create_index(
            f"ix_reauthentication_grants_{column}",
            "reauthentication_grants",
            [column],
        )


def downgrade() -> None:
    op.drop_table("reauthentication_grants")
