from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from verify_staging_readiness_profile import normalized_file_sha256, validate_profile

SCHEMA = "staging-ha-target-capability-v1"
EVIDENCE_KINDS = {"contract-fixture", "target-observation"}
DEPENDENCIES = {"mysql", "redis"}
FIXTURE_RE = re.compile(r"fixture|synthetic|mock|test", re.IGNORECASE)
SECRET_RE = re.compile(
    r"password|passwd|secret|token|authorization|cookie|api[_-]?key|private[_-]?key|connection[_-]?string|endpoint|hostname|host",
    re.IGNORECASE,
)
REQUIRED_CHECKS = {
    "control_plane_health",
    "replication_health",
    "failover_permission",
    "rollback_ready",
    "monitoring_ready",
    "synthetic_workload_ready",
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return value


def _require_int(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _require_true(value: Any, name: str) -> None:
    if value is not True:
        raise ValueError(f"{name} must be true")


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    return value


def _reject_secrets(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_RE.search(str(key)):
                raise ValueError(
                    f"secret or target address field is not allowed: {path}.{key}"
                )
            _reject_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secrets(item, f"{path}[{index}]")
    elif isinstance(value, str) and SECRET_RE.search(value):
        raise ValueError(f"secret-like value is not allowed at {path}")


def validate_capability(
    report: dict[str, Any],
    profile: dict[str, Any],
    repository_root: Path,
    dependency: str,
) -> dict[str, Any]:
    if dependency not in DEPENDENCIES:
        raise ValueError("dependency must be mysql or redis")
    if report.get("schema") != SCHEMA:
        raise ValueError("unexpected HA target capability schema")
    if (
        report.get("environment") != "staging"
        or report.get("synthetic_data_only") is not True
    ):
        raise ValueError(
            "HA target capability must describe synthetic-data-only Staging"
        )
    if report.get("dependency") != dependency:
        raise ValueError(f"capability dependency must be {dependency}")
    evidence_kind = _require_string(report.get("evidence_kind"), "evidence_kind")
    if evidence_kind not in EVIDENCE_KINDS:
        raise ValueError("evidence_kind must be contract-fixture or target-observation")
    source_adapter = _require_string(report.get("source_adapter"), "source_adapter")
    if evidence_kind == "target-observation" and FIXTURE_RE.search(source_adapter):
        raise ValueError(
            "target-observation cannot use a fixture, synthetic, mock or test adapter"
        )
    collected_at = _require_string(report.get("collected_at"), "collected_at")
    try:
        parsed = datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("collected_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("collected_at must include a timezone")

    validated_profile = validate_profile(profile, repository_root)
    target = validated_profile["high_availability"][dependency]
    if report.get("mode") != target["mode"]:
        raise ValueError("capability mode does not match the readiness profile")

    topology = _require_object(report.get("topology"), "topology")
    deployment_model = _require_string(
        topology.get("deployment_model"), "topology.deployment_model"
    )
    if dependency == "mysql" and deployment_model != "managed-service":
        raise ValueError("MySQL managed-ha requires deployment_model=managed-service")
    if dependency == "redis" and deployment_model not in {
        "managed-service",
        "self-managed-sentinel",
    }:
        raise ValueError("Redis HA requires managed-service or self-managed-sentinel")
    failure_domains = _require_int(
        topology.get("failure_domains"), "topology.failure_domains", 2
    )
    standby_replicas = _require_int(
        topology.get("standby_replicas"), "topology.standby_replicas", 1
    )
    _require_true(topology.get("automatic_failover"), "topology.automatic_failover")
    _require_true(
        topology.get("stable_application_address"),
        "topology.stable_application_address",
    )
    _require_true(topology.get("monitoring_enabled"), "topology.monitoring_enabled")
    _require_true(
        topology.get("backup_or_persistence_enabled"),
        "topology.backup_or_persistence_enabled",
    )
    if dependency == "mysql":
        _require_true(
            topology.get("point_in_time_recovery_enabled"),
            "topology.point_in_time_recovery_enabled",
        )
    if deployment_model == "self-managed-sentinel":
        _require_int(topology.get("sentinel_replicas"), "topology.sentinel_replicas", 3)

    limits = _require_object(report.get("limits"), "limits")
    rto = _require_int(limits.get("rto_seconds"), "limits.rto_seconds")
    rpo = _require_int(limits.get("rpo_seconds"), "limits.rpo_seconds")
    if rto > int(target["rto_seconds"]):
        raise ValueError("target RTO capability exceeds the readiness profile")
    if rpo > int(target["rpo_seconds"]):
        raise ValueError("target RPO capability exceeds the readiness profile")

    checks = _require_object(report.get("checks"), "checks")
    missing = REQUIRED_CHECKS - set(checks)
    if missing:
        raise ValueError(f"capability checks missing: {', '.join(sorted(missing))}")
    for name in REQUIRED_CHECKS:
        _require_true(checks.get(name), f"checks.{name}")
    _reject_secrets(report)
    return {
        "evidence_kind": evidence_kind,
        "source_adapter": source_adapter,
        "mode": target["mode"],
        "deployment_model": deployment_model,
        "failure_domains": failure_domains,
        "standby_replicas": standby_replicas,
        "rto_seconds": rto,
        "rpo_seconds": rpo,
    }


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Validate sanitized Staging HA target capability evidence."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--profile",
        type=Path,
        default=root / "infra/staging/readiness-profile.example.json",
    )
    parser.add_argument("--dependency", choices=sorted(DEPENDENCIES), required=True)
    args = parser.parse_args()
    try:
        report = load_json(args.input.resolve())
        profile = load_json(args.profile.resolve())
        summary = validate_capability(report, profile, root, args.dependency)
        output = {
            "schema": "staging-ha-target-capability-verification-v1",
            "status": "passed",
            "environment": "staging",
            "dependency": args.dependency,
            "profile_sha256": normalized_file_sha256(args.profile.resolve()),
            **summary,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"staging HA target capability validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
