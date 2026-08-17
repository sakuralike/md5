"""add community notification email digests

Revision ID: 20260817_0047
Revises: 20260816_0046
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0047"
down_revision: str | None = "20260816_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_notification_email_digests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recipient_id", sa.String(length=36), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suppressed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_name", sa.String(length=32), nullable=True),
        sa.Column("provider_message_id", sa.String(length=512), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
        sa.UniqueConstraint("recipient_id", "window_started_at", name="uq_community_notification_email_digest_window"),
    )
    op.create_index("ix_community_notification_email_digests_recipient_id", "community_notification_email_digests", ["recipient_id"])
    op.create_index("ix_community_notification_email_digests_window_started_at", "community_notification_email_digests", ["window_started_at"])
    op.create_index("ix_community_notification_email_digests_window_ends_at", "community_notification_email_digests", ["window_ends_at"])
    op.create_index("ix_community_notification_email_digests_status", "community_notification_email_digests", ["status"])
    op.create_index("ix_community_notification_email_digests_available_at", "community_notification_email_digests", ["available_at"])
    op.create_table(
        "community_notification_email_digest_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("digest_id", sa.String(length=36), nullable=False),
        sa.Column("notification_id", sa.String(length=36), nullable=False),
        sa.Column("delivery_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["digest_id"], ["community_notification_email_digests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notification_id"], ["community_notifications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("digest_id", "notification_id", "delivery_version", name="uq_community_notification_email_digest_item_version"),
    )
    op.create_index("ix_community_notification_email_digest_items_digest_id", "community_notification_email_digest_items", ["digest_id"])
    op.create_index("ix_community_notification_email_digest_items_notification_id", "community_notification_email_digest_items", ["notification_id"])


def downgrade() -> None:
    op.drop_table("community_notification_email_digest_items")
    op.drop_table("community_notification_email_digests")
