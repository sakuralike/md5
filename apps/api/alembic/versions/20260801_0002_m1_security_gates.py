"""add M1 security gate tables and fields

Revision ID: 20260801_0002
Revises: 20260801_0001
Create Date: 2026-08-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260801_0002"
down_revision = "20260801_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("totp_pending_secret_ciphertext", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("totp_secret_ciphertext", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("totp_enabled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "user_sessions", sa.Column("mfa_verified_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table(
        "account_action_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_account_action_tokens_token_hash"),
    )
    op.create_index("ix_account_action_tokens_user_id", "account_action_tokens", ["user_id"])
    op.create_index("ix_account_action_tokens_kind", "account_action_tokens", ["kind"])
    op.create_index("ix_account_action_tokens_token_hash", "account_action_tokens", ["token_hash"])
    op.create_index("ix_account_action_tokens_expires_at", "account_action_tokens", ["expires_at"])
    op.create_index(
        "ix_account_tokens_user_kind_active",
        "account_action_tokens",
        ["user_id", "kind", "used_at", "expires_at"],
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scope", sa.String(100), nullable=False),
        sa.Column("owner_key", sa.String(64), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "scope", "owner_key", "key_hash", name="uq_idempotency_scope_owner_key"
        ),
    )
    op.create_index("ix_idempotency_records_scope", "idempotency_records", ["scope"])
    op.create_index("ix_idempotency_records_status", "idempotency_records", ["status"])
    op.create_index("ix_idempotency_records_expires_at", "idempotency_records", ["expires_at"])
    op.create_index(
        "ix_idempotency_expires_status", "idempotency_records", ["expires_at", "status"]
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
    op.drop_table("account_action_tokens")
    op.drop_column("user_sessions", "mfa_verified_at")
    op.drop_column("users", "totp_enabled_at")
    op.drop_column("users", "totp_secret_ciphertext")
    op.drop_column("users", "totp_pending_secret_ciphertext")
    op.drop_column("users", "email_verified_at")
