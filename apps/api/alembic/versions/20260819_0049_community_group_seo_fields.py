"""add community group seo fields

Revision ID: 20260819_0049
Revises: 20260818_0048
Create Date: 2026-08-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260819_0049"
down_revision: str | None = "20260818_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("community_groups", sa.Column("seo_title", sa.String(length=120), nullable=True))
    op.add_column(
        "community_groups", sa.Column("seo_description", sa.String(length=320), nullable=True)
    )
    op.add_column("community_groups", sa.Column("seo_keywords", sa.JSON(), nullable=True))
    op.add_column(
        "community_groups", sa.Column("seo_canonical_path", sa.String(length=512), nullable=True)
    )
    op.add_column(
        "community_groups", sa.Column("og_image_url", sa.String(length=1024), nullable=True)
    )
    op.add_column(
        "community_groups",
        sa.Column("seo_version", sa.Integer(), nullable=False, server_default="1"),
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("community_groups") as batch_op:
            batch_op.alter_column(
                "seo_version",
                existing_type=sa.Integer(),
                existing_nullable=False,
                server_default=None,
            )
    else:
        op.alter_column("community_groups", "seo_version", server_default=None)


def downgrade() -> None:
    op.drop_column("community_groups", "seo_version")
    op.drop_column("community_groups", "og_image_url")
    op.drop_column("community_groups", "seo_canonical_path")
    op.drop_column("community_groups", "seo_keywords")
    op.drop_column("community_groups", "seo_description")
    op.drop_column("community_groups", "seo_title")
