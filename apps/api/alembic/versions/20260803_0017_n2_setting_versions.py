"""add immutable system setting versions

Revision ID: 20260803_0017
Revises: 20260803_0016
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260803_0017"
down_revision = "20260803_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_setting_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False, server_default="operational-v1"),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("base_version_id", sa.String(36), nullable=True),
        sa.Column("rollback_of_id", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("published_by", sa.String(36), nullable=True),
        sa.Column("reason_code", sa.String(48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["base_version_id"], ["system_setting_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rollback_of_id"], ["system_setting_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"]),
    )
    op.create_index("ix_system_setting_versions_status", "system_setting_versions", ["status"])
    op.create_index("ix_system_setting_versions_snapshot_hash", "system_setting_versions", ["snapshot_hash"])
    op.create_index("ix_system_setting_versions_created_by", "system_setting_versions", ["created_by"])
    op.create_index("ix_system_setting_versions_status_created", "system_setting_versions", ["status", "created_at"])
    op.create_index("ix_system_setting_versions_published_at", "system_setting_versions", ["published_at"])


def downgrade() -> None:
    op.drop_table("system_setting_versions")
