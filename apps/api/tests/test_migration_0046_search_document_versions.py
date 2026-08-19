from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import BigInteger
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from password_detective.db import models  # noqa: F401
from password_detective.db.base import Base

SEARCH_DOCUMENT_VERSION_TABLES = (
    "community_search_documents",
    "community_search_outbox",
)


def test_release_migrations_converge_at_search_document_version_head() -> None:
    api_directory = Path(__file__).resolve().parents[1]
    config = Config(str(api_directory / "alembic.ini"))
    config.set_main_option("script_location", str(api_directory / "alembic"))

    assert ScriptDirectory.from_config(config).get_heads() == ["20260818_0048"]


def test_search_document_versions_compile_to_mysql_bigint() -> None:
    for table_name in SEARCH_DOCUMENT_VERSION_TABLES:
        table = Base.metadata.tables[table_name]
        column = table.c.document_version

        assert isinstance(column.type, BigInteger)
        ddl = str(CreateTable(table).compile(dialect=mysql.dialect())).upper()
        assert "DOCUMENT_VERSION BIGINT NOT NULL" in ddl


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "20260816_0046_widen_community_search_document_versions.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_20260816_0046", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _BatchRecorder:
    def __init__(self, table_name: str, changes: list[tuple[str, dict[str, object]]]) -> None:
        self._table_name = table_name
        self._changes = changes

    def alter_column(self, column_name: str, **kwargs: object) -> None:
        assert column_name == "document_version"
        self._changes.append((self._table_name, kwargs))


def _record_document_version_changes(migration: ModuleType) -> list[tuple[str, dict[str, object]]]:
    changes: list[tuple[str, dict[str, object]]] = []

    @contextmanager
    def batch_recorder(table_name: str):
        yield _BatchRecorder(table_name, changes)

    migration.op.batch_alter_table = batch_recorder
    return changes


def test_search_document_version_migration_widens_both_tables_with_batch_alter() -> None:
    migration = _load_migration()
    changes = _record_document_version_changes(migration)

    migration.upgrade()

    assert [table_name for table_name, _ in changes] == list(SEARCH_DOCUMENT_VERSION_TABLES)
    assert all(isinstance(change["existing_type"], sa.Integer) for _, change in changes)
    assert all(isinstance(change["type_"], sa.BigInteger) for _, change in changes)
    assert all(change["existing_nullable"] is False for _, change in changes)


def test_search_document_version_migration_downgrade_reverts_both_tables() -> None:
    migration = _load_migration()
    changes = _record_document_version_changes(migration)

    migration.downgrade()

    assert [table_name for table_name, _ in changes] == list(SEARCH_DOCUMENT_VERSION_TABLES)
    assert all(isinstance(change["existing_type"], sa.BigInteger) for _, change in changes)
    assert all(isinstance(change["type_"], sa.Integer) for _, change in changes)
    assert all(change["existing_nullable"] is False for _, change in changes)
