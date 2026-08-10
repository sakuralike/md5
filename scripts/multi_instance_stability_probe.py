from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from celery import Celery
from redis import Redis
from sqlalchemy import create_engine, text


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return round(ordered[index], 3)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run concurrent WP4 multi-instance probes.")
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--redis-url", required=True)
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--interval-seconds", type=float, default=0.2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.duration_seconds < 30:
        parser.error("duration must be at least 30 seconds")
    if not 0.05 <= args.interval_seconds <= 5:
        parser.error("interval must be between 0.05 and 5 seconds")

    engine = create_engine(
        args.database_url,
        pool_pre_ping=True,
        pool_size=8,
        max_overflow=8,
        pool_timeout=10,
        pool_recycle=300,
    )
    redis_client = Redis.from_url(
        args.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    celery = Celery("wp4-stability-probe", broker=args.redis_url, backend=args.redis_url)
    stop = threading.Event()
    lock = threading.Lock()
    latencies: dict[str, list[float]] = {
        "api": [],
        "mysql": [],
        "redis": [],
        "celery": [],
    }
    errors: list[dict[str, str]] = []
    started_at = time.time()
    deadline = started_at + args.duration_seconds

    def record(name: str, started: float) -> None:
        with lock:
            latencies[name].append((time.perf_counter() - started) * 1000)

    def fail(name: str, exc: Exception) -> None:
        message = str(exc)
        for token in (args.database_url, args.redis_url):
            message = message.replace(token, "[redacted-url]")
        with lock:
            errors.append({"probe": name, "error": message[:300]})

    def loop(name: str, operation: Callable[[int], None]) -> None:
        sequence = 0
        while not stop.is_set() and time.time() < deadline:
            started = time.perf_counter()
            try:
                operation(sequence)
                record(name, started)
            except Exception as exc:  # noqa: BLE001 - evidence captures all probe failures
                fail(name, exc)
            sequence += 1
            stop.wait(args.interval_seconds)

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS wp4_stability_probe ("
                "probe_id VARCHAR(64) PRIMARY KEY, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
        )

    def api_probe(_sequence: int) -> None:
        with urllib.request.urlopen(
            f"{args.api_url.rstrip('/')}/api/v1/health/ready", timeout=5
        ) as response:
            if response.status != 200:
                raise RuntimeError(f"readiness returned HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") != "ready":
                raise RuntimeError("readiness payload is not ready")

    def mysql_probe(sequence: int) -> None:
        marker = f"wp4-{sequence}-{uuid.uuid4().hex[:16]}"
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO wp4_stability_probe (probe_id) VALUES (:marker)"),
                {"marker": marker},
            )
            observed = connection.execute(
                text("SELECT COUNT(*) FROM wp4_stability_probe WHERE probe_id = :marker"),
                {"marker": marker},
            ).scalar_one()
            if observed != 1:
                raise RuntimeError("synthetic MySQL row was not readable")
            connection.execute(
                text("DELETE FROM wp4_stability_probe WHERE probe_id = :marker"),
                {"marker": marker},
            )

    def redis_probe(sequence: int) -> None:
        key = f"password-detective:wp4-stability:{sequence}:{uuid.uuid4().hex[:12]}"
        if not redis_client.set(key, "synthetic", ex=30):
            raise RuntimeError("Redis SET did not succeed")
        if redis_client.get(key) != "synthetic":
            raise RuntimeError("Redis GET did not return the synthetic value")
        redis_client.delete(key)

    def celery_probe(sequence: int) -> None:
        marker = f"wp4-stability-task-{sequence}-{uuid.uuid4().hex[:12]}"
        result = celery.send_task("observability.noop", args=[marker])
        if result.get(timeout=15) != marker:
            raise RuntimeError("Celery noop result did not match the marker")

    threads = [
        threading.Thread(target=loop, args=("api", api_probe), daemon=True),
        threading.Thread(target=loop, args=("mysql", mysql_probe), daemon=True),
        threading.Thread(target=loop, args=("redis", redis_probe), daemon=True),
        threading.Thread(target=loop, args=("celery", celery_probe), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(args.duration_seconds + 30)
    stop.set()

    try:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS wp4_stability_probe"))
    finally:
        engine.dispose()
        redis_client.close()

    report: dict[str, Any] = {
        "schema": "multi-instance-stability-probe-v1",
        "status": "passed" if not errors else "failed",
        "duration_seconds": round(time.time() - started_at, 3),
        "operations": {
            name: {
                "count": len(values),
                "p95_ms": percentile(values, 0.95),
                "max_ms": round(max(values), 3) if values else 0.0,
            }
            for name, values in latencies.items()
        },
        "error_count": len(errors),
        "errors": errors[:20],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
