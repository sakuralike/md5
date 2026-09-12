from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime

from password_detective.db import models  # noqa: F401
from password_detective.db.base import Base


def test_direct_message_report_migration_is_the_current_head() -> None:
    api_directory = Path(__file__).resolve().parents[1]
    config = Config(str(api_directory / "alembic.ini"))
    config.set_main_option("script_location", str(api_directory / "alembic"))
    assert ScriptDirectory.from_config(config).get_heads() == ["20260912_0065"]


def test_direct_message_reports_preserve_report_rows_when_message_is_removed() -> None:
    reports = Base.metadata.tables["community_direct_message_reports"]
    assert reports.c.message_id.nullable is True
    assert reports.c.conversation_id.nullable is True
    assert isinstance(Base.metadata.tables["community_direct_messages"].c.removed_at.type, DateTime)
