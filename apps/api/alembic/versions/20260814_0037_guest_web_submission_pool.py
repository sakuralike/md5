from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0037"
down_revision: str | None = "20260814_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("submissions") as batch_op:
        batch_op.alter_column(
            "user_id",
            existing_type=sa.String(36),
            nullable=True,
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM submissions WHERE user_id IS NULL"))
    with op.batch_alter_table("submissions") as batch_op:
        batch_op.alter_column(
            "user_id",
            existing_type=sa.String(36),
            nullable=False,
        )
