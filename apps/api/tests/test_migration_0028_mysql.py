from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "20260812_0028_community_content_lifecycle.py"
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_20260812_0028", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CompletedMigrationInspector:
    def get_table_names(self) -> list[str]:
        return [
            "community_posts",
            "community_comments",
            "community_post_revisions",
        ]

    def get_columns(self, table_name: str) -> list[dict[str, str]]:
        columns = {
            "community_posts": ["version", "edited_at", "deleted_by_author_at"],
            "community_comments": [
                "root_id",
                "reply_to_user_id",
                "version",
                "edited_at",
                "deleted_by_author_at",
            ],
        }
        return [{"name": name} for name in columns.get(table_name, [])]

    def get_indexes(self, table_name: str) -> list[dict[str, str]]:
        indexes = {
            "community_post_revisions": [
                "ix_community_post_revisions_post_id",
                "ix_community_post_revisions_editor_id",
                "ix_community_post_revisions_created_at",
            ],
            "community_comments": [
                "ix_community_comments_root_id",
                "ix_community_comments_reply_to_user_id",
            ],
        }
        return [{"name": name} for name in indexes.get(table_name, [])]

    def get_foreign_keys(self, table_name: str) -> list[dict[str, str]]:
        if table_name != "community_comments":
            return []
        return [
            {"name": "fk_community_comments_root_id"},
            {"name": "fk_community_comments_reply_to_user_id"},
        ]


def fail_ddl(*args: object, **kwargs: object) -> None:
    pytest.fail(f"retry attempted duplicate DDL: args={args!r}, kwargs={kwargs!r}")


def test_mysql_backfill_uses_join_update(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = load_migration()
    statements: list[str] = []
    monkeypatch.setattr(
        migration.op, "execute", lambda statement: statements.append(str(statement))
    )

    bind = SimpleNamespace(dialect=SimpleNamespace(name="mysql"))
    migration._backfill_comment_hierarchy(bind)

    assert len(statements) == 1
    assert (
        "UPDATE community_comments AS child INNER JOIN community_comments AS parent"
        in statements[0]
    )
    assert "SET child.root_id = child.parent_id" in statements[0]
    assert "(SELECT" not in statements[0]


def test_mysql_retry_after_non_transactional_ddl_only_runs_backfill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = load_migration()
    bind = SimpleNamespace(dialect=SimpleNamespace(name="mysql"))
    statements: list[str] = []

    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)
    monkeypatch.setattr(migration.sa, "inspect", lambda connection: CompletedMigrationInspector())
    monkeypatch.setattr(migration.op, "batch_alter_table", fail_ddl)
    monkeypatch.setattr(migration.op, "create_table", fail_ddl)
    monkeypatch.setattr(migration.op, "create_index", fail_ddl)
    monkeypatch.setattr(
        migration.op, "execute", lambda statement: statements.append(str(statement))
    )

    migration.upgrade()

    assert len(statements) == 1
    assert "INNER JOIN community_comments AS parent" in statements[0]
