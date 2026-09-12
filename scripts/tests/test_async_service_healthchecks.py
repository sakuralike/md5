from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def _service_block(service: str, next_service: str) -> str:
    start = COMPOSE.index(f"  {service}:\n")
    end = COMPOSE.index(f"  {next_service}:\n", start)
    return COMPOSE[start:end]


def test_worker_healthcheck_uses_celery_ping_instead_of_http() -> None:
    worker = _service_block("worker", "scheduler")

    assert "healthcheck:" in worker
    assert "celery -A password_detective.worker.celery_app inspect ping" in worker
    assert "--destination celery@$$(hostname)" in worker
    assert "localhost:8000" not in worker


def test_scheduler_healthcheck_validates_the_beat_process() -> None:
    scheduler = _service_block("scheduler", "web")

    assert "healthcheck:" in scheduler
    assert "Path('/proc/1/cmdline').read_bytes()" in scheduler
    assert "b'celery' in command and b'beat' in command" in scheduler
    assert "localhost:8000" not in scheduler
