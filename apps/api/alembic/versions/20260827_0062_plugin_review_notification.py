"""add plugin review notification kind"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260827_0062"
down_revision: str | None = "20260827_0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "mysql":
        op.execute("ALTER TABLE community_notifications MODIFY kind ENUM('mention','reply','follow','like_summary','group_application','group_decision','group_role_change','direct_message','plugin_review') NOT NULL")


def downgrade() -> None:
    if op.get_bind().dialect.name == "mysql":
        op.execute("DELETE FROM community_notifications WHERE kind='plugin_review'")
        op.execute("ALTER TABLE community_notifications MODIFY kind ENUM('mention','reply','follow','like_summary','group_application','group_decision','group_role_change','direct_message') NOT NULL")
