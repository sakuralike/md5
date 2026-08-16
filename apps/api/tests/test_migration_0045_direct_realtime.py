from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from password_detective.db import models  # noqa: F401
from password_detective.db.base import Base


def test_release_migrations_converge_at_direct_realtime_head() -> None:
    api_directory = Path(__file__).resolve().parents[1]
    config = Config(str(api_directory / "alembic.ini"))
    config.set_main_option("script_location", str(api_directory / "alembic"))

    assert ScriptDirectory.from_config(config).get_heads() == ["20260816_0045"]


def test_direct_realtime_tables_have_user_cursor_constraints_and_indexes() -> None:
    position = Base.metadata.tables["community_direct_stream_positions"]
    event = Base.metadata.tables["community_direct_events"]

    assert position.primary_key.columns.keys() == ["user_id"]
    assert {item.name for item in event.constraints} >= {
        "uq_community_direct_event_recipient_sequence"
    }
    assert {index.name for index in event.indexes} >= {
        "ix_community_direct_event_recipient_sequence",
        "ix_community_direct_event_conversation_created",
    }
    assert {"recipient_id", "sequence", "event_type", "payload"} <= set(
        event.columns.keys()
    )


def test_direct_realtime_migration_uses_mysql_safe_types() -> None:
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260816_0045_community_direct_realtime.py"
    )
    source = migration_path.read_text(encoding="utf-8")

    assert 'revision: str = "20260816_0045"' in source
    assert 'down_revision: str | None = "20260816_0044"' in source
    assert "sa.BigInteger()" in source
    assert "sa.JSON()" in source