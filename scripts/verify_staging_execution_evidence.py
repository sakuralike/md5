from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from verify_staging_readiness_profile import validate_profile

RESOURCE_SCHEMA = "staging-resource-trend-report-v1"
HA_SCHEMA = "staging-ha-failover-report-v1"
BUNDLE_SCHEMA = "staging-execution-evidence-bundle-v1"
RESOURCE_NAMES = {"api", "worker", "mysql", "redis"}
HA_NAMES = {"mysql", "redis"}
SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|authorization|cookie|api[_-]?key|private[_-]?key|connection[_-]?string)",
    re.IGNORECASE,
)
REQUIRED_HA_CHECKS = {
    "mysql": {
        "preflight_health",
        "failover_observed",
        "primary_changed",
        "application_readiness_recovered",
        "read_write_recovered",
        "data_consistency",
        "idempotency_preserved",
        "rollback_ready",
    },
    "redis": {
        "preflight_health",
        "failover_observed",
        "primary_changed",
        "application_readiness_recovered",
        "rate_limit_recovered",
        "celery_recovered",
        "queue_drained",
        "rollback_ready",
    },
}


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


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    return value


def _require_number(value: Any, name: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    result = float(value)
    if result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return value


def _parse_timestamp(value: Any, name: str) -> datetime:
    raw = _require_string(value, name)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed


def _require_passed(checks: dict[str, Any], name: str) -> None:
    check = checks.get(name)
    if not isinstance(check, dict) or check.get("status") != "passed":
        raise ValueError(f"{name} check did not pass")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} root must be an object")
    return value


