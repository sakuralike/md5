"""add desktop plugin manual review, publication and report records

Revision ID: 20260825_0057
Revises: 20260825_0056
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260825_0057"
down_revision: str | None = "20260825_0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(*values: str, name: str, length: int) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=length)


def upgrade() -> None:
    op.add_column(
        "desktop_plugin_versions",
        sa.Column("platform_public_key_base64", sa.String(128), nullable=True),
    )
    op.add_column(
        "desktop_plugin_revocations",
        sa.Column("platform_public_key_base64", sa.String(128), nullable=True),
    )
    op.create_table(
        "desktop_plugin_review_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column(
            "kind",
            _enum(
                "submitted",
                "approved",
                "rejected",
                "published",
                "yanked",
                "revoked",
                name="desktoppluginrevieweventkind",
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("requested_capabilities", sa.JSON(), nullable=False),
        sa.Column("approved_capabilities", sa.JSON(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["desktop_plugin_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_desktop_plugin_review_events_version_created",
        "desktop_plugin_review_events",
        ["version_id", "created_at"],
    )
    op.create_index(
        "ix_desktop_plugin_review_events_kind_created",
        "desktop_plugin_review_events",
        ["kind", "created_at"],
    )

    op.create_table(
        "desktop_plugin_publications",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column(
            "status",
            _enum("published", "yanked", name="desktoppluginpublicationstatus", length=16),
            nullable=False,
        ),
        sa.Column("published_by_user_id", sa.String(36), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("yanked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("yanked_by_user_id", sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(["version_id"], ["desktop_plugin_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["yanked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version_id", "channel", name="uq_desktop_plugin_publications_version_channel"
        ),
    )
    op.create_index(
        "ix_desktop_plugin_publications_channel_status",
        "desktop_plugin_publications",
        ["channel", "status"],
    )

    op.create_table(
        "desktop_plugin_reports",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("plugin_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=True),
        sa.Column("reporter_user_id", sa.String(36), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            _enum(
                "open",
                "acknowledged",
                "resolved",
                "dismissed",
                name="desktoppluginreportstatus",
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("reviewer_user_id", sa.String(36), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plugin_id"], ["desktop_plugins.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["version_id"], ["desktop_plugin_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["reporter_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_desktop_plugin_reports_status_created",
        "desktop_plugin_reports",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_desktop_plugin_reports_plugin_status",
        "desktop_plugin_reports",
        ["plugin_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_desktop_plugin_reports_plugin_status", table_name="desktop_plugin_reports")
    op.drop_index("ix_desktop_plugin_reports_status_created", table_name="desktop_plugin_reports")
    op.drop_table("desktop_plugin_reports")
    op.drop_index(
        "ix_desktop_plugin_publications_channel_status", table_name="desktop_plugin_publications"
    )
    op.drop_table("desktop_plugin_publications")
    op.drop_index(
        "ix_desktop_plugin_review_events_kind_created", table_name="desktop_plugin_review_events"
    )
    op.drop_index(
        "ix_desktop_plugin_review_events_version_created", table_name="desktop_plugin_review_events"
    )
    op.drop_table("desktop_plugin_review_events")
    op.drop_column("desktop_plugin_revocations", "platform_public_key_base64")
    op.drop_column("desktop_plugin_versions", "platform_public_key_base64")
