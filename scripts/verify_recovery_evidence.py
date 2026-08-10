from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "recovery-drill-v1"
REQUIRED_CHECKS = ("mysql_backup_restore", "redis_loss_recovery", "worker_restart_idempotency")
THRESHOLDS = {
    "mysql_rpo_seconds": 60,
    "mysql_rto_seconds": 300,
    "redis_rto_seconds": 120,
    "worker_rto_seconds": 180,
}
SECRET_KEY_RE = re.compile(r"(password|passwd|secret|token|authorization|cookie|api[_-]?key|private[_-]?key)", re.IGNORECASE)


def _fail(message: str) -> None:
    raise ValueError(message)


def _walk(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                _fail(f"secret-like field is not allowed: {path}.{key}")
            yield from _walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")
    elif isinstance(value, str) and SECRET_KEY_RE.search(value):
        _fail(f"secret-like value is not allowed at {path}")


def validate_report(report: dict[str, Any]) -> None:
    if report.get("schema") != SCHEMA:
        _fail(f"schema must be {SCHEMA}")
    if report.get("status") != "passed":
        _fail("report status must be passed")
    checks = report.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(REQUIRED_CHECKS):
        _fail(f"checks must contain exactly: {', '.join(REQUIRED_CHECKS)}")
    for name in REQUIRED_CHECKS:
        check = checks[name]
        if not isinstance(check, dict) or check.get("status") != "passed":
            _fail(f"check {name} did not pass")
    summary = report.get("summary")
    if not isinstance(summary, dict) or summary.get("passed") != len(REQUIRED_CHECKS) or summary.get("failed") != 0:
        _fail("summary does not match three passed checks")
    timings = report.get("timings")
    if not isinstance(timings, dict):
        _fail("timings must be an object")
    for field, ceiling in THRESHOLDS.items():
        value = timings.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            _fail(f"{field} must be a non-negative number")
        if value > ceiling:
            _fail(f"{field}={value} exceeds threshold {ceiling}")
    for _ in _walk(report):
        pass


def write_checksums(report_path: Path) -> Path:
    digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
    checksum_path = report_path.with_name("checksums.sha256")
    checksum_path.write_text(f"{digest}  {report_path.name}\n", encoding="utf-8")
    return checksum_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate WP4 recovery drill evidence")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            _fail("report root must be an object")
        validate_report(report)
        checksum_path = write_checksums(args.report) if args.write_checksums else None
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"recovery evidence invalid: {exc}")
        return 1
    print(f"recovery evidence valid: {args.report}")
    if checksum_path:
        print(f"checksum written: {checksum_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


