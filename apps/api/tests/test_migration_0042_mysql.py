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
    def __init__(self) -> None:
        self.added_columns: list[str] = []
        self.created_indexes: list[str] = []

    def add_column(self, column: sa.Column[object]) -> None:
        self.added_columns.append(column.name)

    def create_index(self, name: str, columns: list[str]) -> None:
        del columns
        self.created_indexes.append(name)


@contextmanager
def batch_recorder(table_name: str):
    del table_name
    yield BatchRecorder()


def test_mysql_ddl_for_application_requests_has_no_text_defaults(monkeypatch) -> None:
    migration = load_migration()
    created_tables: list[tuple[object, ...]] = []

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(migration.sa, "inspect", lambda bind: FreshMySqlInspector())
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


class FreshMySqlInspector:
    def get_columns(self, table_name: str) -> list[dict[str, str]]:
        if table_name == "community_public_profiles":
            return []
        return []

    def get_indexes(self, table_name: str) -> list[dict[str, str]]:
        del table_name
        return []

    def get_table_names(self) -> list[str]:
        return ["community_public_profiles"]


class PartialMySqlInspector:
    def get_columns(self, table_name: str) -> list[dict[str, str]]:
        if table_name == "community_public_profiles":
            return [
                {"name": "avatar_kind"},
                {"name": "avatar_url"},
                {"name": "gravatar_enabled"},
            ]
        return []

    def get_indexes(self, table_name: str) -> list[dict[str, str]]:
        if table_name == "community_public_profiles":
            return [{"name": "ix_community_public_profiles_avatar_kind"}]
        return []

    def get_table_names(self) -> list[str]:
        return ["community_public_profiles"]


def test_mysql_retry_skips_already_applied_profile_columns(monkeypatch) -> None:
    migration = load_migration()
    batch = BatchRecorder()
    created_tables: list[str] = []

    @contextmanager
    def record_batch(table_name: str):
        assert table_name == "community_public_profiles"
        yield batch

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(migration.sa, "inspect", lambda bind: PartialMySqlInspector())
    monkeypatch.setattr(migration.op, "batch_alter_table", record_batch)
    monkeypatch.setattr(migration.op, "create_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        migration.op,
        "create_table",
        lambda table_name, *args, **kwargs: created_tables.append(table_name),
    )

    migration.upgrade()

    assert batch.added_columns == []
    assert batch.created_indexes == []
    assert created_tables == [
        "third_party_application_requests",
        "third_party_application_review_events",
    ]
