"""add backend-managed desktop update releases and artifacts

Revision ID: 20260802_0006
Revises: 20260802_0005
Create Date: 2026-08-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260802_0006"
down_revision = "20260802_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "desktop_releases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("architecture", sa.String(16), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("minimum_supported_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("release_notes", sa.Text(), nullable=False),
        sa.Column("artifact_filename", sa.String(255), nullable=False),
        sa.Column("artifact_storage_key", sa.String(128), nullable=True, unique=True),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("artifact_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("code_signature_status", sa.String(24), nullable=False),
        sa.Column("signer_subject", sa.String(255), nullable=True),
        sa.Column("signer_thumbprint", sa.String(128), nullable=True),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "channel",
            "platform",
            "architecture",
            "version",
            name="uq_desktop_releases_target_version",
        ),
    )
    op.create_index("ix_desktop_releases_channel", "desktop_releases", ["channel"])
    op.create_index("ix_desktop_releases_platform", "desktop_releases", ["platform"])
    op.create_index("ix_desktop_releases_architecture", "desktop_releases", ["architecture"])
    op.create_index("ix_desktop_releases_version", "desktop_releases", ["version"])
    op.create_index("ix_desktop_releases_status", "desktop_releases", ["status"])
    op.create_index("ix_desktop_releases_created_by", "desktop_releases", ["created_by"])
    op.create_index("ix_desktop_releases_published_at", "desktop_releases", ["published_at"])


def downgrade() -> None:
    # Dropping the table removes its indexes and foreign key together. MySQL rejects
    # dropping the created_by index first because InnoDB requires it for the FK.
    op.drop_table("desktop_releases")
