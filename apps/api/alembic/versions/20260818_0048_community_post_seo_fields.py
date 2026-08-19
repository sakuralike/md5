"""add community post seo fields

Revision ID: 20260818_0048
Revises: 20260817_0047
Create Date: 2026-08-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0048"
down_revision: str | None = "20260817_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("community_posts", sa.Column("seo_title", sa.String(length=120), nullable=True))
    op.add_column("community_posts", sa.Column("seo_description", sa.String(length=320), nullable=True))
    op.add_column("community_posts", sa.Column("seo_keywords", sa.JSON(), nullable=True))
    op.add_column("community_posts", sa.Column("seo_canonical_path", sa.String(length=512), nullable=True))
    op.add_column("community_posts", sa.Column("og_image_url", sa.String(length=1024), nullable=True))
    op.add_column("community_posts", sa.Column("seo_version", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("community_posts", "seo_version", server_default=None)


def downgrade() -> None:
    op.drop_column("community_posts", "seo_version")
    op.drop_column("community_posts", "og_image_url")
    op.drop_column("community_posts", "seo_canonical_path")
    op.drop_column("community_posts", "seo_keywords")
    op.drop_column("community_posts", "seo_description")
    op.drop_column("community_posts", "seo_title")
