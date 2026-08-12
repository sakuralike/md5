"""add configurable community boards and governed groups

Revision ID: 20260812_0032
Revises: 20260812_0031
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0032"
down_revision: str | None = "20260812_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED_BOARDS = (
    (
        "10000000-0000-4000-8000-000000000001",
        "general",
        "社区广场",
        "交流安全恢复经验、工具使用方式与协作建议。",
        10,
    ),
    (
        "10000000-0000-4000-8000-000000000002",
        "recovery_guides",
        "恢复指南",
        "分享合法授权场景下的恢复流程与排障记录。",
        20,
    ),
    (
        "10000000-0000-4000-8000-000000000003",
        "verification",
        "验证协作",
        "讨论指纹、候选结果与验证证据，不发布真实密码。",
        30,
    ),
    (
        "10000000-0000-4000-8000-000000000004",
        "security",
        "安全与隐私",
        "交流账号保护、数据最小化与隐私实践。",
        40,
    ),
)


def upgrade() -> None:
    op.create_table(
        "community_boards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(48), nullable=False),
        sa.Column("description", sa.String(300), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minimum_role", sa.String(32), nullable=False, server_default="user"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("is_read_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_community_boards_code"),
    )
    op.create_index("ix_community_boards_code", "community_boards", ["code"], unique=True)
    op.create_index("ix_community_boards_sort_order", "community_boards", ["sort_order"])
    op.create_index("ix_community_boards_status", "community_boards", ["status"])

    now = datetime.now(UTC)
    boards = sa.table(
        "community_boards",
        sa.column("id", sa.String),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("minimum_role", sa.String),
        sa.column("status", sa.String),
        sa.column("is_read_only", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    op.bulk_insert(
        boards,
        [
            {
                "id": i,
                "code": c,
                "name": n,
                "description": d,
                "sort_order": o,
                "minimum_role": "user",
                "status": "ACTIVE",
                "is_read_only": False,
                "created_at": now,
                "updated_at": now,
            }
            for i, c, n, d, o in _SEED_BOARDS
        ],
    )

    op.create_table(
        "community_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(48), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("post_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("slug", name="uq_community_groups_slug"),
    )
    for column in ("slug", "visibility", "owner_id", "status", "created_at"):
        op.create_index(
            f"ix_community_groups_{column}", "community_groups", [column], unique=column == "slug"
        )

    op.create_table(
        "community_group_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="MEMBER"),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("decided_by_id", sa.String(36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["community_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("group_id", "user_id", name="uq_community_group_membership"),
    )
    for column in ("group_id", "user_id", "role", "status", "created_at"):
        op.create_index(
            f"ix_community_group_memberships_{column}", "community_group_memberships", [column]
        )

    op.create_table(
        "community_group_governance_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("subject_user_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("before_state", sa.Text(), nullable=True),
        sa.Column("after_state", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["community_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subject_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    for column in ("group_id", "actor_id", "subject_user_id", "action", "created_at"):
        op.create_index(
            f"ix_community_group_governance_events_{column}",
            "community_group_governance_events",
            [column],
        )

    with op.batch_alter_table("community_posts") as batch:
        batch.add_column(sa.Column("board_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("group_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_community_posts_board_id",
            "community_boards",
            ["board_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_community_posts_group_id",
            "community_groups",
            ["group_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_community_posts_board_id", ["board_id"])
        batch.create_index("ix_community_posts_group_id", ["group_id"])
    connection = op.get_bind()
    for board_id, code, *_ in _SEED_BOARDS:
        connection.execute(
            sa.text("UPDATE community_posts SET board_id = :board_id WHERE board_code = :code"),
            {"board_id": board_id, "code": code.upper()},
        )
        connection.execute(
            sa.text("UPDATE community_posts SET board_id = :board_id WHERE board_code = :code"),
            {"board_id": board_id, "code": code},
        )
    with op.batch_alter_table("community_posts") as batch:
        batch.alter_column("board_id", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("community_posts") as batch:
        batch.drop_index("ix_community_posts_group_id")
        batch.drop_index("ix_community_posts_board_id")
        batch.drop_constraint("fk_community_posts_group_id", type_="foreignkey")
        batch.drop_constraint("fk_community_posts_board_id", type_="foreignkey")
        batch.drop_column("group_id")
        batch.drop_column("board_id")
    op.drop_table("community_group_governance_events")
    op.drop_table("community_group_memberships")
    op.drop_table("community_groups")
    op.drop_table("community_boards")
