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
    with op.batch_alter_table("desktop_plugin_download_tickets") as batch:
        batch.add_column(sa.Column("channel", sa.String(16), nullable=False, server_default="stable"))
        batch.add_column(sa.Column("user_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("installation_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_desktop_plugin_download_tickets_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_desktop_plugin_download_tickets_installation_id_client_installations",
            "client_installations",
            ["installation_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_desktop_plugin_download_tickets_user_id", ["user_id"])
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
            "fk_desktop_plugin_install_events_installation_id_client_installations",
            "client_installations",
            ["installation_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_desktop_plugin_install_events_installation_id", ["installation_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("desktop_plugin_install_events") as batch:
        batch.drop_index("ix_desktop_plugin_install_events_installation_id")
        batch.drop_constraint(
            "fk_desktop_plugin_install_events_installation_id_client_installations",
            type_="foreignkey",
        )
        batch.drop_column("evidence_signature")
        batch.drop_column("evidence_payload_hash")
        batch.drop_column("installation_id")
        batch.drop_column("migration_evidence_json")
        batch.drop_column("permission_evidence_json")
    with op.batch_alter_table("desktop_plugin_download_tickets") as batch:
        batch.drop_index("ix_desktop_plugin_download_tickets_installation_id")
        batch.drop_index("ix_desktop_plugin_download_tickets_user_id")
        batch.drop_constraint(
            "fk_desktop_plugin_download_tickets_installation_id_client_installations",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_desktop_plugin_download_tickets_user_id_users",
            type_="foreignkey",
        )
        batch.drop_column("installation_id")
        batch.drop_column("user_id")
        batch.drop_column("channel")
