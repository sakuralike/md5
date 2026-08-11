from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

SCHEMA = "staging-resource-observation-v1"
COLLECTOR_VERSION = "1.0.0"
REQUIRED_SERVICES = ("api", "worker", "mysql", "redis")
QUEUE_METRIC_RE = re.compile(
    r"(?m)^password_detective_worker_queue_depth(?:\{[^\n]*\})?\s+([0-9]+(?:\.[0-9]+)?)\s*$"
)
SIZE_UNITS = {
    "b": 1 / (1024 * 1024),
    "kb": 1000 / (1024 * 1024),
    "kib": 1 / 1024,
    "mb": 1_000_000 / (1024 * 1024),
    "mib": 1,
    "gb": 1_000_000_000 / (1024 * 1024),
    "gib": 1024,
    "tb": 1_000_000_000_000 / (1024 * 1024),
    "tib": 1024 * 1024,
}


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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_utc(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def parse_percent(value: str) -> float:
    text = value.strip()
    if not text.endswith("%"):
        raise ValueError(f"invalid percentage: {value}")
    number = float(text[:-1])
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"invalid percentage: {value}")
    return round(number, 3)


def parse_memory_mebibytes(value: str) -> float:
    used = value.split("/", 1)[0].strip()
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)", used)
    if match is None:
        raise ValueError(f"invalid Docker memory value: {value}")
    number = float(match.group(1))
    unit = match.group(2).lower()
    if unit not in SIZE_UNITS:
        raise ValueError(f"unsupported Docker memory unit: {match.group(2)}")
    return round(number * SIZE_UNITS[unit], 3)


