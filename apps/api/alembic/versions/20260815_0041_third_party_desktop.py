from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0041"
down_revision: str | None = "20260815_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Batch mode keeps this migration compatible with SQLite test/embedded deployments while
    # emitting regular ALTER statements for server databases.
    with op.batch_alter_table("client_installations") as batch_op:
        batch_op.add_column(sa.Column("third_party_app_id", sa.String(36), nullable=True))
        batch_op.add_column(
            sa.Column(
                "receipt_protocol",
                sa.String(48),
                nullable=False,
                server_default="desktop-receipt-v1",
            )
        )
        batch_op.add_column(sa.Column("operating_system", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("architecture", sa.String(32), nullable=True))
        batch_op.create_foreign_key(
            "fk_client_installations_third_party_app_id",
            "third_party_apps",
            ["third_party_app_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        "ix_client_installations_third_party_app_id",
        "client_installations",
        ["third_party_app_id"],
        unique=False,
    )
    op.create_index(
        "ix_client_installations_receipt_protocol",
        "client_installations",
        ["receipt_protocol"],
        unique=False,
    )

    with op.batch_alter_table("verification_challenges") as batch_op:
        batch_op.add_column(sa.Column("third_party_app_id", sa.String(36), nullable=True))
        batch_op.add_column(
            sa.Column(
                "receipt_protocol",
                sa.String(48),
                nullable=False,
                server_default="desktop-receipt-v1",
            )
        )
        batch_op.create_foreign_key(
            "fk_verification_challenges_third_party_app_id",
            "third_party_apps",
            ["third_party_app_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        "ix_verification_challenges_third_party_app_id",
        "verification_challenges",
        ["third_party_app_id"],
        unique=False,
    )
    op.create_index(
        "ix_verification_challenges_receipt_protocol",
        "verification_challenges",
        ["receipt_protocol"],
        unique=False,
    )

    with op.batch_alter_table("verification_receipts") as batch_op:
        batch_op.add_column(sa.Column("third_party_app_id", sa.String(36), nullable=True))
        batch_op.add_column(
            sa.Column(
                "receipt_protocol",
                sa.String(48),
                nullable=False,
                server_default="desktop-receipt-v1",
            )
        )
        batch_op.add_column(
            sa.Column(
                "trust_channel",
                sa.String(32),
                nullable=False,
                server_default="official_desktop",
            )
        )
        batch_op.create_foreign_key(
            "fk_verification_receipts_third_party_app_id",
            "third_party_apps",
            ["third_party_app_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        "ix_verification_receipts_third_party_app_id",
        "verification_receipts",
        ["third_party_app_id"],
        unique=False,
    )
    op.create_index(
        "ix_verification_receipts_receipt_protocol",
        "verification_receipts",
        ["receipt_protocol"],
        unique=False,
    )
    op.create_index(
        "ix_verification_receipts_trust_channel",
        "verification_receipts",
        ["trust_channel"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_verification_receipts_trust_channel", table_name="verification_receipts")
    op.drop_index("ix_verification_receipts_receipt_protocol", table_name="verification_receipts")
    op.drop_index("ix_verification_receipts_third_party_app_id", table_name="verification_receipts")
    with op.batch_alter_table("verification_receipts") as batch_op:
        batch_op.drop_constraint(
            "fk_verification_receipts_third_party_app_id", type_="foreignkey"
        )
        batch_op.drop_column("trust_channel")
        batch_op.drop_column("receipt_protocol")
        batch_op.drop_column("third_party_app_id")

    op.drop_index("ix_verification_challenges_receipt_protocol", table_name="verification_challenges")
    op.drop_index("ix_verification_challenges_third_party_app_id", table_name="verification_challenges")
    with op.batch_alter_table("verification_challenges") as batch_op:
        batch_op.drop_constraint(
            "fk_verification_challenges_third_party_app_id", type_="foreignkey"
        )
        batch_op.drop_column("receipt_protocol")
        batch_op.drop_column("third_party_app_id")

    op.drop_index("ix_client_installations_receipt_protocol", table_name="client_installations")
    op.drop_index("ix_client_installations_third_party_app_id", table_name="client_installations")
    with op.batch_alter_table("client_installations") as batch_op:
        batch_op.drop_constraint(
            "fk_client_installations_third_party_app_id", type_="foreignkey"
        )
        batch_op.drop_column("architecture")
        batch_op.drop_column("operating_system")
        batch_op.drop_column("receipt_protocol")
        batch_op.drop_column("third_party_app_id")