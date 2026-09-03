from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from password_detective import worker


def test_migration_retry_task_is_scheduled_every_30_seconds() -> None:
    entry = worker.celery_app.conf.beat_schedule[
        "schedule-desktop-plugin-migration-retries"
    ]

    assert entry["task"] == "desktop_plugins.schedule_migration_retries"
    assert entry["schedule"] == 30.0


def test_migration_retry_task_delegates_and_disposes_database(
    monkeypatch,
) -> None:
    session = object()
    calls: dict[str, Any] = {}

    class FakeDatabase:
        def __init__(self, configured_settings: object) -> None:
            calls["settings"] = configured_settings

        @contextmanager
        def session_factory(self):
            calls["session_entered"] = True
            yield session
            calls["session_exited"] = True

        def dispose(self) -> None:
            calls["disposed"] = True

    def fake_schedule(db: object) -> dict[str, int]:
        calls["db"] = db
        return {"available": 2}

    monkeypatch.setattr(worker, "Database", FakeDatabase)
    monkeypatch.setattr(worker, "schedule_due_migration_retries", fake_schedule)

    assert worker.process_desktop_plugin_migration_retries() == {"available": 2}
    assert calls["settings"] is worker.settings
    assert calls["db"] is session
    assert calls["session_entered"] is True
    assert calls["session_exited"] is True
    assert calls["disposed"] is True
