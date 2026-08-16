from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260816_0042"
down_revision: str | None = "20260815_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_search_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("board_code", sa.String(32), nullable=True),
        sa.Column("group_slug", sa.String(48), nullable=True),
        sa.Column("author_id", sa.String(36), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_type", "source_id", name="uq_community_search_document_source"),
    )
    op.create_index(
        "ix_community_search_documents_is_public_updated",
        "community_search_documents",
        ["is_public", "source_updated_at"],
    )
    op.create_index(
        "ix_community_search_documents_username",
        "community_search_documents",
        ["username"],
    )

    op.create_table(
        "community_search_outbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dedupe_key", name="uq_community_search_outbox_dedupe"),
    )
    op.create_index(
        "ix_community_search_outbox_status_available_at",
        "community_search_outbox",
        ["status", "available_at"],
    )
    op.create_index(
        "ix_community_search_outbox_source",
        "community_search_outbox",
        ["source_type", "source_id"],
    )

    op.create_table(
        "community_search_rebuild_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("cursor", sa.String(512), nullable=True),
        sa.Column("expected_count", sa.Integer(), nullable=False),
        sa.Column("indexed_count", sa.Integer(), nullable=False),
        sa.Column("missing_count", sa.Integer(), nullable=False),
        sa.Column("extra_count", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.String(256), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_community_search_rebuild_runs_status_created_at",
        "community_search_rebuild_runs",
        ["status", "created_at"],
    )

    if op.get_bind().dialect.name == "mysql":
        op.execute(
            "ALTER TABLE community_search_documents "
            "ADD FULLTEXT INDEX ix_community_search_documents_fulltext "
            "(title, body) WITH PARSER ngram"
        )
    else:
        op.create_index(
            "ix_community_search_documents_title",
            "community_search_documents",
            ["title"],
        )


def downgrade() -> None:
    op.drop_table("community_search_rebuild_runs")
    op.drop_table("community_search_outbox")
    op.drop_table("community_search_documents")
