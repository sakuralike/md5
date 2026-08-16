"""widen community search document versions

Revision ID: 20260816_0046
Revises: 20260816_0045
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260816_0046"
down_revision: str | None = "20260816_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SEARCH_DOCUMENT_VERSION_TABLES = (
    "community_search_documents",
    "community_search_outbox",
)


def upgrade() -> None:
    for table_name in _SEARCH_DOCUMENT_VERSION_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "document_version",
                existing_type=sa.Integer(),
                type_=sa.BigInteger(),
                existing_nullable=False,
            )


def downgrade() -> None:
    for table_name in _SEARCH_DOCUMENT_VERSION_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "document_version",
                existing_type=sa.BigInteger(),
                type_=sa.Integer(),
                existing_nullable=False,
            )
