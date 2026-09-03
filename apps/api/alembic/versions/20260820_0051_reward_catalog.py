"""add virtual reward catalog

Revision ID: 20260820_0051
Revises: 20260819_0050
Create Date: 2026-08-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260820_0051"
down_revision: str | None = "20260819_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reward_catalog_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("VIRTUAL", name="rewardcatalogkind", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("cost_points", sa.Integer(), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("per_user_limit", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "ACTIVE",
                "INACTIVE",
                name="rewardcatalogstatus",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_reward_catalog_items_slug"),
    )
    op.create_index("ix_reward_catalog_items_slug", "reward_catalog_items", ["slug"])
    op.create_index("ix_reward_catalog_items_status", "reward_catalog_items", ["status"])
    op.create_index("ix_reward_catalog_items_created_by", "reward_catalog_items", ["created_by"])
    op.create_index("ix_reward_catalog_items_updated_by", "reward_catalog_items", ["updated_by"])


def downgrade() -> None:
    op.drop_table("reward_catalog_items")
