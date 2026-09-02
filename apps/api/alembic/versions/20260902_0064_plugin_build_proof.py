"""add verified plugin build proof metadata

Revision ID: 20260902_0064
Revises: 20260828_0063
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260902_0064"
down_revision: str | None = "20260828_0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("desktop_plugin_versions")}
    with op.batch_alter_table("desktop_plugin_versions") as batch:
        if "build_proof_sha256" not in columns:
            batch.add_column(sa.Column("build_proof_sha256", sa.String(64), nullable=True))
        if "build_proof_git_commit" not in columns:
            batch.add_column(sa.Column("build_proof_git_commit", sa.String(64), nullable=True))
        if "build_proof_package_sha256" not in columns:
            batch.add_column(
                sa.Column("build_proof_package_sha256", sa.String(64), nullable=True)
            )
        if "build_proof_rebuild_sha256" not in columns:
            batch.add_column(
                sa.Column("build_proof_rebuild_sha256", sa.String(64), nullable=True)
            )
        if "build_proof_verified_at" not in columns:
            batch.add_column(
                sa.Column("build_proof_verified_at", sa.DateTime(timezone=True), nullable=True)
            )
    install_columns = {
        column["name"] for column in inspector.get_columns("desktop_plugin_install_events")
    }
    install_indexes = {
        index["name"] for index in inspector.get_indexes("desktop_plugin_install_events")
    }
    with op.batch_alter_table("desktop_plugin_install_events") as batch:
        if "migration_retry_status" not in install_columns:
            batch.add_column(sa.Column("migration_retry_status", sa.String(16), nullable=True))
        if "migration_retry_attempt" not in install_columns:
            batch.add_column(sa.Column("migration_retry_attempt", sa.Integer(), nullable=True))
        if "migration_retry_next_at" not in install_columns:
            batch.add_column(
                sa.Column("migration_retry_next_at", sa.DateTime(timezone=True), nullable=True)
            )
        if "migration_retry_available_at" not in install_columns:
            batch.add_column(
                sa.Column("migration_retry_available_at", sa.DateTime(timezone=True), nullable=True)
            )
        if "migration_retry_completed_at" not in install_columns:
            batch.add_column(
                sa.Column("migration_retry_completed_at", sa.DateTime(timezone=True), nullable=True)
            )
        if "ix_desktop_plugin_install_events_migration_retry" not in install_indexes:
            batch.create_index(
                "ix_desktop_plugin_install_events_migration_retry",
                ["migration_retry_status", "migration_retry_next_at"],
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    install_columns = {
        column["name"] for column in inspector.get_columns("desktop_plugin_install_events")
    }
    install_indexes = {
        index["name"] for index in inspector.get_indexes("desktop_plugin_install_events")
    }
    with op.batch_alter_table("desktop_plugin_install_events") as batch:
        if "ix_desktop_plugin_install_events_migration_retry" in install_indexes:
            batch.drop_index("ix_desktop_plugin_install_events_migration_retry")
        for column in (
            "migration_retry_completed_at",
            "migration_retry_available_at",
            "migration_retry_next_at",
            "migration_retry_attempt",
            "migration_retry_status",
        ):
            if column in install_columns:
                batch.drop_column(column)
    columns = {column["name"] for column in inspector.get_columns("desktop_plugin_versions")}
    with op.batch_alter_table("desktop_plugin_versions") as batch:
        for column in (
            "build_proof_verified_at",
            "build_proof_rebuild_sha256",
            "build_proof_package_sha256",
            "build_proof_git_commit",
            "build_proof_sha256",
        ):
            if column in columns:
                batch.drop_column(column)