def _profile_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_resource_report(
    report: dict[str, Any], profile: dict[str, Any], profile_sha256: str
) -> dict[str, Any]:
    if report.get("schema") != RESOURCE_SCHEMA:
        raise ValueError("unexpected resource trend report schema")
    if report.get("status") != "passed":
        raise ValueError("resource trend report did not pass")
    if report.get("environment") != "staging":
        raise ValueError("resource trend environment must be staging")
    if report.get("synthetic_data_only") is not True:
        raise ValueError("resource trend report must be synthetic-data-only")
    if report.get("profile_sha256") != profile_sha256:
        raise ValueError("resource trend report profile hash does not match the profile")
    evidence_kind = _require_string(report.get("evidence_kind"), "evidence_kind")
    if evidence_kind not in {"contract-fixture", "target-execution"}:
        raise ValueError("evidence_kind must be contract-fixture or target-execution")

    stability = _require_object(profile["stability"], "profile.stability")
    duration = _require_number(report.get("duration_seconds"), "duration_seconds")
    required_duration = int(stability["duration_seconds"])
    if duration < required_duration:
        raise ValueError(f"resource trend duration must be at least {required_duration} seconds")
    started = _parse_timestamp(report.get("started_at"), "started_at")
    finished = _parse_timestamp(report.get("finished_at"), "finished_at")
    elapsed = (finished - started).total_seconds()
    if elapsed < required_duration or abs(elapsed - duration) > 5:
        raise ValueError("resource trend timestamps do not cover the declared duration")

    sample_interval = _require_number(
        report.get("sample_interval_seconds"), "sample_interval_seconds", 1
    )
    configured_interval = int(stability["resource_sample_interval_seconds"])
    if sample_interval > configured_interval:
        raise ValueError("resource samples are less frequent than the staging profile")
    sample_count = int(_require_number(report.get("sample_count"), "sample_count"))
    minimum_samples = math.ceil(duration / sample_interval * 0.95)
    if sample_count < minimum_samples:
        raise ValueError(f"resource samples must contain at least {minimum_samples} samples")
    coverage = _require_number(report.get("coverage_percent"), "coverage_percent")
    if coverage < 95 or coverage > 100:
        raise ValueError("resource trend coverage must be between 95 and 100 percent")

    operations = _require_object(report.get("operations"), "operations")
    minimum_operations = _require_object(stability["minimum_operations"], "profile.minimum_operations")
    p95_limits = _require_object(stability["p95_limits_ms"], "profile.p95_limits_ms")
    operation_summary: dict[str, Any] = {}
    for name in ("api", "mysql", "redis", "celery"):
        operation = _require_object(operations.get(name), f"operations.{name}")
        count = int(_require_number(operation.get("count"), f"operations.{name}.count"))
        p95 = _require_number(operation.get("p95_ms"), f"operations.{name}.p95_ms")
        if count < int(minimum_operations[name]):
            raise ValueError(f"{name} operations are below the staging minimum")
        if p95 > float(p95_limits[name]):
            raise ValueError(f"{name} p95 exceeded the staging limit")
        operation_summary[name] = {"count": count, "p95_ms": p95}

    max_error_rate = _require_number(report.get("error_rate_percent"), "error_rate_percent")
    if max_error_rate > float(stability["max_error_rate_percent"]):
        raise ValueError("resource trend error rate exceeded the staging limit")
    consecutive = int(_require_number(report.get("max_consecutive_errors"), "max_consecutive_errors"))
    if consecutive > int(stability["max_consecutive_errors"]):
        raise ValueError("resource trend consecutive errors exceeded the staging limit")
    if report.get("single_worker_loss") is not True:
        raise ValueError("resource trend report must include single Worker loss")

    resources = _require_object(report.get("resources"), "resources")
    if set(resources) != RESOURCE_NAMES:
        raise ValueError("resource trend report must cover API, Worker, MySQL and Redis")
    resource_limits = _require_object(profile["resource_limits"], "profile.resource_limits")
    resource_summary: dict[str, Any] = {}
    for name in sorted(RESOURCE_NAMES):
        current = _require_object(resources[name], f"resources.{name}")
        limits = _require_object(resource_limits[name], f"profile.resource_limits.{name}")
        cpu = _require_object(current.get("cpu_percent"), f"resources.{name}.cpu_percent")
        memory = _require_object(
            current.get("memory_mebibytes"), f"resources.{name}.memory_mebibytes"
        )
        cpu_max = _require_number(cpu.get("max"), f"resources.{name}.cpu_percent.max")
        cpu_p95 = _require_number(cpu.get("p95"), f"resources.{name}.cpu_percent.p95")
        memory_max = _require_number(
            memory.get("max"), f"resources.{name}.memory_mebibytes.max"
        )
        memory_p95 = _require_number(
            memory.get("p95"), f"resources.{name}.memory_mebibytes.p95"
        )
        if cpu_max > float(limits["max_cpu_percent"]) or cpu_p95 > float(limits["max_cpu_percent"]):
            raise ValueError(f"{name} CPU resource limit exceeded")
        if memory_max > float(limits["max_memory_mebibytes"]):
            raise ValueError(f"{name} memory resource limit exceeded")
        resource_summary[name] = {
            "cpu_p95": cpu_p95,
            "cpu_max": cpu_max,
            "memory_p95": memory_p95,
            "memory_max": memory_max,
        }

    connection = _require_object(report.get("database_connections"), "database_connections")
    pool = _require_object(profile["database_pool"], "profile.database_pool")
    peak_connections = int(_require_number(connection.get("peak"), "database_connections.peak"))
    mysql_max = int(pool["mysql_max_connections"])
    reserved = int(pool["reserved_connections"])
    allowed = math.floor((mysql_max - reserved) * int(pool["max_budget_utilization_percent"]) / 100)
    if connection.get("allowed") != allowed:
        raise ValueError("database connection allowed budget does not match the profile")
    if peak_connections > allowed:
        raise ValueError("database connection peak exceeded the approved budget")
    if int(connection.get("remaining_at_peak", -1)) != mysql_max - peak_connections:
        raise ValueError("database remaining connection calculation is inconsistent")
    if int(connection["remaining_at_peak"]) < reserved:
        raise ValueError("database peak consumed reserved connections")

    queue = _require_object(report.get("celery_queue"), "celery_queue")
    if int(_require_number(queue.get("peak_depth"), "celery_queue.peak_depth")) < 0:
        raise ValueError("Celery peak depth cannot be negative")
    if int(queue.get("final_depth", -1)) != 0:
        raise ValueError("Celery queue did not drain")
    _walk_for_secrets(report)
    return {
        "evidence_kind": evidence_kind,
        "duration_seconds": duration,
        "sample_count": sample_count,
        "coverage_percent": coverage,
        "operations": operation_summary,
        "resources": resource_summary,
        "database_peak": peak_connections,
        "queue_peak_depth": int(queue["peak_depth"]),
    }


