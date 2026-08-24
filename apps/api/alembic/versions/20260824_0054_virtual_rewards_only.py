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
    constraints = (
        (
            "reward_catalog_items",
            "ck_reward_catalog_items_virtual_kind",
            "kind = 'VIRTUAL'",
        ),
        (
            "reward_order_items",
            "ck_reward_order_items_virtual_kind",
            "kind_snapshot = 'VIRTUAL'",
        ),
        (
            "reward_fulfillments",
            "ck_reward_fulfillments_internal_entitlement",
            "delivery_kind = 'INTERNAL_ENTITLEMENT'",
        ),
    )
    for table_name, constraint_name, condition in constraints:
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.create_check_constraint(constraint_name, condition)
        else:
            op.create_check_constraint(constraint_name, table_name, condition)


def downgrade() -> None:
    constraints = (
        ("reward_fulfillments", "ck_reward_fulfillments_internal_entitlement"),
        ("reward_order_items", "ck_reward_order_items_virtual_kind"),
        ("reward_catalog_items", "ck_reward_catalog_items_virtual_kind"),
    )
    for table_name, constraint_name in constraints:
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.drop_constraint(constraint_name, type_="check")
        else:
            op.drop_constraint(constraint_name, table_name, type_="check")
