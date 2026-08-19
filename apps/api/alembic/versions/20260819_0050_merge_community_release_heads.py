"""merge the community image and SEO release migration heads

Revision ID: 20260819_0050
Revises: 20260819_0044, 20260819_0049
Create Date: 2026-08-19
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "20260819_0050"
down_revision: tuple[str, str] = ("20260819_0044", "20260819_0049")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
