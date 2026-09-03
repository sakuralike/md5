from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260815_0042"
down_revision: str | None = "20260815_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _create_index_if_missing(
    name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    profile_columns = _column_names("community_public_profiles")
    profile_indexes = _index_names("community_public_profiles")
    missing_profile_columns = {
        "avatar_kind",
        "avatar_url",
        "gravatar_enabled",
    } - profile_columns
    needs_avatar_index = "ix_community_public_profiles_avatar_kind" not in profile_indexes
    if missing_profile_columns or needs_avatar_index:
        with op.batch_alter_table("community_public_profiles") as batch_op:
            if "avatar_kind" in missing_profile_columns:
                batch_op.add_column(
                    sa.Column(
                        "avatar_kind",
                        sa.String(16),
                        nullable=False,
                        server_default="generated",
                    )
                )
            if "avatar_url" in missing_profile_columns:
                batch_op.add_column(sa.Column("avatar_url", sa.String(512), nullable=True))
            if "gravatar_enabled" in missing_profile_columns:
                batch_op.add_column(
                    sa.Column(
                        "gravatar_enabled",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.false(),
                    )
                )
            if needs_avatar_index:
                batch_op.create_index("ix_community_public_profiles_avatar_kind", ["avatar_kind"])

    if not _table_exists("third_party_application_requests"):
        op.create_table(
            "third_party_application_requests",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "submitted_by_user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("developer_name", sa.String(128), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("website_url", sa.String(2000), nullable=False),
            sa.Column("privacy_policy_url", sa.String(2000), nullable=False),
            sa.Column("redirect_uris_json", sa.Text(), nullable=False),
            sa.Column("requested_scopes_json", sa.Text(), nullable=False),
            sa.Column("windows_release_info", sa.Text(), nullable=False),
            sa.Column("use_case", sa.Text(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
            sa.Column("resubmission_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column(
                "reviewer_user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column(
                "approved_application_id",
                sa.String(36),
                sa.ForeignKey("third_party_apps.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    _create_index_if_missing(
        "ix_third_party_application_requests_submitted_by_user_id",
        "third_party_application_requests",
        ["submitted_by_user_id"],
    )
    _create_index_if_missing(
        "ix_third_party_application_requests_status",
        "third_party_application_requests",
        ["status"],
    )
    _create_index_if_missing(
        "ix_third_party_application_requests_reviewer_user_id",
        "third_party_application_requests",
        ["reviewer_user_id"],
    )
    _create_index_if_missing(
        "ix_third_party_application_requests_approved_application_id",
        "third_party_application_requests",
        ["approved_application_id"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_third_party_application_requests_status_created",
        "third_party_application_requests",
        ["status", "created_at"],
    )
    _create_index_if_missing(
        "ix_third_party_application_requests_submitter_status",
        "third_party_application_requests",
        ["submitted_by_user_id", "status"],
    )

    if not _table_exists("third_party_application_review_events"):
        op.create_table(
            "third_party_application_review_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "application_request_id",
                sa.String(36),
                sa.ForeignKey("third_party_application_requests.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "actor_user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("kind", sa.String(24), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    _create_index_if_missing(
        "ix_third_party_application_review_events_application_request_id",
        "third_party_application_review_events",
        ["application_request_id"],
    )
    _create_index_if_missing(
        "ix_third_party_application_review_events_actor_user_id",
        "third_party_application_review_events",
        ["actor_user_id"],
    )
    _create_index_if_missing(
        "ix_third_party_application_review_events_kind",
        "third_party_application_review_events",
        ["kind"],
    )
    _create_index_if_missing(
        "ix_third_party_application_review_events_request_created",
        "third_party_application_review_events",
        ["application_request_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("third_party_application_review_events")
    op.drop_table("third_party_application_requests")
    with op.batch_alter_table("community_public_profiles") as batch_op:
        batch_op.drop_index("ix_community_public_profiles_avatar_kind")
        batch_op.drop_column("gravatar_enabled")
        batch_op.drop_column("avatar_url")
        batch_op.drop_column("avatar_kind")
