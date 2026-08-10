from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

REQUIRED_CHECKS = {
    "old_key_read_succeeded",
    "dry_run_left_database_unchanged",
    "rotation_wrote_current_version",
    "rotation_plaintexts_verified",
    "rollback_wrote_legacy_version",
    "rollback_plaintexts_verified",
    "dedup_tags_stable",
    "ciphertexts_changed_on_rotation",
}
FORBIDDEN = re.compile(r"synthetic-rotation-(?:one|two)|candidate-key-000[12]", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify candidate secret rotation evidence")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--write-checksums", action="store_true")
    return parser.parse_args()


def require_mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    return value


def main() -> int:
    args = parse_args()
    raw = args.report.read_text(encoding="utf-8")
    if FORBIDDEN.search(raw):
        raise SystemExit("rotation evidence contains forbidden synthetic secret markers")
    report = require_mapping(json.loads(raw), "report")
    checks = require_mapping(report.get("checks"), "checks")
    if report.get("schema_version") != 1 or report.get("status") != "passed":
        raise SystemExit("rotation evidence did not pass")
    if set(checks) != REQUIRED_CHECKS or not all(value is True for value in checks.values()):
        raise SystemExit("rotation evidence checks are incomplete")
    for phase, expected_target in (("dry_run", "v2"), ("rotation", "v2"), ("rollback", "v1")):
        summary = require_mapping(report.get(phase), phase)
        if summary.get("scanned") != 2 or summary.get("rotated") != 2:
            raise SystemExit(f"{phase} summary counts are invalid")
        if summary.get("target_version") != expected_target:
            raise SystemExit(f"{phase} target version is invalid")
    if report["dry_run"].get("dry_run") is not True:
        raise SystemExit("dry-run phase was not marked dry-run")
    if report["rotation"].get("dry_run") is not False or report["rollback"].get("dry_run") is not False:
        raise SystemExit("apply phases were not marked as applied")
    if args.write_checksums:
        checksum = hashlib.sha256(args.report.read_bytes()).hexdigest()
        (args.report.parent / "SHA256SUMS").write_text(
            f"{checksum}  {args.report.name}\n", encoding="utf-8"
        )
    print(f"verified candidate secret rotation evidence: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
