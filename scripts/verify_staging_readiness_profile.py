from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

PROFILE_SCHEMA = "staging-readiness-profile-v1"
PLAN_SCHEMA = "staging-readiness-plan-v1"
REQUIRED_PROBES = {"api", "mysql", "redis", "celery"}
REQUIRED_RESOURCES = {"api", "worker", "mysql", "redis"}
SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|authorization|cookie|api[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)


def normalized_file_sha256(path: Path) -> str:
    """Hash a text contract without making the digest depend on checkout EOLs."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    return value


def _require_int(value: Any, name: str, minimum: int, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        suffix = f" and at most {maximum}" if maximum is not None else ""
        raise ValueError(f"{name} must be at least {minimum}{suffix}")
    return value


def _require_number(value: Any, name: str, minimum: float, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    number = float(value)
    if number < minimum or (maximum is not None and number > maximum):
        suffix = f" and at most {maximum}" if maximum is not None else ""
        raise ValueError(f"{name} must be at least {minimum}{suffix}")
    return number


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


def _require_relative_markdown(path_value: Any, name: str, repository_root: Path) -> str:
    if not isinstance(path_value, str) or not path_value.strip():
        raise TypeError(f"{name} must be a non-empty path")
    candidate = Path(path_value)
    if candidate.is_absolute() or candidate.suffix.lower() != ".md":
        raise ValueError(f"{name} must be a relative Markdown path")
    resolved = (repository_root / candidate).resolve()
    root = repository_root.resolve()
    if root not in resolved.parents:
        raise ValueError(f"{name} must stay inside the repository")
    if not resolved.is_file():
        raise ValueError(f"{name} does not exist: {path_value}")
    return candidate.as_posix()


def validate_profile(profile: dict[str, Any], repository_root: Path) -> dict[str, Any]:
    if profile.get("schema") != PROFILE_SCHEMA:
        raise ValueError("unexpected staging readiness profile schema")
    if profile.get("environment") != "staging":
        raise ValueError("environment must be staging")
    if profile.get("synthetic_data_only") is not True:
        raise ValueError("staging readiness execution must use synthetic data only")

    stability = _require_object(profile.get("stability"), "stability")
    duration_seconds = _require_int(
        stability.get("duration_seconds"), "stability.duration_seconds", 60, 86_400
    )
    probe_interval_seconds = _require_number(
        stability.get("probe_interval_seconds"),
        "stability.probe_interval_seconds",
        0.2,
        60,
    )
    resource_sample_interval_seconds = _require_int(
        stability.get("resource_sample_interval_seconds"),
        "stability.resource_sample_interval_seconds",
        5,
        300,
    )
    if duration_seconds / resource_sample_interval_seconds < 4:
        raise ValueError("stability window must contain at least 4 resource samples")
    if stability.get("single_worker_loss_required") is not True:
        raise ValueError("single worker loss must remain part of the staging gate")
    max_error_rate_percent = _require_number(
        stability.get("max_error_rate_percent"),
        "stability.max_error_rate_percent",
        0,
        1,
    )
    max_consecutive_errors = _require_int(
        stability.get("max_consecutive_errors"),
        "stability.max_consecutive_errors",
        0,
        10,
    )

    minimum_operations = _require_object(
        stability.get("minimum_operations"), "stability.minimum_operations"
    )
    latency_limits = _require_object(
        stability.get("p95_limits_ms"), "stability.p95_limits_ms"
    )
    if set(minimum_operations) != REQUIRED_PROBES or set(latency_limits) != REQUIRED_PROBES:
        raise ValueError("stability probe thresholds must cover api, mysql, redis and celery")
    for probe in sorted(REQUIRED_PROBES):
        _require_int(minimum_operations[probe], f"minimum_operations.{probe}", 50)
        _require_number(latency_limits[probe], f"p95_limits_ms.{probe}", 1, 30_000)

    topology = _require_object(profile.get("topology"), "topology")
    api_replicas = _require_int(topology.get("api_replicas"), "topology.api_replicas", 2, 100)
    api_processes = _require_int(
        topology.get("api_processes_per_replica"),
        "topology.api_processes_per_replica",
        1,
        64,
    )
    worker_replicas = _require_int(
        topology.get("worker_replicas"), "topology.worker_replicas", 3, 100
    )
    worker_processes = _require_int(
        topology.get("worker_processes_per_replica"),
        "topology.worker_processes_per_replica",
        1,
        64,
    )
    scheduler_replicas = _require_int(
        topology.get("scheduler_replicas"), "topology.scheduler_replicas", 1, 1
    )

    pool = _require_object(profile.get("database_pool"), "database_pool")
    pool_size = _require_int(pool.get("pool_size"), "database_pool.pool_size", 1, 100)
    max_overflow = _require_int(
        pool.get("max_overflow"), "database_pool.max_overflow", 0, 200
    )
    mysql_max_connections = _require_int(
        pool.get("mysql_max_connections"),
        "database_pool.mysql_max_connections",
        50,
        100_000,
    )
    reserved_connections = _require_int(
        pool.get("reserved_connections"),
        "database_pool.reserved_connections",
        1,
        mysql_max_connections - 1,
    )
    utilization_percent = _require_number(
        pool.get("max_budget_utilization_percent"),
        "database_pool.max_budget_utilization_percent",
        10,
        90,
    )
    client_processes = (
        api_replicas * api_processes
        + worker_replicas * worker_processes
        + scheduler_replicas
    )
    connections_per_process = pool_size + max_overflow
    requested_connections = client_processes * connections_per_process
    usable_connections = mysql_max_connections - reserved_connections
    allowed_connections = math.floor(usable_connections * utilization_percent / 100)
    if requested_connections > allowed_connections:
        raise ValueError(
            "database pool budget is overcommitted: "
            f"requested {requested_connections}, allowed {allowed_connections}"
        )

    resource_accounting = _require_object(
        profile.get("resource_accounting"), "resource_accounting"
    )
    if resource_accounting.get("cpu_scope") != "per-running-replica-average":
        raise ValueError(
            "resource_accounting.cpu_scope must be per-running-replica-average"
        )
    if resource_accounting.get("memory_scope") != "service-aggregate":
        raise ValueError("resource_accounting.memory_scope must be service-aggregate")
    if set(resource_accounting) != {"cpu_scope", "memory_scope"}:
        raise ValueError("resource_accounting contains unsupported fields")

    resource_limits = _require_object(profile.get("resource_limits"), "resource_limits")
    if set(resource_limits) != REQUIRED_RESOURCES:
        raise ValueError("resource limits must cover api, worker, mysql and redis")
    for resource, raw_limits in resource_limits.items():
        limits = _require_object(raw_limits, f"resource_limits.{resource}")
        _require_number(limits.get("max_cpu_percent"), f"{resource}.max_cpu_percent", 1, 95)
        _require_int(limits.get("max_memory_mebibytes"), f"{resource}.max_memory_mebibytes", 64)

    ha = _require_object(profile.get("high_availability"), "high_availability")
    ha_evidence: dict[str, Any] = {}
    for dependency in ("mysql", "redis"):
        item = _require_object(ha.get(dependency), f"high_availability.{dependency}")
        mode = item.get("mode")
        if not isinstance(mode, str) or mode in {"", "single", "standalone", "none"}:
            raise ValueError(f"{dependency} high availability mode must be declared")
        runbook = _require_relative_markdown(
            item.get("failover_runbook"),
            f"high_availability.{dependency}.failover_runbook",
            repository_root,
        )
        rto_seconds = _require_int(item.get("rto_seconds"), f"{dependency}.rto_seconds", 1, 3600)
        rpo_seconds = _require_int(item.get("rpo_seconds"), f"{dependency}.rpo_seconds", 0, 3600)
        evidence_file = item.get("evidence_file")
        if not isinstance(evidence_file, str) or not evidence_file.endswith(".json"):
            raise ValueError(f"{dependency}.evidence_file must be a JSON filename")
        if "/" in evidence_file or "\\" in evidence_file:
            raise ValueError(f"{dependency}.evidence_file must not contain directories")
        ha_evidence[dependency] = {
            "mode": mode,
            "runbook": runbook,
            "rto_seconds": rto_seconds,
            "rpo_seconds": rpo_seconds,
            "evidence_file": evidence_file,
        }

    release_decision = _require_object(profile.get("release_decision"), "release_decision")
    if release_decision.get("mode") != "automated-evidence-gate":
        raise ValueError("release_decision.mode must be automated-evidence-gate")
    template = _require_relative_markdown(
        release_decision.get("template"), "release_decision.template", repository_root
    )

    _walk_for_secrets(profile)
    return {
        "duration_seconds": duration_seconds,
        "probe_interval_seconds": probe_interval_seconds,
        "resource_sample_interval_seconds": resource_sample_interval_seconds,
        "max_error_rate_percent": max_error_rate_percent,
        "max_consecutive_errors": max_consecutive_errors,
        "minimum_operations": minimum_operations,
        "p95_limits_ms": latency_limits,
        "worker_replicas": worker_replicas,
        "capacity_budget": {
            "client_processes": client_processes,
            "connections_per_process": connections_per_process,
            "requested_connections": requested_connections,
            "usable_connections": usable_connections,
            "allowed_connections": allowed_connections,
            "remaining_connections": allowed_connections - requested_connections,
        },
        "resource_accounting": resource_accounting,
        "resource_limits": resource_limits,
        "high_availability": ha_evidence,
        "release_decision_template": template,
        "release_decision_mode": "automated-evidence-gate",
    }


def build_plan(profile: dict[str, Any], repository_root: Path, profile_path: Path) -> dict[str, Any]:
    validated = validate_profile(profile, repository_root)
    return {
        "schema": PLAN_SCHEMA,
        "status": "contract-valid",
        "execution_status": "not-run",
        "go_no_go_status": "pending-evidence",
        "environment": "staging",
        "profile_sha256": normalized_file_sha256(profile_path),
        "synthetic_data_only": True,
        **validated,
        "required_evidence": [
            "multi-instance-stability-report.json",
            "resource-trend-report.json",
            validated["high_availability"]["mysql"]["evidence_file"],
            validated["high_availability"]["redis"]["evidence_file"],
            "checksums.sha256",
            validated["release_decision_template"],
        ],
    }


def write_checksums(profile_path: Path, plan_path: Path) -> Path:
    checksum_path = plan_path.with_name("checksums.sha256")
    lines = []
    for path in (profile_path, plan_path):
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return checksum_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the WP4 staging readiness contract.")
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
        if not isinstance(profile, dict):
            raise TypeError("profile root must be an object")
        plan = build_plan(profile, args.repository_root, args.profile)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        checksum_path = None
        if args.write_checksums:
            checksum_path = write_checksums(args.profile, args.output)
        print(
            json.dumps(
                {
                    "schema": PLAN_SCHEMA,
                    "status": "passed",
                    "output": str(args.output),
                    "checksums": str(checksum_path) if checksum_path else None,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"staging readiness profile verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
