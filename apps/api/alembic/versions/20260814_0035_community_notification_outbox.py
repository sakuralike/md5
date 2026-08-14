from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0035"
down_revision: str | None = "20260813_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "community_notifications",
        sa.Column("delivery_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "community_notification_outbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("notification_id", sa.String(36), nullable=False),
        sa.Column("recipient_id", sa.String(36), nullable=False),
        sa.Column("dedupe_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["community_notifications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("dedupe_key", name="uq_community_notification_outbox_dedupe"),
    )
    for column in (
        "notification_id",
        "recipient_id",
        "status",
        "available_at",
        "delivered_at",
        "failed_at",
        "created_at",
    ):
        op.create_index(
            f"ix_community_notification_outbox_{column}",
            "community_notification_outbox",
            [column],
        )


def downgrade() -> None:
    op.drop_table("community_notification_outbox")
    op.drop_column("community_notifications", "delivery_version")
