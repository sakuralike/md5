"""add desktop release distribution authorization metadata

Revision ID: 20260811_0024
Revises: 20260808_0023
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0024"
down_revision: str | None = "20260808_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "desktop_releases",
        sa.Column("distribution_authorized", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "desktop_releases",
        sa.Column("legal_declaration", sa.String(length=2_000), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("desktop_releases", "legal_declaration")
    op.drop_column("desktop_releases", "distribution_authorized")
