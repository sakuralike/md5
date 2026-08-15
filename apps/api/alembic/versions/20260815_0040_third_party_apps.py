from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260815_0040"
down_revision: str | None = "20260814_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "third_party_apps",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("management_secret_hash", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("developer_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("application_source", sa.String(32), nullable=False, server_default="admin"),
        sa.Column("requested_scopes_json", sa.Text(), nullable=False),
        sa.Column("approved_scopes_json", sa.Text(), nullable=False),
        sa.Column("submitted_by_user_id", sa.String(36), nullable=True),
        sa.Column("reviewer_user_id", sa.String(36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column(
            "trusted_verification_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", name="uq_third_party_apps_client_id"),
    )
    op.create_index(
        "ix_third_party_apps_client_id", "third_party_apps", ["client_id"], unique=False
    )
    op.create_index("ix_third_party_apps_status", "third_party_apps", ["status"], unique=False)
    op.create_index(
        "ix_third_party_apps_application_source",
        "third_party_apps",
        ["application_source"],
        unique=False,
    )
    op.create_index(
        "ix_third_party_apps_submitted_by_user_id",
        "third_party_apps",
        ["submitted_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_third_party_apps_reviewer_user_id",
        "third_party_apps",
        ["reviewer_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_third_party_apps_trusted_verification_enabled",
        "third_party_apps",
        ["trusted_verification_enabled"],
        unique=False,
    )
    op.create_index(
        "ix_third_party_apps_status_created",
        "third_party_apps",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_third_party_apps_submitted_by_status",
        "third_party_apps",
        ["submitted_by_user_id", "status"],
        unique=False,
    )

    op.create_table(
        "third_party_app_redirect_uris",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("app_id", sa.String(36), nullable=False),
        sa.Column("redirect_uri", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["app_id"], ["third_party_apps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_id", "redirect_uri", name="uq_third_party_app_redirect_uri"),
    )
    op.create_index(
        "ix_third_party_app_redirect_uris_app_id",
        "third_party_app_redirect_uris",
        ["app_id"],
        unique=False,
    )

    op.create_table(
        "third_party_authorizations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("app_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("scope_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["app_id"], ["third_party_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_id", "user_id", name="uq_third_party_authorization_app_user"),
    )
    op.create_index(
        "ix_third_party_authorizations_user_id",
        "third_party_authorizations",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "third_party_authorization_codes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("app_id", sa.String(36), nullable=False),
        sa.Column("authorization_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("redirect_uri", sa.String(2000), nullable=False),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("code_challenge_method", sa.String(8), nullable=False, server_default="S256"),
        sa.Column("scope_json", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["app_id"], ["third_party_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["authorization_id"], ["third_party_authorizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash", name="uq_third_party_authorization_codes_code_hash"),
    )
    op.create_index(
        "ix_third_party_authorization_codes_app_id",
        "third_party_authorization_codes",
        ["app_id"],
        unique=False,
    )
    op.create_index(
        "ix_third_party_authorization_codes_expires_at",
        "third_party_authorization_codes",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_third_party_authorization_codes_code_hash",
        "third_party_authorization_codes",
        ["code_hash"],
        unique=False,
    )

    op.create_table(
        "third_party_token_sessions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("app_id", sa.String(36), nullable=False),
        sa.Column("authorization_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("token_family_id", sa.String(36), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False),
        sa.Column("scope_json", sa.Text(), nullable=False),
        sa.Column("refresh_issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["app_id"], ["third_party_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["authorization_id"], ["third_party_authorizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "refresh_token_hash", name="uq_third_party_token_sessions_refresh_token_hash"
        ),
    )
    op.create_index(
        "ix_third_party_token_sessions_app_id",
        "third_party_token_sessions",
        ["app_id"],
        unique=False,
    )
    op.create_index(
        "ix_third_party_token_sessions_user_id",
        "third_party_token_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_third_party_token_sessions_family_id",
        "third_party_token_sessions",
        ["token_family_id"],
        unique=False,
    )
    op.create_index(
        "ix_third_party_token_sessions_refresh_token_hash",
        "third_party_token_sessions",
        ["refresh_token_hash"],
        unique=False,
    )


def downgrade() -> None:
    for index_name, table_name in (
        ("ix_third_party_token_sessions_refresh_token_hash", "third_party_token_sessions"),
        ("ix_third_party_token_sessions_family_id", "third_party_token_sessions"),
        ("ix_third_party_token_sessions_user_id", "third_party_token_sessions"),
        ("ix_third_party_token_sessions_app_id", "third_party_token_sessions"),
    ):
        op.drop_index(index_name, table_name=table_name)
    op.drop_table("third_party_token_sessions")

    for index_name, table_name in (
        ("ix_third_party_authorization_codes_code_hash", "third_party_authorization_codes"),
        ("ix_third_party_authorization_codes_expires_at", "third_party_authorization_codes"),
        ("ix_third_party_authorization_codes_app_id", "third_party_authorization_codes"),
    ):
        op.drop_index(index_name, table_name=table_name)
    op.drop_table("third_party_authorization_codes")

    op.drop_index("ix_third_party_authorizations_user_id", table_name="third_party_authorizations")
    op.drop_table("third_party_authorizations")

    op.drop_index(
        "ix_third_party_app_redirect_uris_app_id", table_name="third_party_app_redirect_uris"
    )
    op.drop_table("third_party_app_redirect_uris")

    for index_name in (
        "ix_third_party_apps_submitted_by_status",
        "ix_third_party_apps_status_created",
        "ix_third_party_apps_trusted_verification_enabled",
        "ix_third_party_apps_reviewer_user_id",
        "ix_third_party_apps_submitted_by_user_id",
        "ix_third_party_apps_application_source",
        "ix_third_party_apps_status",
        "ix_third_party_apps_client_id",
    ):
        op.drop_index(index_name, table_name="third_party_apps")
    op.drop_table("third_party_apps")
