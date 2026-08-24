"""add user referral links and registration rewards

Revision ID: 20260824_0055
Revises: 20260824_0054
Create Date: 2026-08-24
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0055"
down_revision: str | None = "20260824_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _new_code(existing: set[str]) -> str:
    while True:
        code = f"pd-{secrets.token_hex(10)}"
        if code not in existing:
            existing.add(code)
            return code


def upgrade() -> None:
    op.create_table(
        "user_referral_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_referral_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_referral_profiles")),
        sa.UniqueConstraint("user_id", name="uq_user_referral_profiles_user_id"),
        sa.UniqueConstraint("code", name="uq_user_referral_profiles_code"),
    )
    op.create_index(
        op.f("ix_user_referral_profiles_user_id"),
        "user_referral_profiles",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_referral_profiles_code"),
        "user_referral_profiles",
        ["code"],
        unique=False,
    )

    op.create_table(
        "user_referral_uses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("referral_profile_id", sa.String(length=36), nullable=False),
        sa.Column("invitee_id", sa.String(length=36), nullable=False),
        sa.Column("points_awarded", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["referral_profile_id"],
            ["user_referral_profiles.id"],
            name=op.f("fk_user_referral_uses_referral_profile_id_user_referral_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invitee_id"],
            ["users.id"],
            name=op.f("fk_user_referral_uses_invitee_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_referral_uses")),
        sa.UniqueConstraint("invitee_id", name="uq_user_referral_uses_invitee_id"),
    )
    op.create_index(
        op.f("ix_user_referral_uses_referral_profile_id"),
        "user_referral_uses",
        ["referral_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_referral_uses_invitee_id"),
        "user_referral_uses",
        ["invitee_id"],
        unique=False,
    )

    bind = op.get_bind()
    existing_codes: set[str] = set()
    rows = bind.execute(sa.text("SELECT id FROM users")).mappings().all()
    for row in rows:
        bind.execute(
            sa.text(
                "INSERT INTO user_referral_profiles "
                "(id, user_id, code, created_at) VALUES (:id, :user_id, :code, :created_at)"
            ),
            {
                "id": str(uuid.uuid4()),
                "user_id": row["id"],
                "code": _new_code(existing_codes),
                "created_at": datetime.now(UTC),
            },
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_referral_uses_invitee_id"), table_name="user_referral_uses")
    op.drop_index(
        op.f("ix_user_referral_uses_referral_profile_id"), table_name="user_referral_uses"
    )
    op.drop_table("user_referral_uses")
    op.drop_index(op.f("ix_user_referral_profiles_code"), table_name="user_referral_profiles")
    op.drop_index(op.f("ix_user_referral_profiles_user_id"), table_name="user_referral_profiles")
    op.drop_table("user_referral_profiles")
