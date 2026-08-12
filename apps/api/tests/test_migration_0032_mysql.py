from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest

MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "20260812_0032_community_boards_groups.py"
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_20260812_0032", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PartialMysqlInspector:
    def get_table_names(self) -> list[str]:
        return [
            "community_posts",
            "community_boards",
            "community_groups",
            "community_group_memberships",
            "community_group_governance_events",
        ]

    def get_columns(self, table_name: str) -> list[dict[str, object]]:
        assert table_name == "community_posts"
        return [
            {"name": "board_id", "nullable": True},
            {"name": "group_id", "nullable": True},
        ]


class RecordingBatch:
    def __init__(self) -> None:
        self.alter_calls: list[dict[str, object]] = []

    def __enter__(self) -> RecordingBatch:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def alter_column(self, name: str, **kwargs: object) -> None:
        self.alter_calls.append({"name": name, **kwargs})


class PartialMysqlConnection:
    dialect = SimpleNamespace(name="mysql")

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: object, parameters: object) -> None:
        del parameters
        self.statements.append(str(statement))

    def scalar(self, statement: object) -> int:
        self.statements.append(str(statement))
        return 0


def fail_duplicate_ddl(*args: object, **kwargs: object) -> None:
    pytest.fail(f"retry attempted duplicate DDL: args={args!r}, kwargs={kwargs!r}")


def test_mysql_retry_finishes_only_board_nullability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = load_migration()
    connection = PartialMysqlConnection()
    batch = RecordingBatch()

    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(migration.sa, "inspect", lambda bind: PartialMysqlInspector())
    monkeypatch.setattr(migration.op, "batch_alter_table", lambda table_name: batch)
    monkeypatch.setattr(migration.op, "create_table", fail_duplicate_ddl)
    monkeypatch.setattr(migration.op, "create_index", fail_duplicate_ddl)

    migration.upgrade()

    update_statements = [
        statement for statement in connection.statements if statement.startswith("UPDATE")
    ]
    assert len(update_statements) == 4
    assert any("COUNT(*)" in statement for statement in connection.statements)
    assert len(batch.alter_calls) == 1
    call = batch.alter_calls[0]
    assert call["name"] == "board_id"
    assert call["nullable"] is False
    assert str(call["existing_type"]) == "VARCHAR(36)"


def test_mysql_retry_refuses_unmapped_posts(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = load_migration()
    connection = PartialMysqlConnection()
    connection.scalar = cast(object, lambda statement: 1)

    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(migration.sa, "inspect", lambda bind: PartialMysqlInspector())
    monkeypatch.setattr(migration.op, "batch_alter_table", fail_duplicate_ddl)

    with pytest.raises(RuntimeError, match="无法映射"):
        migration.upgrade()
