"""add plugin remediation deadline"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0061"
down_revision: str | None = "20260826_0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("desktop_plugin_versions", sa.Column("remediation_deadline_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_desktop_plugin_versions_remediation_deadline_at", "desktop_plugin_versions", ["remediation_deadline_at"])


def downgrade() -> None:
    op.drop_index("ix_desktop_plugin_versions_remediation_deadline_at", table_name="desktop_plugin_versions")
    op.drop_column("desktop_plugin_versions", "remediation_deadline_at")
