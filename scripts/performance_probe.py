from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def request_once(url: str, request_id: str) -> tuple[int, float, str | None]:
    request = urllib.request.Request(url, headers={"X-Request-ID": request_id})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
            return response.status, time.perf_counter() - started, None
    except urllib.error.HTTPError as exc:
        exc.read()
        return exc.code, time.perf_counter() - started, None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, time.perf_counter() - started, type(exc).__name__


def run_workload(
    *,
    name: str,
    base_url: str,
    request_path: str,
    report_route: str,
    total_requests: int,
    concurrency: int,
    target_qps: float,
    p95_threshold_ms: float,
) -> dict[str, Any]:
    futures: list[Future[tuple[int, float, str | None]]] = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for index in range(total_requests):
            scheduled = started + (index / target_qps)
            remaining = scheduled - time.perf_counter()
            if remaining > 0:
                time.sleep(remaining)
            futures.append(
                executor.submit(
                    request_once,
                    base_url + request_path,
                    f"perf-{name}-{index:05d}",
                )
            )
        results = [future.result() for future in futures]
    duration = time.perf_counter() - started
    latencies_ms = [elapsed * 1000 for _, elapsed, _ in results]
    status_counts: dict[str, int] = {}
    errors: dict[str, int] = {}
    for status_code, _, error in results:
        key = str(status_code)
        status_counts[key] = status_counts.get(key, 0) + 1
        if error:
            errors[error] = errors.get(error, 0) + 1
    successful = status_counts.get("200", 0)
    error_rate = (total_requests - successful) / total_requests
    achieved_qps = total_requests / duration
    p95 = percentile(latencies_ms, 0.95)
    threshold = {
        "p95_ms": p95_threshold_ms,
        "max_error_rate": 0.01,
        "min_target_qps_ratio": 0.8,
    }
    passed = (
        p95 <= threshold["p95_ms"]
        and error_rate <= threshold["max_error_rate"]
        and achieved_qps >= target_qps * threshold["min_target_qps_ratio"]
    )
    return {
        "name": name,
        "method": "GET",
        "route": report_route,
        "total_requests": total_requests,
        "concurrency": concurrency,
        "target_qps": target_qps,
        "duration_seconds": round(duration, 3),
        "achieved_qps": round(achieved_qps, 3),
        "status_counts": status_counts,
        "errors": errors,
        "error_rate": round(error_rate, 6),
        "latency_ms": {
            "min": round(min(latencies_ms), 3),
            "mean": round(statistics.fmean(latencies_ms), 3),
            "p50": round(percentile(latencies_ms, 0.50), 3),
            "p95": round(p95, 3),
            "p99": round(percentile(latencies_ms, 0.99), 3),
            "max": round(max(latencies_ms), 3),
        },
        "thresholds": threshold,
        "status": "passed" if passed else "failed",
    }


def fetch_observability(base_url: str) -> dict[str, Any]:
    correlation_id = "performance-correlation-check"
    request = urllib.request.Request(
        base_url + "/api/v1/health/live",
        headers={"X-Request-ID": correlation_id},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
        echoed = response.headers.get("X-Request-ID")
    with urllib.request.urlopen(base_url + "/api/v1/metrics", timeout=10) as response:
        metrics_text = response.read().decode("utf-8")
        metrics_status = response.status
    required_metrics = [
        "password_detective_http_requests_total",
        "password_detective_http_request_duration_seconds",
        "password_detective_http_requests_active",
        "password_detective_dependency_up",
        "password_detective_worker_queue_depth",
        "password_detective_process_uptime_seconds",
    ]
    return {
        "metrics_status_code": metrics_status,
        "required_metrics": {
            name: name in metrics_text for name in required_metrics
        },
        "normalized_archive_route": 'route="/api/v1/archives/search"' in metrics_text,
        "request_id_echo": echoed == correlation_id,
        "request_id_not_exported": correlation_id not in metrics_text,
        "sensitive_query_not_exported": "a" * 64 not in metrics_text,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    workloads = [
        run_workload(
            name="liveness_100qps",
            base_url=base_url,
            request_path="/api/v1/health/live",
            report_route="/api/v1/health/live",
            total_requests=300,
            concurrency=32,
            target_qps=100.0,
            p95_threshold_ms=250.0,
        ),
        run_workload(
            name="archives_search",
            base_url=base_url,
            request_path="/api/v1/archives/search?fingerprint=" + "a" * 64,
            report_route="/api/v1/archives/search",
            total_requests=40,
            concurrency=4,
            target_qps=10.0,
            p95_threshold_ms=500.0,
        ),
    ]
    observability = fetch_observability(base_url)
    passed_workloads = sum(item["status"] == "passed" for item in workloads)
    observability_passed = (
        observability["metrics_status_code"] == 200
        and all(observability["required_metrics"].values())
        and observability["normalized_archive_route"]
        and observability["request_id_echo"]
        and observability["request_id_not_exported"]
        and observability["sensitive_query_not_exported"]
    )
    report = {
        "schema": "performance-baseline-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": "isolated-integration",
        "workloads": workloads,
        "observability": {
            **observability,
            "status": "passed" if observability_passed else "failed",
        },
        "summary": {
            "passed": passed_workloads + int(observability_passed),
            "failed": len(workloads) + 1 - passed_workloads - int(observability_passed),
        },
        "status": (
            "passed"
            if passed_workloads == len(workloads) and observability_passed
            else "failed"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
