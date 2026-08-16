from __future__ import annotations

from collections.abc import Sequence

revision: str = "20260816_0043"
down_revision: tuple[str, str] = ("20260815_0042", "20260816_0042")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
