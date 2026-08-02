"""add M2 archive, fingerprint, candidate and contribution core

Revision ID: 20260802_0003
Revises: 20260801_0002
Create Date: 2026-08-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260802_0003"
down_revision = "20260801_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "archives",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("optional_size", sa.BigInteger(), nullable=True),
        sa.Column("optional_format", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_archives_created_by", "archives", ["created_by"])

    op.create_table(
        "archive_fingerprints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("archive_id", sa.String(36), nullable=False),
        sa.Column("algorithm", sa.String(16), nullable=False),
        sa.Column("digest", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["archive_id"], ["archives.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "algorithm", "digest", name="uq_archive_fingerprints_algorithm_digest"
        ),
    )
    op.create_index("ix_archive_fingerprints_archive_id", "archive_fingerprints", ["archive_id"])
    op.create_index("ix_archive_fingerprints_algorithm", "archive_fingerprints", ["algorithm"])
    op.create_index("ix_archive_fingerprints_digest", "archive_fingerprints", ["digest"])

    op.create_table(
        "password_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("archive_id", sa.String(36), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("secret_nonce", sa.String(64), nullable=False),
        sa.Column("secret_key_version", sa.String(32), nullable=False),
        sa.Column("secret_dedup_tag", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["archive_id"], ["archives.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "archive_id", "secret_dedup_tag", name="uq_password_candidates_archive_dedup"
        ),
    )
    op.create_index("ix_password_candidates_archive_id", "password_candidates", ["archive_id"])
    op.create_index(
        "ix_password_candidates_secret_dedup_tag", "password_candidates", ["secret_dedup_tag"]
    )
    op.create_index("ix_password_candidates_status", "password_candidates", ["status"])
    op.create_index(
        "ix_password_candidates_last_verified_at", "password_candidates", ["last_verified_at"]
    )
    op.create_index(
        "ix_candidates_archive_status_confidence",
        "password_candidates",
        ["archive_id", "status", "confidence_score"],
    )

    op.create_table(
        "submissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("authorization_version", sa.String(32), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("ip_prefix", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["password_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_submissions_candidate_id", "submissions", ["candidate_id"])
    op.create_index("ix_submissions_user_id", "submissions", ["user_id"])
    op.create_index(
        "ix_submissions_idempotency_key_hash", "submissions", ["idempotency_key_hash"]
    )
    op.create_index("ix_submissions_user_created", "submissions", ["user_id", "created_at"])

    op.create_table(
        "points_ledger",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("reference_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "event_type", "reference_id", name="uq_points_ledger_event_reference"
        ),
    )
    op.create_index("ix_points_ledger_user_id", "points_ledger", ["user_id"])
    op.create_index("ix_points_ledger_event_type", "points_ledger", ["event_type"])
    op.create_index("ix_points_ledger_reference_id", "points_ledger", ["reference_id"])
    op.create_index("ix_points_ledger_status", "points_ledger", ["status"])


def downgrade() -> None:
    op.drop_table("points_ledger")
    op.drop_table("submissions")
    op.drop_table("password_candidates")
    op.drop_table("archive_fingerprints")
    op.drop_table("archives")
