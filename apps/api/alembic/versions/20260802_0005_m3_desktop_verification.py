"""add desktop installations, one-time challenges and signed receipts

Revision ID: 20260802_0005
Revises: 20260802_0004
Create Date: 2026-08-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260802_0005"
down_revision = "20260802_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_installations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("public_key_der", sa.LargeBinary(), nullable=False),
        sa.Column("public_key_fingerprint", sa.String(64), nullable=False),
        sa.Column("key_algorithm", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("client_version", sa.String(32), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("receipt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_ip_prefix", sa.String(64), nullable=True),
        sa.Column("last_ip_prefix", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "public_key_fingerprint",
            name="uq_client_installations_public_key_fingerprint",
        ),
    )
    op.create_index("ix_client_installations_user_id", "client_installations", ["user_id"])
    op.create_index("ix_client_installations_status", "client_installations", ["status"])
    op.create_index(
        "ix_client_installations_public_key_fingerprint",
        "client_installations",
        ["public_key_fingerprint"],
    )

    op.create_table(
        "verification_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("installation_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("fingerprint_algorithm", sa.String(16), nullable=False),
        sa.Column("fingerprint_digest", sa.String(128), nullable=False),
        sa.Column("client_version", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["client_installations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["password_candidates.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_verification_challenges_installation_id",
        "verification_challenges",
        ["installation_id"],
    )
    op.create_index(
        "ix_verification_challenges_user_id", "verification_challenges", ["user_id"]
    )
    op.create_index(
        "ix_verification_challenges_candidate_id",
        "verification_challenges",
        ["candidate_id"],
    )
    op.create_index(
        "ix_verification_challenges_expires_at", "verification_challenges", ["expires_at"]
    )

    op.create_table(
        "verification_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("challenge_id", sa.String(36), nullable=False),
        sa.Column("installation_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("archive_format", sa.String(16), nullable=False),
        sa.Column("fingerprint_algorithm", sa.String(16), nullable=False),
        sa.Column("fingerprint_digest", sa.String(128), nullable=False),
        sa.Column("candidate_digest_hash", sa.String(64), nullable=False),
        sa.Column("client_version", sa.String(32), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canonical_payload_hash", sa.String(64), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("evidence_event_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["challenge_id"], ["verification_challenges.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["client_installations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["password_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["evidence_event_id"], ["verification_evidence_events.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("challenge_id", name="uq_verification_receipts_challenge_id"),
        sa.UniqueConstraint(
            "canonical_payload_hash", name="uq_verification_receipts_payload_hash"
        ),
    )
    op.create_index(
        "ix_verification_receipts_challenge_id", "verification_receipts", ["challenge_id"]
    )
    op.create_index(
        "ix_verification_receipts_installation_id",
        "verification_receipts",
        ["installation_id"],
    )
    op.create_index(
        "ix_verification_receipts_user_id", "verification_receipts", ["user_id"]
    )
    op.create_index(
        "ix_verification_receipts_candidate_id", "verification_receipts", ["candidate_id"]
    )
    op.create_index("ix_verification_receipts_outcome", "verification_receipts", ["outcome"])
    op.create_index(
        "ix_verification_receipts_canonical_payload_hash",
        "verification_receipts",
        ["canonical_payload_hash"],
    )


def downgrade() -> None:
    op.drop_table("verification_receipts")
    op.drop_table("verification_challenges")
    op.drop_table("client_installations")
