"""add privacy-minimized desktop plugin install events

Revision ID: 20260826_0060
Revises: 20260826_0059
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260826_0060"
down_revision: str | None = "20260826_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "desktop_plugin_install_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("plugin_slug", sa.String(128), nullable=False),
        sa.Column("semver", sa.String(32), nullable=False),
        sa.Column("architecture", sa.String(16), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "installed",
                "upgraded",
                "rolled_back",
                "enabled",
                "disabled",
                "uninstalled",
                "download_failed",
                name="desktopplugininstalleventkind",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("client_version", sa.String(32), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_desktop_plugin_install_events_event_id"),
    )
    op.create_index(
        "ix_desktop_plugin_install_events_plugin_created",
        "desktop_plugin_install_events",
        ["plugin_slug", "created_at"],
    )
    for column in ("plugin_slug", "kind", "user_id"):
        op.create_index(
            f"ix_desktop_plugin_install_events_{column}",
            "desktop_plugin_install_events",
            [column],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        inspector = sa.inspect(bind)
        for foreign_key in inspector.get_foreign_keys("desktop_plugin_install_events"):
            if foreign_key.get("constrained_columns") == ["user_id"] and foreign_key.get("name"):
                op.drop_constraint(
                    foreign_key["name"],
                    "desktop_plugin_install_events",
                    type_="foreignkey",
                )
    for column in ("user_id", "kind", "plugin_slug"):
        op.drop_index(
            f"ix_desktop_plugin_install_events_{column}",
            table_name="desktop_plugin_install_events",
        )
    op.drop_index(
        "ix_desktop_plugin_install_events_plugin_created",
        table_name="desktop_plugin_install_events",
    )
    op.drop_table("desktop_plugin_install_events")
