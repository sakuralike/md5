from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA = "multi-instance-stability-drill-v1"
PROBE_SCHEMAS = {"multi-instance-stability-probe-v1", "multi-instance-stability-probe-v2"}
SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|authorization|cookie|api[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)
LATENCY_LIMITS = {"api": 3000, "mysql": 3000, "redis": 1500, "celery": 15000}


def _walk_for_secrets(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                raise ValueError(f"secret-like field is not allowed: {path}.{key}")
            _walk_for_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_for_secrets(item, f"{path}[{index}]")
    elif isinstance(value, str) and SECRET_KEY_RE.search(value):
        raise ValueError(f"secret-like value is not allowed at {path}")


def require_passed(checks: dict[str, Any], name: str) -> dict[str, Any]:
    value = checks.get(name)
    if not isinstance(value, dict) or value.get("status") != "passed":
        raise ValueError(f"{name} check did not pass")
    return value


def validate_report(report: dict[str, Any]) -> None:
    if report.get("schema") != SCHEMA:
        raise ValueError("unexpected report schema")
    if report.get("status") != "passed":
        raise ValueError("multi-instance stability drill did not pass")
    configuration = report.get("configuration")
    if not isinstance(configuration, dict):
        raise TypeError("configuration must be an object")
    worker_count = int(configuration.get("worker_count", 0))
    if worker_count < 3:
        raise ValueError("at least three worker instances are required")
    if int(configuration.get("duration_seconds", 0)) < 45:
        raise ValueError("stability window must be at least 45 seconds")

    checks = report.get("checks")
    if not isinstance(checks, dict):
        raise TypeError("checks must be an object")
    initial = require_passed(checks, "initial_workers")
    degraded = require_passed(checks, "single_worker_loss")
    recovered = require_passed(checks, "worker_replacement")
    queue = require_passed(checks, "queue_drained")
    require_passed(checks, "final_readiness")
    if int(initial.get("observed", 0)) < worker_count:
        raise ValueError("initial worker count is below the requested scale")
    if int(degraded.get("observed", 0)) < worker_count - 1:
        raise ValueError("remaining worker count is below the degraded target")
    if int(degraded.get("worker_dependency_up", 0)) != 1:
        raise ValueError("worker dependency became unavailable after one worker loss")
    if int(recovered.get("observed", 0)) < worker_count:
        raise ValueError("replacement worker count did not recover")
    if int(queue.get("observed_depth", -1)) != 0:
        raise ValueError("Celery queue did not drain")

    probe = report.get("probe")
    if not isinstance(probe, dict) or probe.get("schema") not in PROBE_SCHEMAS:
        raise ValueError("unexpected probe schema")
    if probe.get("status") != "passed" or int(probe.get("error_count", -1)) != 0:
        raise ValueError("mixed-load probe contains errors")
    operations = probe.get("operations")
    if not isinstance(operations, dict):
        raise TypeError("probe operations must be an object")
    for name, limit in LATENCY_LIMITS.items():
        operation = operations.get(name)
        if not isinstance(operation, dict):
            raise TypeError(f"{name} probe evidence is missing")
        if int(operation.get("count", 0)) < 10:
            raise ValueError(f"{name} probe did not complete at least ten operations")
        if float(operation.get("p95_ms", limit + 1)) > limit:
            raise ValueError(f"{name} probe p95 exceeded {limit} ms")
    _walk_for_secrets(report)


def write_checksums(report_path: Path) -> Path:
    checksum_path = report_path.with_name("checksums.sha256")
    checksum = hashlib.sha256(report_path.read_bytes()).hexdigest()
    checksum_path.write_text(f"{checksum}  {report_path.name}\n", encoding="utf-8")
    return checksum_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify WP4 multi-instance stability evidence.")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8-sig"))
        if not isinstance(report, dict):
            raise TypeError("report root must be an object")
        validate_report(report)
        if args.write_checksums:
            write_checksums(args.report)
        print(json.dumps({"schema": "multi-instance-stability-evidence-v1", "status": "passed"}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"multi-instance stability evidence verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
