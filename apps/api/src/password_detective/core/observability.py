from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from redis import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from password_detective.core.request_context import get_request_id

WORKER_HEARTBEAT_KEY: Final[str] = "password-detective:worker:heartbeat"
WORKER_HEARTBEAT_TTL_SECONDS: Final[int] = 90

_HISTOGRAM_BUCKETS: Final[tuple[float, ...]] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(items: Iterable[tuple[str, str]]) -> str:
    pairs = (f'{key}="{_escape_label(value)}"' for key, value in items)
    return "{" + ",".join(pairs) + "}"


@dataclass(frozen=True)
class RequestObservation:
    method: str
    route: str
    status_code: int
    duration_seconds: float


class MetricsRegistry:
    """Dependency-free Prometheus text registry with low-cardinality labels."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._durations: dict[tuple[str, str], list[int]] = defaultdict(
            lambda: [0] * len(_HISTOGRAM_BUCKETS)
        )
        self._duration_count: dict[tuple[str, str], int] = defaultdict(int)
        self._duration_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._active_requests = 0
        self._health = {"database": 0, "redis": 0, "worker": 0}
        self._queue_depth = 0
        self._started_at = time.time()

    def observe_request(self, observation: RequestObservation) -> None:
        key = (observation.method, observation.route, observation.status_code)
        duration_key = (observation.method, observation.route)
        with self._lock:
            self._requests[key] += 1
            for index, boundary in enumerate(_HISTOGRAM_BUCKETS):
                if observation.duration_seconds <= boundary:
                    self._durations[duration_key][index] += 1
                    break
            self._duration_count[duration_key] += 1
            self._duration_sum[duration_key] += observation.duration_seconds

    def active_request_started(self) -> None:
        with self._lock:
            self._active_requests += 1

    def active_request_finished(self) -> None:
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)

    def set_health(
        self,
        *,
        database: bool | None = None,
        redis: bool | None = None,
        worker: bool | None = None,
        queue_depth: int | None = None,
    ) -> None:
        with self._lock:
            updates = (("database", database), ("redis", redis), ("worker", worker))
            for name, value in updates:
                if value is not None:
                    self._health[name] = int(value)
            if queue_depth is not None:
                self._queue_depth = max(0, int(queue_depth))

    def render(self) -> str:
        lines = [
            "# HELP password_detective_http_requests_total Total HTTP requests.",
            "# TYPE password_detective_http_requests_total counter",
        ]
        with self._lock:
            requests = dict(self._requests)
            durations = {key: list(value) for key, value in self._durations.items()}
            duration_count = dict(self._duration_count)
            duration_sum = dict(self._duration_sum)
            active = self._active_requests
            health = dict(self._health)
            queue_depth = self._queue_depth
            uptime = max(0.0, time.time() - self._started_at)
        for (method, route, status_code), value in sorted(requests.items()):
            labels = _labels(
                (
                    ("method", method),
                    ("route", route),
                    ("status_code", str(status_code)),
                )
            )
            lines.append(f"password_detective_http_requests_total{labels} {value}")
        lines.extend(
            [
                "# HELP password_detective_http_request_duration_seconds "
                "HTTP request duration in seconds.",
                "# TYPE password_detective_http_request_duration_seconds histogram",
            ]
        )
        for (method, route), buckets in sorted(durations.items()):
            cumulative = 0
            for boundary, bucket_count in zip(_HISTOGRAM_BUCKETS, buckets, strict=True):
                cumulative += bucket_count
                labels = _labels(
                    (("method", method), ("route", route), ("le", str(boundary)))
                )
                lines.append(
                    "password_detective_http_request_duration_seconds_bucket"
                    f"{labels} {cumulative}"
                )
            count = duration_count[(method, route)]
            infinite_labels = _labels(
                (("method", method), ("route", route), ("le", "+Inf"))
            )
            metric_labels = _labels((("method", method), ("route", route)))
            lines.extend(
                [
                    "password_detective_http_request_duration_seconds_bucket"
                    f"{infinite_labels} {count}",
                    "password_detective_http_request_duration_seconds_sum"
                    f"{metric_labels} {duration_sum[(method, route)]:.6f}",
                    "password_detective_http_request_duration_seconds_count"
                    f"{metric_labels} {count}",
                ]
            )
        lines.extend(
            [
                "# HELP password_detective_http_requests_active "
                "Current in-flight HTTP requests.",
                "# TYPE password_detective_http_requests_active gauge",
                f"password_detective_http_requests_active {active}",
                "# HELP password_detective_dependency_up "
                "Dependency availability (1=up, 0=down).",
                "# TYPE password_detective_dependency_up gauge",
            ]
        )
        for name, value in sorted(health.items()):
            labels = _labels((("dependency", name),))
            lines.append(f"password_detective_dependency_up{labels} {value}")
        lines.extend(
            [
                "# HELP password_detective_worker_queue_depth Celery default queue depth.",
                "# TYPE password_detective_worker_queue_depth gauge",
                f"password_detective_worker_queue_depth {queue_depth}",
                "# HELP password_detective_process_uptime_seconds Process uptime in seconds.",
                "# TYPE password_detective_process_uptime_seconds gauge",
                f"password_detective_process_uptime_seconds {uptime:.3f}",
                "",
            ]
        )
        return "\n".join(lines)


metrics = MetricsRegistry()


def publish_worker_heartbeat(redis_url: str) -> None:
    client = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        client.set(WORKER_HEARTBEAT_KEY, str(int(time.time())), ex=WORKER_HEARTBEAT_TTL_SECONDS)
    finally:
        client.close()


def clear_worker_heartbeat(redis_url: str) -> None:
    client = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        client.delete(WORKER_HEARTBEAT_KEY)
    finally:
        client.close()


def refresh_runtime_metrics(redis_url: str) -> None:
    client = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        redis_up = bool(client.ping())
        worker_up = bool(client.exists(WORKER_HEARTBEAT_KEY))
        queue_depth = int(client.llen("celery"))
        metrics.set_health(
            redis=redis_up,
            worker=worker_up,
            queue_depth=queue_depth,
        )
    except RedisError:
        metrics.set_health(redis=False, worker=False, queue_depth=0)
    finally:
        client.close()


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.endswith("/metrics"):
            return await call_next(request)
        started = time.perf_counter()
        metrics.active_request_started()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration = time.perf_counter() - started
            route_object = request.scope.get("route")
            route_path = getattr(route_object, "path", None)
            route = (
                route_path
                if not route_path or route_path.startswith("/api/v1")
                else f"/api/v1{route_path}"
            )
            route = route or "__unmatched__"
            status_code = response.status_code if response is not None else 500
            metrics.observe_request(
                RequestObservation(request.method, route, status_code, duration)
            )
            metrics.active_request_finished()
            request_id = getattr(request.state, "request_id", get_request_id())
            request.app.state.logger.info(
                {
                    "event": "http.request.completed",
                    "method": request.method,
                    "route": route,
                    "status_code": status_code,
                    "duration_ms": round(duration * 1000, 3),
                },
                extra={"request_id": request_id},
            )
