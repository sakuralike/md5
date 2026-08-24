"""restrict reward persistence to virtual entitlements

Revision ID: 20260824_0054
Revises: 20260820_0053
Create Date: 2026-08-24
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260824_0054"
down_revision: str | None = "20260820_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_reward_catalog_items_virtual_kind",
        "reward_catalog_items",
        "kind = 'VIRTUAL'",
    )
    op.create_check_constraint(
        "ck_reward_order_items_virtual_kind",
        "reward_order_items",
        "kind_snapshot = 'VIRTUAL'",
    )
    op.create_check_constraint(
        "ck_reward_fulfillments_internal_entitlement",
        "reward_fulfillments",
        "delivery_kind = 'INTERNAL_ENTITLEMENT'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_reward_fulfillments_internal_entitlement",
        "reward_fulfillments",
        type_="check",
    )
    op.drop_constraint(
        "ck_reward_order_items_virtual_kind",
        "reward_order_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_reward_catalog_items_virtual_kind",
        "reward_catalog_items",
        type_="check",
    )
