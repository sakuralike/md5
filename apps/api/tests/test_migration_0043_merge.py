from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_release_migrations_extend_search_document_version_head() -> None:
    api_directory = Path(__file__).resolve().parents[1]
    config = Config(str(api_directory / "alembic.ini"))
    config.set_main_option("script_location", str(api_directory / "alembic"))
    script_directory = ScriptDirectory.from_config(config)

    assert script_directory.get_heads() == ["20260820_0052"]
    assert script_directory.get_revision("20260816_0046").down_revision == "20260816_0045"
    assert script_directory.get_revision("20260816_0045").down_revision == "20260816_0044"
    assert script_directory.get_revision("20260816_0044").down_revision == "20260816_0043"
