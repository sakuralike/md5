"""add desktop plugin dynamic review runners and tasks

Revision ID: 20260826_0059
Revises: 20260826_0058
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260826_0059"
down_revision: str | None = "20260826_0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(*values: str, name: str, length: int) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=length)


def upgrade() -> None:
    op.create_table(
        "desktop_plugin_runner_agents",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("architecture", sa.String(16), nullable=False),
        sa.Column("certificate_fingerprint", sa.String(64), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False),
        sa.Column(
            "status",
            _enum(
                "ready",
                "busy",
                "offline",
                "revoked",
                name="desktoppluginrunnerstatus",
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("policy_version", sa.String(64), nullable=True),
        sa.Column("image_digest", sa.String(64), nullable=True),
        sa.Column("probe_version", sa.String(64), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "certificate_fingerprint", name="uq_desktop_plugin_runner_certificate"
        ),
    )
    op.create_index(
        "ix_desktop_plugin_runner_status_heartbeat",
        "desktop_plugin_runner_agents",
        ["status", "last_heartbeat_at"],
    )
    op.create_index(
        "ix_desktop_plugin_runner_agents_architecture",
        "desktop_plugin_runner_agents",
        ["architecture"],
    )
    op.create_index(
        "ix_desktop_plugin_runner_agents_created_by_user_id",
        "desktop_plugin_runner_agents",
        ["created_by_user_id"],
    )

    op.create_table(
        "desktop_plugin_dynamic_review_tasks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("review_run_id", sa.String(36), nullable=False),
        sa.Column("artifact_id", sa.String(36), nullable=False),
        sa.Column(
            "status",
            _enum(
                "queued",
                "leased",
                "passed",
                "blocked",
                "infrastructure_failed",
                "cancelled",
                name="desktopplugindynamictaskstatus",
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("runner_id", sa.String(36), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_token_hash", sa.String(64), nullable=True),
        sa.Column("task_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_summary_json", sa.JSON(), nullable=False),
        sa.Column("evidence_complete", sa.Boolean(), nullable=False),
        sa.Column("fresh_environment", sa.Boolean(), nullable=False),
        sa.Column("destruction_proof_sha256", sa.String(64), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["review_run_id"], ["desktop_plugin_review_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["desktop_plugin_artifacts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["runner_id"], ["desktop_plugin_runner_agents.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "review_run_id", "artifact_id", name="uq_desktop_plugin_dynamic_task_run_artifact"
        ),
    )
    op.create_index(
        "ix_desktop_plugin_dynamic_task_status_lease",
        "desktop_plugin_dynamic_review_tasks",
        ["status", "lease_expires_at"],
    )
    for column in ("review_run_id", "artifact_id", "runner_id"):
        op.create_index(
            f"ix_desktop_plugin_dynamic_review_tasks_{column}",
            "desktop_plugin_dynamic_review_tasks",
            [column],
        )
    with op.batch_alter_table("desktop_plugin_review_findings") as batch_op:
        batch_op.add_column(sa.Column("dynamic_task_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_desktop_plugin_review_findings_dynamic_task",
            "desktop_plugin_dynamic_review_tasks",
            ["dynamic_task_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index(
            "ix_desktop_plugin_review_findings_dynamic_task_id",
            ["dynamic_task_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("desktop_plugin_review_findings") as batch_op:
        batch_op.drop_index("ix_desktop_plugin_review_findings_dynamic_task_id")
        batch_op.drop_constraint(
            "fk_desktop_plugin_review_findings_dynamic_task",
            type_="foreignkey",
        )
        batch_op.drop_column("dynamic_task_id")
    for column in ("runner_id", "artifact_id", "review_run_id"):
        op.drop_index(
            f"ix_desktop_plugin_dynamic_review_tasks_{column}",
            table_name="desktop_plugin_dynamic_review_tasks",
        )
    op.drop_index(
        "ix_desktop_plugin_dynamic_task_status_lease",
        table_name="desktop_plugin_dynamic_review_tasks",
    )
    op.drop_table("desktop_plugin_dynamic_review_tasks")
    op.drop_index(
        "ix_desktop_plugin_runner_agents_created_by_user_id",
        table_name="desktop_plugin_runner_agents",
    )
    op.drop_index(
        "ix_desktop_plugin_runner_agents_architecture",
        table_name="desktop_plugin_runner_agents",
    )
    op.drop_index(
        "ix_desktop_plugin_runner_status_heartbeat",
        table_name="desktop_plugin_runner_agents",
    )
    op.drop_table("desktop_plugin_runner_agents")
