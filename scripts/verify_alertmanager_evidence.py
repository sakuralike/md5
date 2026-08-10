from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_report(report: dict[str, Any]) -> dict[str, Any]:
    _assert(report.get("schema") == "alertmanager-drill-v1", "unexpected report schema")
    _assert(report.get("status") == "passed", "Alertmanager drill did not pass")
    checks = report.get("checks")
    _assert(isinstance(checks, dict), "checks object is required")
    readiness = checks.get("readiness", {})
    firing = checks.get("firing", {})
    recovery = checks.get("recovery", {})
    redaction = checks.get("redaction", {})
    delivery_ids = checks.get("delivery_ids", {})
    _assert(readiness.get("alertmanager_http") == 200, "Alertmanager was not ready")
    _assert(readiness.get("receiver_http") == 200, "notification gateway was not ready")
    _assert(firing.get("submitted") == 2, "drill must submit a duplicate firing alert")
    _assert(firing.get("delivered") == 1, "duplicate firing notification was not suppressed")
    _assert(firing.get("duplicate_suppressed") is True, "deduplication evidence is missing")
    _assert(recovery.get("delivered") == 1, "resolved notification was not delivered exactly once")
    _assert(recovery.get("send_resolved") is True, "send_resolved evidence is missing")
    _assert(redaction.get("raw_marker_absent") is True, "raw sensitive marker leaked")
    _assert(redaction.get("redaction_marker_present") is True, "redaction marker is missing")
    _assert(delivery_ids.get("total") == 2, "expected firing and resolved deliveries")
    _assert(delivery_ids.get("unique") == 2, "delivery IDs must be unique")
    serialized = json.dumps(report, ensure_ascii=False)
    _assert("synthetic-alert-secret-do-not-persist" not in serialized, "sensitive marker persisted in report")
    return {
        "schema": "alertmanager-evidence-v1",
        "status": "passed",
        "firing_deliveries": firing.get("delivered"),
        "resolved_deliveries": recovery.get("delivered"),
        "duplicate_suppressed": True,
        "redaction_verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate WP4 Alertmanager drill evidence.")
    parser.add_argument("--report", type=Path, default=Path(".local/alertmanager-wp4-iteration-9/alertmanager-report.json"))
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8-sig"))
        result = validate_report(report)
        if args.write_checksums:
            digest = hashlib.sha256(args.report.read_bytes()).hexdigest()
            (args.report.parent / "checksums.sha256").write_text(f"{digest}  {args.report.name}\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Alertmanager evidence validation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
