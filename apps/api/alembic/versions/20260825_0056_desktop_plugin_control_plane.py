"""add desktop plugin control plane and artifact storage records

Revision ID: 20260825_0056
Revises: 20260824_0055
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260825_0056"
down_revision: str | None = "20260824_0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(*values: str, name: str, length: int) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=length)


def upgrade() -> None:
    op.create_table(
        "desktop_plugins",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("owner_user_id", sa.String(36), nullable=False),
        sa.Column("linked_third_party_app_id", sa.String(36), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("summary", sa.String(320), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("website_url", sa.String(2000), nullable=True),
        sa.Column("privacy_policy_url", sa.String(2000), nullable=True),
        sa.Column("source_url", sa.String(2000), nullable=True),
        sa.Column(
            "status",
            _enum(
                "draft",
                "active",
                "suspended",
                "revoked",
                name="desktoppluginstatus",
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["linked_third_party_app_id"], ["third_party_apps.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_desktop_plugins_slug"),
    )
    op.create_index("ix_desktop_plugins_slug", "desktop_plugins", ["slug"])
    op.create_index(
        "ix_desktop_plugins_owner_status", "desktop_plugins", ["owner_user_id", "status"]
    )
    op.create_index(
        "ix_desktop_plugins_status_updated", "desktop_plugins", ["status", "updated_at"]
    )

    op.create_table(
        "desktop_plugin_signing_keys",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("owner_user_id", sa.String(36), nullable=False),
        sa.Column("rotated_from_id", sa.String(36), nullable=True),
        sa.Column("key_id", sa.String(128), nullable=False),
        sa.Column("public_key_base64", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "status",
            _enum(
                "active",
                "rotating",
                "revoked",
                name="desktoppluginsigningkeystatus",
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["rotated_from_id"], ["desktop_plugin_signing_keys.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_id", name="uq_desktop_plugin_signing_keys_key_id"),
        sa.UniqueConstraint("fingerprint", name="uq_desktop_plugin_signing_keys_fingerprint"),
    )
    op.create_index(
        "ix_desktop_plugin_signing_keys_owner_status",
        "desktop_plugin_signing_keys",
        ["owner_user_id", "status"],
    )

    op.create_table(
        "desktop_plugin_versions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("plugin_id", sa.String(36), nullable=False),
        sa.Column("semver", sa.String(32), nullable=False),
        sa.Column(
            "status",
            _enum(
                "draft",
                "uploading",
                "quarantined",
                "review_queued",
                "auto_review_running",
                "auto_review_failed",
                "manual_review_ready",
                "approved",
                "published",
                "yanked",
                "rejected",
                "revoked",
                name="desktoppluginversionstatus",
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("signing_key_id", sa.String(36), nullable=False),
        sa.Column("signing_key_fingerprint", sa.String(64), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=True),
        sa.Column("manifest_sha256", sa.String(64), nullable=True),
        sa.Column("protocol_min", sa.Integer(), nullable=False),
        sa.Column("protocol_max", sa.Integer(), nullable=False),
        sa.Column("host_min", sa.String(32), nullable=False),
        sa.Column("host_max", sa.String(32), nullable=False),
        sa.Column("requested_capabilities", sa.JSON(), nullable=False),
        sa.Column("approved_capabilities", sa.JSON(), nullable=False),
        sa.Column("risk_tier", sa.String(16), nullable=False),
        sa.Column("release_notes", sa.Text(), nullable=False),
        sa.Column("source_review_mode", sa.String(32), nullable=False),
        sa.Column("reviewer_user_id", sa.String(36), nullable=True),
        sa.Column("review_policy_version", sa.String(64), nullable=True),
        sa.Column("platform_key_id", sa.String(128), nullable=True),
        sa.Column("platform_signature_base64", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("yanked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["plugin_id"], ["desktop_plugins.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["signing_key_id"], ["desktop_plugin_signing_keys.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plugin_id", "semver", name="uq_desktop_plugin_versions_plugin_semver"),
    )
    op.create_index(
        "ix_desktop_plugin_versions_plugin_status",
        "desktop_plugin_versions",
        ["plugin_id", "status"],
    )
    op.create_index(
        "ix_desktop_plugin_versions_status_published",
        "desktop_plugin_versions",
        ["status", "published_at"],
    )

    op.create_table(
        "desktop_plugin_artifacts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("plugin_version_id", sa.String(36), nullable=False),
        sa.Column("architecture", sa.String(16), nullable=False),
        sa.Column("runtime", sa.String(32), nullable=False),
        sa.Column(
            "status",
            _enum(
                "uploading",
                "quarantined",
                "public",
                "yanked",
                "revoked",
                name="desktoppluginartifactstatus",
                length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            "zone",
            _enum(
                "quarantine",
                "public",
                "revoked",
                name="desktoppluginartifactzone",
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("public_storage_key", sa.String(512), nullable=True),
        sa.Column("artifact_filename", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("expanded_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("developer_signature_base64", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["plugin_version_id"], ["desktop_plugin_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plugin_version_id",
            "architecture",
            name="uq_desktop_plugin_artifacts_version_arch",
        ),
    )
    op.create_index(
        "ix_desktop_plugin_artifacts_status_zone",
        "desktop_plugin_artifacts",
        ["status", "zone"],
    )

    op.create_table(
        "desktop_plugin_upload_sessions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("plugin_version_id", sa.String(36), nullable=False),
        sa.Column("artifact_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expected_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("expected_sha256", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            _enum(
                "open",
                "uploaded",
                "finalized",
                "expired",
                "aborted",
                name="desktoppluginuploadsessionstatus",
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["plugin_version_id"], ["desktop_plugin_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["desktop_plugin_artifacts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_desktop_plugin_upload_sessions_token_hash"),
    )
    op.create_index(
        "ix_desktop_plugin_upload_sessions_version_status",
        "desktop_plugin_upload_sessions",
        ["plugin_version_id", "status"],
    )
    op.create_index(
        "ix_desktop_plugin_upload_sessions_expires_status",
        "desktop_plugin_upload_sessions",
        ["expires_at", "status"],
    )

    op.create_table(
        "desktop_plugin_download_tickets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("artifact_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["desktop_plugin_artifacts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_desktop_plugin_download_tickets_token_hash"),
    )
    op.create_index(
        "ix_desktop_plugin_download_tickets_expires",
        "desktop_plugin_download_tickets",
        ["expires_at"],
    )

    op.create_table(
        "desktop_plugin_revocations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column(
            "scope",
            _enum(
                "plugin",
                "version",
                "signing_key",
                name="desktoppluginrevocationscope",
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("plugin_id", sa.String(36), nullable=True),
        sa.Column("plugin_version_id", sa.String(36), nullable=True),
        sa.Column("signing_key_id", sa.String(36), nullable=True),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("affects_historical_versions", sa.Boolean(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("batch_id", sa.String(64), nullable=False),
        sa.Column("platform_key_id", sa.String(128), nullable=False),
        sa.Column("platform_signature_base64", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(plugin_id IS NOT NULL AND plugin_version_id IS NULL AND signing_key_id IS NULL) OR "
            "(plugin_id IS NULL AND plugin_version_id IS NOT NULL AND signing_key_id IS NULL) OR "
            "(plugin_id IS NULL AND plugin_version_id IS NULL AND signing_key_id IS NOT NULL)",
            name="ck_desktop_plugin_revocations_single_target",
        ),
        sa.ForeignKeyConstraint(["plugin_id"], ["desktop_plugins.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["plugin_version_id"], ["desktop_plugin_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["signing_key_id"], ["desktop_plugin_signing_keys.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_desktop_plugin_revocations_effective",
        "desktop_plugin_revocations",
        ["effective_at", "created_at"],
    )
    op.create_index(
        "ix_desktop_plugin_revocations_scope_effective",
        "desktop_plugin_revocations",
        ["scope", "effective_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_desktop_plugin_revocations_scope_effective",
        table_name="desktop_plugin_revocations",
    )
    op.drop_index(
        "ix_desktop_plugin_revocations_effective", table_name="desktop_plugin_revocations"
    )
    op.drop_table("desktop_plugin_revocations")
    op.drop_index(
        "ix_desktop_plugin_download_tickets_expires",
        table_name="desktop_plugin_download_tickets",
    )
    op.drop_table("desktop_plugin_download_tickets")
    op.drop_index(
        "ix_desktop_plugin_upload_sessions_expires_status",
        table_name="desktop_plugin_upload_sessions",
    )
    op.drop_index(
        "ix_desktop_plugin_upload_sessions_version_status",
        table_name="desktop_plugin_upload_sessions",
    )
    op.drop_table("desktop_plugin_upload_sessions")
    op.drop_index("ix_desktop_plugin_artifacts_status_zone", table_name="desktop_plugin_artifacts")
    op.drop_table("desktop_plugin_artifacts")
    op.drop_index(
        "ix_desktop_plugin_versions_status_published", table_name="desktop_plugin_versions"
    )
    op.drop_index("ix_desktop_plugin_versions_plugin_status", table_name="desktop_plugin_versions")
    op.drop_table("desktop_plugin_versions")
    op.drop_index(
        "ix_desktop_plugin_signing_keys_owner_status",
        table_name="desktop_plugin_signing_keys",
    )
    op.drop_table("desktop_plugin_signing_keys")
    op.drop_index("ix_desktop_plugins_status_updated", table_name="desktop_plugins")
    op.drop_index("ix_desktop_plugins_owner_status", table_name="desktop_plugins")
    op.drop_index("ix_desktop_plugins_slug", table_name="desktop_plugins")
    op.drop_table("desktop_plugins")
