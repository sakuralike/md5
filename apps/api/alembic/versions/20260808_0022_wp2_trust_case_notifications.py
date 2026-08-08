"""add trust case result notification outbox

Revision ID: 20260808_0022
Revises: 20260808_0021
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260808_0022"
down_revision: str | None = "20260808_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trust_case_notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=True),
        sa.Column("recipient_user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("RESOLUTION", name="trustcasenotificationkind", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "SENT",
                "FAILED",
                name="trustcasenotificationstatus",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("replay_count", sa.Integer(), nullable=False),
        sa.Column("last_replayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_replayed_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["trust_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["trust_case_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["last_replayed_by_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    for column in (
        "case_id",
        "recipient_user_id",
        "kind",
        "status",
        "provider",
        "available_at",
        "failed_at",
        "created_at",
    ):
        op.create_index(
            op.f(f"ix_trust_case_notifications_{column}"),
            "trust_case_notifications",
            [column],
        )


def downgrade() -> None:
    for column in reversed(
        (
            "case_id",
            "recipient_user_id",
            "kind",
            "status",
            "provider",
            "available_at",
            "failed_at",
            "created_at",
        )
    ):
        op.drop_index(
            op.f(f"ix_trust_case_notifications_{column}"),
            table_name="trust_case_notifications",
        )
    op.drop_table("trust_case_notifications")
