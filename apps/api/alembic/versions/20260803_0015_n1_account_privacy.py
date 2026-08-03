"""add N1 account activity and privacy workflows

Revision ID: 20260803_0015
Revises: 20260803_0014
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260803_0015"
down_revision = "20260803_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "authorization_declarations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("declaration_version", sa.String(32), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id",
            "declaration_version",
            "purpose",
            "source",
            name="uq_authorization_declarations_scope",
        ),
    )
    for column in (
        "user_id",
        "declaration_version",
        "purpose",
        "source",
    ):
        op.create_index(
            f"ix_authorization_declarations_{column}",
            "authorization_declarations",
            [column],
        )

    op.create_table(
        "privacy_exports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("artifact", sa.JSON(), nullable=True),
        sa.Column("artifact_sha256", sa.String(64), nullable=True),
        sa.Column("download_token_hash", sa.String(64), nullable=True),
        sa.Column("download_token_ciphertext", sa.Text(), nullable=True),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_privacy_exports_user_id", "privacy_exports", ["user_id"])
    op.create_index("ix_privacy_exports_status", "privacy_exports", ["status"])

    op.create_table(
        "privacy_deletion_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancel_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_privacy_deletion_requests_user_id",
        "privacy_deletion_requests",
        ["user_id"],
    )
    op.create_index(
        "ix_privacy_deletion_requests_status",
        "privacy_deletion_requests",
        ["status"],
    )
    op.create_index(
        "ix_privacy_deletion_requests_cancel_before",
        "privacy_deletion_requests",
        ["cancel_before"],
    )


def downgrade() -> None:
    op.drop_table("privacy_deletion_requests")
    op.drop_table("privacy_exports")
    op.drop_table("authorization_declarations")
