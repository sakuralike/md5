from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from verify_staging_execution_evidence import validate_ha_report
from verify_staging_readiness_profile import normalized_file_sha256, validate_profile

SCHEMA = "staging-ha-execution-gate-v1"
FORMAL_SCHEMA = "staging-formal-session-control-v1"
HEX_REVISION_RE = re.compile(r"^[0-9a-f]{7,64}$", re.IGNORECASE)
DEPENDENCIES = ("mysql", "redis")


def format_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _check(checks: dict[str, bool], reasons: list[str], name: str, passed: bool, reason: str) -> None:
    checks[name] = passed
    if not passed:
        reasons.append(reason)


def build_preflight(
    state_path: Path,
    profile_path: Path,
    repository_root: Path,
    dependency: str,
    mysql_report_path: Optional[Path] = None,  # noqa: UP045 - target host Python 3.9
) -> dict[str, Any]:
    if dependency not in DEPENDENCIES:
        raise ValueError(f"dependency must be one of: {', '.join(DEPENDENCIES)}")

    profile = load_json(profile_path)
    validated_profile = validate_profile(profile, repository_root)
    profile_digest = normalized_file_sha256(profile_path)
    state = load_json(state_path)
    checks: dict[str, bool] = {}
    reasons: list[str] = []

    _check(checks, reasons, "formal_schema", state.get("schema") == FORMAL_SCHEMA, "formal session control schema is unsupported")
    _check(checks, reasons, "formal_completed", state.get("status") == "completed", f"formal session status is {state.get('status', 'missing')}, expected completed")
    source_revision = state.get("source_revision")
    valid_revision = isinstance(source_revision, str) and HEX_REVISION_RE.fullmatch(source_revision) is not None
    _check(checks, reasons, "source_revision", valid_revision, "formal session source revision is not a hexadecimal commit id")

    verification = state.get("verification")
    verification_object = verification if isinstance(verification, dict) else {}
    _check(checks, reasons, "verification_passed", verification_object.get("verification_status") == "passed", "formal session verification has not passed")
    _check(checks, reasons, "target_execution_eligible", verification_object.get("eligible_for_target_execution") is True, "formal session is not eligible for target execution")
    _check(checks, reasons, "execution_status", verification_object.get("execution_status") == "target-execution", "formal session evidence is not target-execution")
    duration = verification_object.get("duration_seconds")
    required_duration = int(validated_profile["duration_seconds"])
    duration_valid = isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration >= required_duration
    _check(checks, reasons, "minimum_duration", duration_valid, f"formal session duration is below {required_duration} seconds")

    output_value = state.get("output_directory")
    verification_path = Path(str(output_value)) / "staging-resource-samples-verification.json" if output_value else None
    report_exists = verification_path is not None and verification_path.is_file()
    _check(checks, reasons, "verification_report_exists", report_exists, "formal session verification report is missing")
    digest_matches = report_exists and verification_object.get("verification_sha256") == sha256(verification_path)
    _check(checks, reasons, "verification_digest", bool(digest_matches), "formal session verification digest does not match the report")

    prerequisite: Optional[dict[str, Any]] = None  # noqa: UP045 - target host Python 3.9
    if dependency == "redis":
        mysql_present = mysql_report_path is not None and mysql_report_path.is_file()
        _check(checks, reasons, "mysql_evidence_present", mysql_present, "Redis HA execution requires a completed MySQL HA target report")
        mysql_valid = False
        if mysql_present and mysql_report_path is not None:
            try:
                mysql_report = load_json(mysql_report_path)
                summary = validate_ha_report(mysql_report, profile, profile_digest, "mysql")
                mysql_valid = summary["evidence_kind"] == "target-execution"
                prerequisite = {
                    "dependency": "mysql",
                    "report_sha256": sha256(mysql_report_path),
                    "evidence_kind": summary["evidence_kind"],
                    "rto_seconds": summary["rto_seconds"],
                    "rpo_seconds": summary["rpo_seconds"],
                }
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                mysql_valid = False
        _check(checks, reasons, "mysql_target_execution_passed", mysql_valid, "MySQL HA prerequisite is not valid target-execution evidence")

    target = validated_profile["high_availability"][dependency]
    ready = all(checks.values())
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "ready" if ready else "blocked",
        "environment": "staging",
        "synthetic_data_only": True,
        "generated_at": format_utc(),
        "dependency": dependency,
        "mode": target["mode"],
        "source_revision": source_revision if isinstance(source_revision, str) else None,
        "formal_run_id": state.get("run_id"),
        "formal_state_sha256": sha256(state_path),
        "profile_sha256": profile_digest,
        "rto_seconds": target["rto_seconds"],
        "rpo_seconds": target["rpo_seconds"],
        "failover_runbook": target["runbook"],
        "expected_evidence_file": target["evidence_file"],
        "checks": checks,
        "blocked_reasons": reasons,
    }
    if prerequisite is not None:
        report["prerequisite"] = prerequisite
    return report


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Gate WP4 MySQL/Redis HA execution behind formal Staging evidence.")
    parser.add_argument("--dependency", choices=DEPENDENCIES, required=True)
    parser.add_argument("--state-file", type=Path, default=root / ".local/staging-formal-session-control.json")
    parser.add_argument("--profile", type=Path, default=root / "infra/staging/readiness-profile.example.json")
    parser.add_argument("--mysql-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write-checksums", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    output = args.output or root / ".local/staging-ha-execution-gate" / f"{args.dependency}-preflight.json"
    try:
        report = build_preflight(
            args.state_file.resolve(),
            args.profile.resolve(),
            root,
            args.dependency,
            args.mysql_report.resolve() if args.mysql_report else None,
        )
        atomic_write_json(output.resolve(), report)
        if args.write_checksums:
            checksum_path = output.resolve().with_name("SHA256SUMS")
            checksum_path.write_text(f"{sha256(output.resolve())}  {output.resolve().name}\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if args.require_ready and report["status"] != "ready" else 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"staging HA execution gate failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

