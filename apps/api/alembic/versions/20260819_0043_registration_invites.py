from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260819_0043"
down_revision: str | None = "20260815_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "registration_invites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_registration_invites_created_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registration_invites")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_registration_invites_code_hash")),
    )
    op.create_index(
        op.f("ix_registration_invites_code_hash"),
        "registration_invites",
        ["code_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_registration_invites_created_by"),
        "registration_invites",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_registration_invites_expires_at"),
        "registration_invites",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_registration_invites_revoked_at"),
        "registration_invites",
        ["revoked_at"],
        unique=False,
    )

    op.create_table(
        "registration_invite_uses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("invite_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["invite_id"],
            ["registration_invites.id"],
            name=op.f("fk_registration_invite_uses_invite_id_registration_invites"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_registration_invite_uses_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registration_invite_uses")),
        sa.UniqueConstraint("user_id", name="uq_registration_invite_uses_user_id"),
    )
    op.create_index(
        op.f("ix_registration_invite_uses_invite_id"),
        "registration_invite_uses",
        ["invite_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_registration_invite_uses_user_id"),
        "registration_invite_uses",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("registration_invite_uses")
    op.drop_table("registration_invites")
