"""add reward orders fulfillment and operations

Revision ID: 20260820_0052
Revises: 20260820_0051
Create Date: 2026-08-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260820_0052"
down_revision: str | None = "20260820_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reward_catalog_items", sa.Column("category", sa.String(64), nullable=True))
    op.add_column("reward_catalog_items", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column("reward_catalog_items", sa.Column("sort_weight", sa.Integer(), nullable=True))
    op.add_column(
        "reward_catalog_items", sa.Column("entitlement_key", sa.String(64), nullable=True)
    )
    op.add_column(
        "reward_catalog_items", sa.Column("entitlement_duration_days", sa.Integer(), nullable=True)
    )
    op.add_column(
        "reward_catalog_items",
        sa.Column("redeem_start_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reward_catalog_items",
        sa.Column("redeem_end_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE reward_catalog_items SET category = 'general', tags = '[]', "
            "sort_weight = 0, entitlement_key = 'community_supporter'"
        )
    )
    op.alter_column("reward_catalog_items", "category", existing_type=sa.String(64), nullable=False)
    op.alter_column("reward_catalog_items", "tags", existing_type=sa.JSON(), nullable=False)
    op.alter_column(
        "reward_catalog_items", "sort_weight", existing_type=sa.Integer(), nullable=False
    )
    op.alter_column(
        "reward_catalog_items",
        "entitlement_key",
        existing_type=sa.String(64),
        nullable=False,
    )
    op.create_index("ix_reward_catalog_items_category", "reward_catalog_items", ["category"])
    op.create_index("ix_reward_catalog_items_sort_weight", "reward_catalog_items", ["sort_weight"])
    op.create_index(
        "ix_reward_catalog_items_redeem_start", "reward_catalog_items", ["redeem_start_at"]
    )
    op.create_index("ix_reward_catalog_items_redeem_end", "reward_catalog_items", ["redeem_end_at"])

    order_status = sa.Enum(
        "PENDING_FULFILLMENT",
        "PROCESSING",
        "FULFILLED",
        "FAILED",
        "CANCELLED",
        name="rewardorderstatus",
        native_enum=False,
        length=32,
    )
    actor_type = sa.Enum(
        "USER", "ADMIN", "SYSTEM", name="rewardactortype", native_enum=False, length=16
    )
    op.create_table(
        "reward_orders",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("order_no", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("status", order_status, nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_cost_points", sa.Integer(), nullable=False),
        sa.Column("total_cost_points", sa.Integer(), nullable=False),
        sa.Column("catalog_item_id", sa.String(36), nullable=False),
        sa.Column("catalog_version", sa.Integer(), nullable=False),
        sa.Column("item_slug_snapshot", sa.String(64), nullable=False),
        sa.Column("item_name_snapshot", sa.String(100), nullable=False),
        sa.Column("entitlement_key_snapshot", sa.String(64), nullable=False),
        sa.Column("entitlement_duration_days_snapshot", sa.Integer(), nullable=True),
        sa.Column("points_ledger_entry_id", sa.String(36), nullable=False),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("compensation_ledger_entry_id", sa.String(36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("compensated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["catalog_item_id"], ["reward_catalog_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["compensation_ledger_entry_id"], ["points_ledger.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["points_ledger_entry_id"], ["points_ledger.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("compensation_ledger_entry_id"),
        sa.UniqueConstraint("order_no", name="uq_reward_orders_order_no"),
        sa.UniqueConstraint("points_ledger_entry_id"),
    )
    op.create_index("ix_reward_orders_order_no", "reward_orders", ["order_no"])
    op.create_index("ix_reward_orders_user_id", "reward_orders", ["user_id"])
    op.create_index("ix_reward_orders_status", "reward_orders", ["status"])
    op.create_index("ix_reward_orders_catalog_item_id", "reward_orders", ["catalog_item_id"])

    op.create_table(
        "reward_order_items",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("order_id", sa.String(36), nullable=False),
        sa.Column("catalog_item_id", sa.String(36), nullable=False),
        sa.Column("item_slug_snapshot", sa.String(64), nullable=False),
        sa.Column("item_name_snapshot", sa.String(100), nullable=False),
        sa.Column(
            "kind_snapshot",
            sa.Enum("VIRTUAL", name="rewardcatalogkind", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_cost_points", sa.Integer(), nullable=False),
        sa.Column("total_cost_points", sa.Integer(), nullable=False),
        sa.Column("catalog_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["catalog_item_id"], ["reward_catalog_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["order_id"], ["reward_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reward_order_items_order_id", "reward_order_items", ["order_id"])
    op.create_index("ix_reward_order_items_catalog", "reward_order_items", ["catalog_item_id"])

    op.create_table(
        "reward_inventory_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("catalog_item_id", sa.String(36), nullable=False),
        sa.Column("order_id", sa.String(36), nullable=True),
        sa.Column(
            "event_type",
            sa.Enum(
                "REDEEMED",
                "RELEASED",
                "ADMIN_ADJUSTED",
                name="rewardinventoryeventtype",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("stock_before", sa.Integer(), nullable=False),
        sa.Column("stock_after", sa.Integer(), nullable=False),
        sa.Column("actor_type", actor_type, nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("reference_key", sa.String(100), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["catalog_item_id"], ["reward_catalog_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["order_id"], ["reward_orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_type", "reference_key", name="uq_reward_inventory_event_ref"),
    )
    op.create_index("ix_reward_inventory_catalog", "reward_inventory_events", ["catalog_item_id"])
    op.create_index("ix_reward_inventory_order", "reward_inventory_events", ["order_id"])
    op.create_index("ix_reward_inventory_event_type", "reward_inventory_events", ["event_type"])
    op.create_index("ix_reward_inventory_actor", "reward_inventory_events", ["actor_id"])
    op.create_index("ix_reward_inventory_created", "reward_inventory_events", ["created_at"])

    op.create_table(
        "reward_order_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("order_id", sa.String(36), nullable=False),
        sa.Column("from_status", order_status, nullable=True),
        sa.Column("to_status", order_status, nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_type", actor_type, nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["reward_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reward_order_events_order", "reward_order_events", ["order_id"])
    op.create_index("ix_reward_order_events_to_status", "reward_order_events", ["to_status"])
    op.create_index("ix_reward_order_events_type", "reward_order_events", ["event_type"])
    op.create_index("ix_reward_order_events_created", "reward_order_events", ["created_at"])

    op.create_table(
        "reward_fulfillments",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("order_id", sa.String(36), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column(
            "delivery_kind",
            sa.Enum(
                "INTERNAL_ENTITLEMENT",
                name="rewarddeliverykind",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "RUNNING",
                "SUCCEEDED",
                "RETRYABLE",
                "FAILED",
                "CANCELLED",
                name="rewardfulfillmentstatus",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("result_code", sa.String(128), nullable=True),
        sa.Column("safe_message", sa.String(300), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["reward_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "attempt_no", name="uq_reward_fulfillment_attempt"),
    )
    op.create_index("ix_reward_fulfillments_order", "reward_fulfillments", ["order_id"])
    op.create_index("ix_reward_fulfillments_status", "reward_fulfillments", ["status"])
    op.create_index("ix_reward_fulfillments_retry", "reward_fulfillments", ["next_retry_at"])

    op.create_table(
        "reward_entitlement_grants",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("order_id", sa.String(36), nullable=False),
        sa.Column("entitlement_key", sa.String(64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "REVOKED",
                "FAILED",
                name="rewardentitlementstatus",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["reward_orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "entitlement_key", name="uq_reward_entitlement_order_key"),
    )
    op.create_index("ix_reward_grants_user", "reward_entitlement_grants", ["user_id"])
    op.create_index("ix_reward_grants_order", "reward_entitlement_grants", ["order_id"])
    op.create_index("ix_reward_grants_key", "reward_entitlement_grants", ["entitlement_key"])
    op.create_index("ix_reward_grants_status", "reward_entitlement_grants", ["status"])


def downgrade() -> None:
    op.drop_table("reward_entitlement_grants")
    op.drop_table("reward_fulfillments")
    op.drop_table("reward_order_events")
    op.drop_table("reward_inventory_events")
    op.drop_table("reward_order_items")
    op.drop_table("reward_orders")
    op.drop_index("ix_reward_catalog_items_redeem_end", table_name="reward_catalog_items")
    op.drop_index("ix_reward_catalog_items_redeem_start", table_name="reward_catalog_items")
    op.drop_index("ix_reward_catalog_items_sort_weight", table_name="reward_catalog_items")
    op.drop_index("ix_reward_catalog_items_category", table_name="reward_catalog_items")
    op.drop_column("reward_catalog_items", "redeem_end_at")
    op.drop_column("reward_catalog_items", "redeem_start_at")
    op.drop_column("reward_catalog_items", "entitlement_duration_days")
    op.drop_column("reward_catalog_items", "entitlement_key")
    op.drop_column("reward_catalog_items", "sort_weight")
    op.drop_column("reward_catalog_items", "tags")
    op.drop_column("reward_catalog_items", "category")
