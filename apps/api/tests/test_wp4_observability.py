from __future__ import annotations

import json
import logging

import fakeredis
from fastapi.testclient import TestClient

from password_detective.core.config import Settings
from password_detective.core.logging import JsonFormatter
from password_detective.core.notifications import MemoryNotificationGateway
from password_detective.core.observability import (
    MetricsRegistry,
    RequestObservation,
    clear_worker_heartbeat,
    metrics,
    publish_worker_heartbeat,
    refresh_runtime_metrics,
)
from password_detective.main import create_app


def test_metrics_endpoint_uses_normalized_routes_and_dependency_gauges(client):
    request_id = "synthetic-observability-request"
    response = client.get(
        "/api/v1/health/ready",
        headers={"X-Request-ID": request_id},
    )
    metrics_response = client.get("/api/v1/metrics")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    assert metrics_response.status_code == 200
    assert "text/plain" in metrics_response.headers["content-type"]
    body = metrics_response.text
    assert 'route="/api/v1/health/ready"' in body
    assert 'dependency="database"} 1' in body
    assert 'dependency="redis"} 1' in body
    assert "password_detective_worker_queue_depth" in body
    assert request_id not in body


def test_unmatched_routes_do_not_create_high_cardinality_labels(client):
    secret_path = "/missing/synthetic-object-123456789"
    response = client.get(secret_path)
    metrics_response = client.get("/api/v1/metrics")

    assert response.status_code == 404
    assert 'route="__unmatched__"' in metrics_response.text
    assert secret_path not in metrics_response.text


def test_metrics_can_be_disabled(tmp_path):
    settings = Settings(
        app_env="test",
        app_secret_key="synthetic-observability-disabled-secret",
        database_url=f"sqlite:///{(tmp_path / 'disabled.db').as_posix()}",
        rate_limit_backend="memory",
        notification_backend="memory",
        auto_create_tables=True,
        observability_metrics_enabled=False,
    )
    app = create_app(settings, notification_gateway=MemoryNotificationGateway())
    with TestClient(app) as client:
        response = client.get("/api/v1/metrics")
    assert response.status_code == 404


def test_histogram_buckets_are_cumulative_without_double_counting():
    registry = MetricsRegistry()
    registry.observe_request(RequestObservation("GET", "/synthetic", 200, 0.02))
    body = registry.render()

    assert 'le="0.01"} 0' in body
    assert 'le="0.025"} 1' in body
    assert 'le="0.05"} 1' in body
    assert 'le="+Inf"} 1' in body


def test_structured_logging_redacts_sensitive_fields():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="password_detective.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg={
            "event": "http.request.completed",
            "route": "/api/v1/archives/{archive_id}/reveal",
            "status_code": 200,
            "password": "synthetic-secret-value",
        },
        args=(),
        exc_info=None,
    )
    record.request_id = "synthetic-log-request-id"

    payload = json.loads(formatter.format(record))

    assert payload["event"] == "http.request.completed"
    assert payload["request_id"] == "synthetic-log-request-id"
    assert payload["password"] == "[REDACTED]"
    assert "synthetic-secret-value" not in json.dumps(payload)


def test_worker_heartbeats_are_isolated_per_instance(monkeypatch):
    server = fakeredis.FakeServer()

    def fake_from_url(*_args, **_kwargs):
        return fakeredis.FakeRedis(server=server, decode_responses=True)

    monkeypatch.setattr(
        "password_detective.core.observability.Redis.from_url", fake_from_url
    )

    publish_worker_heartbeat("redis://synthetic", "worker-a")
    publish_worker_heartbeat("redis://synthetic", "worker-b")
    refresh_runtime_metrics("redis://synthetic")
    body = metrics.render()
    assert "password_detective_worker_instances_ready 2" in body
    assert 'dependency="worker"} 1' in body

    clear_worker_heartbeat("redis://synthetic", "worker-a")
    refresh_runtime_metrics("redis://synthetic")
    body = metrics.render()
    assert "password_detective_worker_instances_ready 1" in body
    assert 'dependency="worker"} 1' in body


def test_database_pool_settings_are_applied_to_non_sqlite_engine(monkeypatch):
    captured: dict[str, object] = {}

    def fake_create_engine(url: str, **kwargs: object):
        captured["url"] = url
        captured.update(kwargs)

        class SyntheticEngine:
            def dispose(self) -> None:
                return None

        return SyntheticEngine()

    monkeypatch.setattr(
        "password_detective.db.database.create_engine", fake_create_engine
    )
    from password_detective.db.database import Database

    settings = Settings(
        app_env="test",
        app_secret_key="synthetic-database-pool-secret",
        database_url="mysql+pymysql://synthetic:synthetic@localhost/synthetic",
        database_pool_size=7,
        database_max_overflow=11,
        database_pool_timeout_seconds=19,
        database_pool_recycle_seconds=901,
    )
    Database(settings)

    assert captured["pool_pre_ping"] is True
    assert captured["pool_size"] == 7
    assert captured["max_overflow"] == 11
    assert captured["pool_timeout"] == 19
    assert captured["pool_recycle"] == 901
