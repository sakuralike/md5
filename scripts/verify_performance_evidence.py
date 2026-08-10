from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

_REQUIRED_WORKLOADS = {"liveness_100qps", "archives_search"}
_REQUIRED_METRICS = {
    "password_detective_http_requests_total",
    "password_detective_http_request_duration_seconds",
    "password_detective_http_requests_active",
    "password_detective_dependency_up",
    "password_detective_worker_queue_depth",
    "password_detective_process_uptime_seconds",
}
_SECRET_KEYS = {"password", "token", "authorization", "cookie", "secret", "fingerprint"}
_SECRET_VALUE = re.compile(r"bearer\s+|[a-f0-9]{64,}|eyJ[a-zA-Z0-9_-]{20,}", re.IGNORECASE)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _scan(value: Any, path: str = "report") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            _assert(normalized_key not in _SECRET_KEYS, f"secret-like key found: {path}.{key}")
            _scan(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan(item, f"{path}[{index}]")
    elif isinstance(value, str):
        _assert(not _SECRET_VALUE.search(value), f"secret-like value found: {path}")


def verify_report(report: dict[str, Any]) -> None:
    _assert(report.get("schema") == "performance-baseline-v1", "invalid schema")
    _assert(report.get("status") == "passed", "report status must be passed")
    workloads = report.get("workloads")
    _assert(isinstance(workloads, list), "workloads must be a list")
    names = {item.get("name") for item in workloads if isinstance(item, dict)}
    _assert(names == _REQUIRED_WORKLOADS, "required workloads are missing or unexpected")
    for item in workloads:
        _assert(item.get("status") == "passed", f"workload failed: {item.get('name')}")
        latency = item.get("latency_ms", {})
        thresholds = item.get("thresholds", {})
        _assert(latency.get("p95", float("inf")) <= thresholds.get("p95_ms", -1), "p95 exceeded")
        _assert(item.get("error_rate", 1) <= thresholds.get("max_error_rate", -1), "error rate exceeded")
        _assert(
            item.get("achieved_qps", 0)
            >= item.get("target_qps", float("inf")) * thresholds.get("min_target_qps_ratio", 2),
            "achieved QPS below threshold",
        )
    observability = report.get("observability", {})
    _assert(observability.get("status") == "passed", "observability checks failed")
    metrics = observability.get("required_metrics", {})
    _assert(set(metrics) == _REQUIRED_METRICS, "required metrics set mismatch")
    _assert(all(metrics.values()), "one or more required metrics are absent")
    for check in (
        "normalized_archive_route",
        "request_id_echo",
        "request_id_not_exported",
        "sensitive_query_not_exported",
    ):
        _assert(observability.get(check) is True, f"observability check failed: {check}")
    summary = report.get("summary", {})
    _assert(summary == {"passed": 3, "failed": 0}, "invalid summary")
    _scan(report)


def write_checksum(report_path: Path) -> Path:
    digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
    checksum_path = report_path.parent / "checksums.sha256"
    checksum_path.write_text(f"{digest}  {report_path.name}\n", encoding="utf-8")
    return checksum_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    verify_report(report)
    if args.write_checksums:
        write_checksum(args.report)
    print("Performance evidence is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