def validate_ha_report(
    report: dict[str, Any], profile: dict[str, Any], profile_sha256: str, dependency: str
) -> dict[str, Any]:
    if report.get("schema") != HA_SCHEMA:
        raise ValueError(f"unexpected {dependency} HA report schema")
    if report.get("status") != "passed":
        raise ValueError(f"{dependency} HA failover did not pass")
    if report.get("environment") != "staging":
        raise ValueError(f"{dependency} HA environment must be staging")
    if report.get("synthetic_data_only") is not True:
        raise ValueError(f"{dependency} HA report must be synthetic-data-only")
    if report.get("dependency") != dependency:
        raise ValueError(f"HA report dependency must be {dependency}")
    if report.get("profile_sha256") != profile_sha256:
        raise ValueError(f"{dependency} HA report profile hash does not match the profile")
    evidence_kind = _require_string(report.get("evidence_kind"), f"{dependency}.evidence_kind")
    if evidence_kind not in {"contract-fixture", "target-execution"}:
        raise ValueError("HA evidence_kind must be contract-fixture or target-execution")
    expected = _require_object(profile["high_availability"][dependency], f"profile.high_availability.{dependency}")
    if report.get("mode") != expected["mode"]:
        raise ValueError(f"{dependency} HA mode does not match the profile")
    started = _parse_timestamp(report.get("started_at"), f"{dependency}.started_at")
    finished = _parse_timestamp(report.get("finished_at"), f"{dependency}.finished_at")
    triggered = _parse_timestamp(report.get("failover_triggered_at"), f"{dependency}.failover_triggered_at")
    recovered = _parse_timestamp(report.get("recovered_at"), f"{dependency}.recovered_at")
    if not started <= triggered <= recovered <= finished:
        raise ValueError(f"{dependency} HA timestamps are not ordered")
    rto = _require_number(report.get("rto_seconds"), f"{dependency}.rto_seconds")
    rpo = _require_number(report.get("rpo_seconds"), f"{dependency}.rpo_seconds")
    if rto > float(expected["rto_seconds"]):
        raise ValueError(f"{dependency} RTO exceeded the profile")
    if rpo > float(expected["rpo_seconds"]):
        raise ValueError(f"{dependency} RPO exceeded the profile")
    checks = _require_object(report.get("checks"), f"{dependency}.checks")
    missing = REQUIRED_HA_CHECKS[dependency] - set(checks)
    if missing:
        raise ValueError(f"{dependency} HA checks missing: {', '.join(sorted(missing))}")
    for name in REQUIRED_HA_CHECKS[dependency]:
        _require_passed(checks, name)
    if int(_require_number(report.get("lost_records"), f"{dependency}.lost_records")) != 0:
        raise ValueError(f"{dependency} HA evidence reports lost records")
    _walk_for_secrets(report)
    return {"evidence_kind": evidence_kind, "mode": expected["mode"], "rto_seconds": rto, "rpo_seconds": rpo}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_checksums(paths: list[Path], destination: Path) -> None:
    lines = [f"{_sha256(path)}  {path.name}" for path in paths]
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_bundle(
    profile_path: Path,
    plan_path: Path,
    resource_path: Path,
    mysql_path: Path,
    redis_path: Path,
    output_path: Path,
    write_checksum_manifest: bool,
) -> dict[str, Any]:
    profile = _load_json(profile_path)
    validate_profile(profile, profile_path.resolve().parents[2])
    plan = _load_json(plan_path)
    profile_sha256 = _profile_sha256(profile_path)
    if plan.get("schema") != "staging-readiness-plan-v1" or plan.get("status") != "contract-valid":
        raise ValueError("readiness plan is not contract-valid")
    if plan.get("profile_sha256") != profile_sha256:
        raise ValueError("readiness plan profile hash does not match the profile")
    resource = _load_json(resource_path)
    mysql = _load_json(mysql_path)
    redis = _load_json(redis_path)
    resource_summary = validate_resource_report(resource, profile, profile_sha256)
    mysql_summary = validate_ha_report(mysql, profile, profile_sha256, "mysql")
    redis_summary = validate_ha_report(redis, profile, profile_sha256, "redis")
    kinds = {resource_summary["evidence_kind"], mysql_summary["evidence_kind"], redis_summary["evidence_kind"]}
    if len(kinds) != 1:
        raise ValueError("all evidence reports must use the same evidence_kind")
    evidence_kind = kinds.pop()
    if evidence_kind == "contract-fixture":
        execution_status = "not-run"
        go_no_go_status = "pending-evidence"
        status = "contract-valid"
    else:
        execution_status = "evidence-valid"
        go_no_go_status = "pending-approvals"
        status = "evidence-valid"
    summary = {
        "schema": BUNDLE_SCHEMA,
        "status": status,
        "evidence_kind": evidence_kind,
        "synthetic_data_only": True,
        "execution_status": execution_status,
        "go_no_go_status": go_no_go_status,
        "profile_sha256": profile_sha256,
        "readiness_plan_schema": "staging-readiness-plan-v1",
        "resource_trend": resource_summary,
        "mysql_ha": mysql_summary,
        "redis_ha": redis_summary,
        "reports": [resource_path.name, mysql_path.name, redis_path.name],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if write_checksum_manifest:
        write_checksums(
            [profile_path, plan_path, resource_path, mysql_path, redis_path, output_path],
            output_path.with_name("checksums.sha256"),
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify WP4 staging resource and HA evidence contracts.")
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--resource-report", type=Path, required=True)
    parser.add_argument("--mysql-report", type=Path, required=True)
    parser.add_argument("--redis-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    try:
        summary = validate_bundle(
            args.profile,
            args.plan,
            args.resource_report,
            args.mysql_report,
            args.redis_report,
            args.output,
            args.write_checksums,
        )
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"staging execution evidence verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
