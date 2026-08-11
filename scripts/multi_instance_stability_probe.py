from __future__ import annotations

import argparse
import json
import math
import os
import threading
import time
import urllib.request
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from celery import Celery
from redis import Redis
from sqlalchemy import create_engine, text

OPERATION_NAMES = ("api", "mysql", "redis", "celery")


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * ratio) - 1))
    return round(ordered[index], 3)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_operation_stats() -> dict[str, Any]:
    return {
        "count": 0,
        "error_count": 0,
        "max_consecutive_errors": 0,
        "current_consecutive_errors": 0,
        "latencies_ms": [],
    }


def public_operation_stats(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "count": int(value["count"]),
        "error_count": int(value["error_count"]),
        "max_consecutive_errors": int(value["max_consecutive_errors"]),
        "p95_ms": percentile(value["latencies_ms"], 0.95),
        "max_ms": round(max(value["latencies_ms"]), 3) if value["latencies_ms"] else 0.0,
    }


def build_probe_report(
    *,
    started_at: datetime,
    finished_at: datetime,
    window_seconds: int,
    aggregate: dict[str, dict[str, Any]],
    windows: list[dict[str, dict[str, Any]]],
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    probe_windows: list[dict[str, Any]] = []
    for index, values in enumerate(windows):
        window_started = started_at + timedelta(seconds=index * window_seconds)
        window_finished = min(
            finished_at,
            started_at + timedelta(seconds=(index + 1) * window_seconds),
        )
        if window_finished <= window_started:
            continue
        probe_windows.append(
            {
                "started_at": format_utc(window_started),
                "finished_at": format_utc(window_finished),
                "operations": {
                    name: public_operation_stats(values[name]) for name in OPERATION_NAMES
                },
            }
        )
    return {
        "schema": "multi-instance-stability-probe-v2",
        "status": "passed" if not errors else "failed",
        "synthetic_data_only": True,
        "started_at": format_utc(started_at),
        "finished_at": format_utc(finished_at),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "window_seconds": window_seconds,
        "operations": {
            name: public_operation_stats(aggregate[name]) for name in OPERATION_NAMES
        },
        "probe_windows": probe_windows,
        "error_count": len(errors),
        "errors": errors[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run concurrent WP4 multi-instance probes.")
    parser.add_argument("--api-url", default=os.getenv("WP4_PROBE_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL"))
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--interval-seconds", type=float, default=0.2)
    parser.add_argument("--window-seconds", type=int, default=60)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("database URL is required through --database-url or DATABASE_URL")
    if not args.redis_url:
        parser.error("Redis URL is required through --redis-url or REDIS_URL")
    if args.duration_seconds < 30:
        parser.error("duration must be at least 30 seconds")
    if not 0.05 <= args.interval_seconds <= 5:
        parser.error("interval must be between 0.05 and 5 seconds")
    if not 5 <= args.window_seconds <= args.duration_seconds:
        parser.error("window must be between 5 seconds and the session duration")

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
    aggregate = {name: new_operation_stats() for name in OPERATION_NAMES}
    window_count = math.ceil(args.duration_seconds / args.window_seconds)
    windows = [
        {name: new_operation_stats() for name in OPERATION_NAMES}
        for _ in range(window_count)
    ]
    errors: list[dict[str, str]] = []
    started_at = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()
    deadline = started_monotonic + args.duration_seconds

    def record(name: str, started: float, error: Optional[Exception]) -> None:  # noqa: UP045 - container supports Python 3.12; host contracts support 3.9
        elapsed = max(0.0, time.monotonic() - started_monotonic)
        window_index = min(window_count - 1, int(elapsed // args.window_seconds))
        latency_ms = (time.perf_counter() - started) * 1000
        with lock:
            for stats in (aggregate[name], windows[window_index][name]):
                stats["count"] += 1
                if error is None:
                    stats["latencies_ms"].append(latency_ms)
                    stats["current_consecutive_errors"] = 0
                else:
                    stats["error_count"] += 1
                    stats["current_consecutive_errors"] += 1
                    stats["max_consecutive_errors"] = max(
                        stats["max_consecutive_errors"],
                        stats["current_consecutive_errors"],
                    )
            if error is not None:
                message = str(error)
                for token in (args.database_url, args.redis_url):
                    message = message.replace(token, "[redacted-url]")
                errors.append(
                    {
                        "probe": name,
                        "observed_at": format_utc(datetime.now(timezone.utc)),
                        "error": message[:300],
                    }
                )

    def loop(name: str, operation: Callable[[int], None]) -> None:
        sequence = 0
        while not stop.is_set() and time.monotonic() < deadline:
            started = time.perf_counter()
            try:
                operation(sequence)
            except Exception as exc:  # noqa: BLE001 - evidence captures all probe failures
                record(name, started, exc)
            else:
                record(name, started, None)
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

    report = build_probe_report(
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        window_seconds=args.window_seconds,
        aggregate=aggregate,
        windows=windows,
        errors=errors,
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