def _json_lines(value: str, name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(value.splitlines(), start=1):
        if not line.strip():
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise TypeError(f"{name} line {line_number} must be a JSON object")
        rows.append(parsed)
    if not rows:
        raise ValueError(f"{name} returned no rows")
    return rows


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


def discover_containers(
    runner: Runner,
    compose_files: Sequence[str],
    project_directory: Optional[str],  # noqa: UP045 - target Python 3.9
) -> tuple[dict[str, list[str]], list[str]]:
    prefix = compose_prefix(compose_files, project_directory)
    rows = _json_lines(runner.run([*prefix, "ps", "--format", "json"]), "compose ps")
    containers: dict[str, list[str]] = {service: [] for service in REQUIRED_SERVICES}
    for row in rows:
        service = str(row.get("Service", ""))
        state = str(row.get("State", ""))
        name = str(row.get("Name") or row.get("Names") or "")
        if service in containers and state == "running" and name:
            containers[service].append(name)
    missing = [service for service, names in containers.items() if not names]
    if missing:
        raise ValueError(
            f"required Compose services are not running: {', '.join(missing)}"
        )
    return containers, prefix


def fetch_metrics(url: str, timeout_seconds: int) -> str:
    request = urllib.request.Request(url, headers={"Accept": "text/plain"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        if response.status != 200:
            raise RuntimeError(f"API metrics returned HTTP {response.status}")
        return response.read().decode("utf-8")


def parse_queue_depth(metrics_text: str) -> int:
    match = QUEUE_METRIC_RE.search(metrics_text)
    if match is None:
        raise ValueError(
            "API metrics are missing password_detective_worker_queue_depth"
        )
    return int(float(match.group(1)))


def collect_sample(
    runner: Runner,
    compose_prefix_arguments: Sequence[str],
    containers: dict[str, list[str]],
    metrics_url: str,
    timeout_seconds: int,
    now: Callable[[], datetime] = _utc_now,
    metrics_fetcher: Callable[[str, int], str] = fetch_metrics,
) -> dict[str, Any]:
    names = [name for service in REQUIRED_SERVICES for name in containers[service]]
    stats_rows = _json_lines(
        runner.run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}", *names]
        ),
        "docker stats",
    )
    name_to_service = {
        name: service
        for service, service_names in containers.items()
        for name in service_names
    }
    resources = {
        service: {"cpu_percent": 0.0, "memory_mebibytes": 0.0}
        for service in REQUIRED_SERVICES
    }
    seen: set[str] = set()
    for row in stats_rows:
        name = str(row.get("Name") or row.get("Container") or "")
        service = name_to_service.get(name)
        if service is None:
            continue
        resources[service]["cpu_percent"] += parse_percent(str(row.get("CPUPerc", "")))
        resources[service]["memory_mebibytes"] += parse_memory_mebibytes(
            str(row.get("MemUsage", ""))
        )
        seen.add(name)
    missing_stats = sorted(set(names) - seen)
    if missing_stats:
        raise ValueError(
            f"docker stats omitted {len(missing_stats)} required containers"
        )
    for values in resources.values():
        values["cpu_percent"] = round(values["cpu_percent"], 3)
        values["memory_mebibytes"] = round(values["memory_mebibytes"], 3)

    mysql_command = (
        'MYSQL_PWD="$MYSQL_PASSWORD" mysql -N -B -u"$MYSQL_USER" '
        '"$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM information_schema.PROCESSLIST;"'
    )
    connection_text = runner.run(
        [*compose_prefix_arguments, "exec", "-T", "mysql", "sh", "-lc", mysql_command]
    ).strip()
    try:
        database_connections = int(connection_text.splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise ValueError("MySQL connection probe did not return an integer") from exc
    if database_connections < 0:
        raise ValueError("MySQL connection count cannot be negative")

    queue_depth = parse_queue_depth(metrics_fetcher(metrics_url, timeout_seconds))
    return {
        "observed_at": _format_utc(now()),
        "resources": resources,
        "database_connections": database_connections,
        "celery_queue_depth": queue_depth,
    }


def collect_observation(
    runner: Runner,
    compose_files: Sequence[str],
    project_directory: Optional[str],  # noqa: UP045 - target Python 3.9
    metrics_url: str,
    duration_seconds: int,
    sample_interval_seconds: int,
    timeout_seconds: int,
    now: Callable[[], datetime] = _utc_now,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    metrics_fetcher: Callable[[str, int], str] = fetch_metrics,
) -> dict[str, Any]:
    if duration_seconds < 0:
        raise ValueError("duration_seconds cannot be negative")
    if sample_interval_seconds < 1:
        raise ValueError("sample_interval_seconds must be at least one")
    containers, prefix = discover_containers(runner, compose_files, project_directory)
    requested_samples = max(
        1, math.floor(duration_seconds / sample_interval_seconds) + 1
    )
    started_at = now()
    started_monotonic = monotonic()
    samples: list[dict[str, Any]] = []
    for index in range(requested_samples):
        samples.append(
            collect_sample(
                runner,
                prefix,
                containers,
                metrics_url,
                timeout_seconds,
                now=now,
                metrics_fetcher=metrics_fetcher,
            )
        )
        if index + 1 < requested_samples:
            next_sample_at = started_monotonic + (index + 1) * sample_interval_seconds
            sleeper(max(0.0, next_sample_at - monotonic()))
    finished_at = now()
    return {
        "schema": SCHEMA,
        "status": "passed",
        "evidence_kind": "target-observation",
        "execution_status": "observation-only",
        "eligible_for_target_execution": False,
        "environment": "staging",
        "synthetic_data_only": True,
        "collector_adapter": "docker-stats-api-metrics-v1",
        "collector_version": COLLECTOR_VERSION,
        "started_at": _format_utc(started_at),
        "finished_at": _format_utc(finished_at),
        "requested_duration_seconds": duration_seconds,
        "sample_interval_seconds": sample_interval_seconds,
        "sample_count": len(samples),
        "service_container_counts": {
            service: len(containers[service]) for service in REQUIRED_SERVICES
        },
        "samples": samples,
        "limitations": [
            "operation probe windows are not collected",
            "single Worker loss and recovery are not executed",
            "MySQL and Redis HA failover are not executed",
            "this observation cannot be used as target-execution evidence",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect a redacted WP4 Staging resource observation from Docker and API metrics."
    )
    parser.add_argument("--compose-file", action="append", default=[])
    parser.add_argument("--project-directory")
    parser.add_argument(
        "--api-metrics-url", default="http://127.0.0.1:8000/api/v1/metrics"
    )
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--sample-interval-seconds", type=int, default=15)
    parser.add_argument("--timeout-seconds", type=int, default=15)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            ".local/staging-resource-observation-wp4-iteration-19/resource-observation.json"
        ),
    )
    args = parser.parse_args()
    compose_files = args.compose_file or ["docker-compose.yml"]
    try:
        observation = collect_observation(
            SubprocessRunner(),
            compose_files,
            args.project_directory,
            args.api_metrics_url,
            args.duration_seconds,
            args.sample_interval_seconds,
            args.timeout_seconds,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(observation, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"staging resource observation failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "schema": observation["schema"],
                "status": observation["status"],
                "execution_status": observation["execution_status"],
                "sample_count": observation["sample_count"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
