"""add desktop plugin static review runs and findings

Revision ID: 20260826_0058
Revises: 20260825_0057
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260826_0058"
down_revision: str | None = "20260825_0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(*values: str, name: str, length: int) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=length)


def upgrade() -> None:
    op.create_table(
        "desktop_plugin_review_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column(
            "status",
            _enum(
                "queued",
                "running",
                "passed",
                "failed",
                "infrastructure_failed",
                "cancelled",
                name="desktoppluginreviewrunstatus",
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("evidence_storage_key", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["desktop_plugin_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_desktop_plugin_review_runs_version_created",
        "desktop_plugin_review_runs",
        ["version_id", "created_at"],
    )
    op.create_index(
        "ix_desktop_plugin_review_runs_status_lease",
        "desktop_plugin_review_runs",
        ["status", "lease_expires_at"],
    )

    op.create_table(
        "desktop_plugin_review_findings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("review_run_id", sa.String(36), nullable=False),
        sa.Column(
            "stage",
            _enum(
                "structure",
                "signature",
                "sbom",
                "vulnerability",
                "license",
                "secret",
                "static_behavior",
                "pe_analysis",
                "dynamic_protocol",
                "dynamic_resource",
                "dynamic_file",
                "dynamic_process",
                "dynamic_network",
                "dynamic_cleanup",
                name="desktoppluginreviewstage",
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column(
            "severity",
            _enum(
                "info",
                "low",
                "medium",
                "high",
                "critical",
                name="desktoppluginfindingseverity",
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("developer_visible", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["review_run_id"], ["desktop_plugin_review_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_desktop_plugin_review_findings_run_created",
        "desktop_plugin_review_findings",
        ["review_run_id", "created_at"],
    )
    op.create_index(
        "ix_desktop_plugin_review_findings_rule_severity",
        "desktop_plugin_review_findings",
        ["rule_id", "severity"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        inspector = sa.inspect(bind)
        for foreign_key in inspector.get_foreign_keys("desktop_plugin_review_findings"):
            if foreign_key.get("name"):
                op.drop_constraint(
                    foreign_key["name"],
                    "desktop_plugin_review_findings",
                    type_="foreignkey",
                )
    op.drop_index(
        "ix_desktop_plugin_review_findings_rule_severity",
        table_name="desktop_plugin_review_findings",
    )
    op.drop_index(
        "ix_desktop_plugin_review_findings_run_created",
        table_name="desktop_plugin_review_findings",
    )
    op.drop_table("desktop_plugin_review_findings")
    op.drop_index(
        "ix_desktop_plugin_review_runs_status_lease",
        table_name="desktop_plugin_review_runs",
    )
    op.drop_index(
        "ix_desktop_plugin_review_runs_version_created",
        table_name="desktop_plugin_review_runs",
    )
    op.drop_table("desktop_plugin_review_runs")
