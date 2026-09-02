"""add privacy-minimized plugin upgrade evidence

Revision ID: 20260828_0063
Revises: 20260827_0062
Create Date: 2026-08-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260828_0063"
down_revision: str | None = "20260827_0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("desktop_plugin_download_tickets")}
    foreign_keys = {
        constraint.get("name")
        for constraint in inspector.get_foreign_keys("desktop_plugin_download_tickets")
    }
    indexes = {index["name"] for index in inspector.get_indexes("desktop_plugin_download_tickets")}
    with op.batch_alter_table("desktop_plugin_download_tickets") as batch:
        if "channel" not in columns:
            batch.add_column(
                sa.Column("channel", sa.String(16), nullable=False, server_default="stable")
            )
        if "user_id" not in columns:
            batch.add_column(sa.Column("user_id", sa.String(36), nullable=True))
        if "installation_id" not in columns:
            batch.add_column(sa.Column("installation_id", sa.String(36), nullable=True))
        if "fk_dpdt_user" not in foreign_keys:
            batch.create_foreign_key(
                "fk_dpdt_user",
                "users",
                ["user_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if "fk_dpdt_installation" not in foreign_keys:
            batch.create_foreign_key(
                "fk_dpdt_installation",
                "client_installations",
                ["installation_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if "ix_desktop_plugin_download_tickets_user_id" not in indexes:
            batch.create_index("ix_desktop_plugin_download_tickets_user_id", ["user_id"])
        if "ix_desktop_plugin_download_tickets_installation_id" not in indexes:
            batch.create_index(
                "ix_desktop_plugin_download_tickets_installation_id", ["installation_id"]
            )
    with op.batch_alter_table("desktop_plugin_install_events") as batch:
        batch.add_column(sa.Column("permission_evidence_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("migration_evidence_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("installation_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("evidence_payload_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("evidence_signature", sa.Text(), nullable=True))
        batch.create_foreign_key(
            "fk_dpie_installation",
            "client_installations",
            ["installation_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_desktop_plugin_install_events_installation_id", ["installation_id"]
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("desktop_plugin_download_tickets")}
    foreign_keys = {
        constraint.get("name")
        for constraint in inspector.get_foreign_keys("desktop_plugin_download_tickets")
    }
    indexes = {index["name"] for index in inspector.get_indexes("desktop_plugin_download_tickets")}
    with op.batch_alter_table("desktop_plugin_install_events") as batch:
        batch.drop_constraint(
            "fk_dpie_installation",
            type_="foreignkey",
        )
        batch.drop_index("ix_desktop_plugin_install_events_installation_id")
        batch.drop_column("evidence_signature")
        batch.drop_column("evidence_payload_hash")
        batch.drop_column("installation_id")
        batch.drop_column("migration_evidence_json")
        batch.drop_column("permission_evidence_json")
    with op.batch_alter_table("desktop_plugin_download_tickets") as batch:
        if "ix_desktop_plugin_download_tickets_installation_id" in indexes:
            batch.drop_index("ix_desktop_plugin_download_tickets_installation_id")
        if "ix_desktop_plugin_download_tickets_user_id" in indexes:
            batch.drop_index("ix_desktop_plugin_download_tickets_user_id")
        if "fk_dpdt_installation" in foreign_keys:
            batch.drop_constraint("fk_dpdt_installation", type_="foreignkey")
        if "fk_dpdt_user" in foreign_keys:
            batch.drop_constraint("fk_dpdt_user", type_="foreignkey")
        if "installation_id" in columns:
            batch.drop_column("installation_id")
        if "user_id" in columns:
            batch.drop_column("user_id")
        if "channel" in columns:
            batch.drop_column("channel")
