from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

SCHEMA = "staging-topology-capacity-preflight-v1"
PREFLIGHT_VERSION = "1.0.0"
SERVICES = ("api", "worker", "scheduler", "mysql", "redis")


class Runner(Protocol):
    def run(self, arguments: Sequence[str]) -> str: ...


class SubprocessRunner:
    def run(self, arguments: Sequence[str]) -> str:
        completed = subprocess.run(
            list(arguments),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"command failed ({completed.returncode}): {arguments[0]}: {detail[:400]}"
            )
        return completed.stdout


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} root must be an object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def compose_prefix(
    compose_files: Sequence[str],
    project_directory: Optional[str],  # noqa: UP045 - target Python 3.9
) -> list[str]:
    arguments = ["docker", "compose"]
    if project_directory:
        arguments.extend(["--project-directory", project_directory])
    for compose_file in compose_files:
        arguments.extend(["--file", compose_file])
    return arguments


def discover_service_counts(
    runner: Runner,
    compose_files: Sequence[str],
    project_directory: Optional[str],  # noqa: UP045 - target Python 3.9
) -> tuple[dict[str, int], list[str]]:
    prefix = compose_prefix(compose_files, project_directory)
    output = runner.run([*prefix, "ps", "--format", "json"])
    counts = {service: 0 for service in SERVICES}
    rows = 0
    for line_number, line in enumerate(output.splitlines(), start=1):
        if not line.strip():
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise TypeError(f"compose ps line {line_number} must be a JSON object")
        rows += 1
        service = str(parsed.get("Service", ""))
        state = str(parsed.get("State", ""))
        if service in counts and state == "running":
            counts[service] += 1
    if rows == 0:
        raise ValueError("compose ps returned no rows")
    return counts, prefix


def build_capacity_budget(profile: dict[str, Any]) -> dict[str, int]:
    topology = profile["topology"]
    pool = profile["database_pool"]
    client_processes = (
        int(topology["api_replicas"]) * int(topology["api_processes_per_replica"])
        + int(topology["worker_replicas"]) * int(topology["worker_processes_per_replica"])
        + int(topology["scheduler_replicas"])
    )
    connections_per_process = int(pool["pool_size"]) + int(pool["max_overflow"])
    requested_connections = client_processes * connections_per_process
    usable_connections = int(pool["mysql_max_connections"]) - int(pool["reserved_connections"])
    allowed_connections = math.floor(
        usable_connections * int(pool["max_budget_utilization_percent"]) / 100
    )
    return {
        "client_processes": client_processes,
        "connections_per_process": connections_per_process,
        "requested_connections": requested_connections,
        "usable_connections": usable_connections,
        "allowed_connections": allowed_connections,
        "remaining_connections": allowed_connections - requested_connections,
    }


def build_topology_preflight(
    profile: dict[str, Any],
    service_replicas: dict[str, int],
    *,
    observed_at: Optional[datetime] = None,  # noqa: UP045 - target Python 3.9
) -> dict[str, Any]:
    if set(service_replicas) != set(SERVICES):
        raise ValueError("service replica counts must cover api, worker, scheduler, mysql and redis")
    for service, count in service_replicas.items():
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"service replica count must be a non-negative integer: {service}")
    topology = profile.get("topology")
    if not isinstance(topology, dict):
        raise TypeError("profile.topology must be an object")
    expected = {
        "api": int(topology["api_replicas"]),
        "worker": int(topology["worker_replicas"]),
        "scheduler": int(topology["scheduler_replicas"]),
        "mysql": 1,
        "redis": 1,
    }
    checks = {
        "api_replicas": service_replicas["api"] == expected["api"],
        "worker_replicas": service_replicas["worker"] == expected["worker"],
        "scheduler_replicas": service_replicas["scheduler"] == expected["scheduler"],
        "mysql_available": service_replicas["mysql"] >= expected["mysql"],
        "redis_available": service_replicas["redis"] >= expected["redis"],
    }
    budget = build_capacity_budget(profile)
    checks["database_pool_budget"] = budget["remaining_connections"] >= 0
    ready = all(checks.values())
    return {
        "schema": SCHEMA,
        "status": "passed" if ready else "blocked",
        "environment": "staging",
        "synthetic_data_only": True,
        "observed_at": format_utc(observed_at or datetime.now(timezone.utc)),
        "collector_version": PREFLIGHT_VERSION,
        "service_replicas": service_replicas,
        "expected_replicas": expected,
        "capacity_budget": budget,
        "checks": checks,
        "ready_for_target_execution": ready,
        "limitations": [name for name, passed in checks.items() if not passed],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect a sanitized Staging topology/capacity preflight")
    parser.add_argument("--profile", type=Path, default=Path("infra/staging/readiness-profile.example.json"))
    parser.add_argument("--compose-file", action="append", dest="compose_files", default=[])
    parser.add_argument("--project-directory")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-blocked", action="store_true")
    args = parser.parse_args()
    compose_files = args.compose_files or ["docker-compose.yml"]
    try:
        counts, _ = discover_service_counts(SubprocessRunner(), compose_files, args.project_directory)
        report = build_topology_preflight(load_json(args.profile), counts)
        write_json(args.output, report)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["ready_for_target_execution"] or args.allow_blocked else 1
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"Staging topology preflight failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
