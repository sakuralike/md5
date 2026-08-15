from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa

MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "20260815_0042_profile_avatar_and_developer_requests.py"
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_20260815_0042", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BatchRecorder:
    def add_column(self, column: sa.Column[object]) -> None:
        del column

    def create_index(self, name: str, columns: list[str]) -> None:
        del name, columns


@contextmanager
def batch_recorder(table_name: str):
    del table_name
    yield BatchRecorder()


def test_mysql_ddl_for_application_requests_has_no_text_defaults(monkeypatch) -> None:
    migration = load_migration()
    created_tables: list[tuple[object, ...]] = []

    monkeypatch.setattr(migration.op, "batch_alter_table", batch_recorder)
    monkeypatch.setattr(migration.op, "create_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        migration.op,
        "create_table",
        lambda *args, **kwargs: created_tables.append(args),
    )

    migration.upgrade()

    request_args = next(
        args for args in created_tables if args[0] == "third_party_application_requests"
    )
    text_columns = [
        column
        for column in request_args[1:]
        if isinstance(column, sa.Column) and isinstance(column.type, sa.Text)
    ]

    assert {column.name for column in text_columns} >= {
        "description",
        "redirect_uris_json",
        "requested_scopes_json",
        "windows_release_info",
        "use_case",
    }
    assert all(column.server_default is None for column in text_columns)
