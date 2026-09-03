from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0036"
down_revision: str | None = "20260814_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("community_notification_outbox") as batch_op:
        batch_op.add_column(
            sa.Column("replay_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("last_replayed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("last_replayed_by_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_community_notification_outbox_last_replayed_by_users",
            "users",
            ["last_replayed_by_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_community_notification_outbox_last_replayed_by_id",
            ["last_replayed_by_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("community_notification_outbox") as batch_op:
        batch_op.drop_constraint(
            "fk_community_notification_outbox_last_replayed_by_users",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_community_notification_outbox_last_replayed_by_id")
        batch_op.drop_column("last_replayed_by_id")
        batch_op.drop_column("last_replayed_at")
        batch_op.drop_column("replay_count")
