from __future__ import annotations

import json
import logging

from fastapi.testclient import TestClient

from password_detective.core.config import Settings
from password_detective.core.logging import JsonFormatter
from password_detective.core.notifications import MemoryNotificationGateway
from password_detective.core.observability import MetricsRegistry, RequestObservation
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
