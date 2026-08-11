from __future__ import annotations

import argparse
import json
import math
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA = "staging-resource-samples-v1"
ASSEMBLER_VERSION = "1.0.0"
RESOURCE_SCHEMA = "staging-resource-observation-v1"
PROBE_SCHEMA = "multi-instance-stability-probe-v2"
EVENT_SCHEMA = "staging-worker-recovery-events-v1"
RESOURCE_NAMES = ("api", "worker", "mysql", "redis")
OPERATION_NAMES = ("api", "mysql", "redis", "celery")
EVIDENCE_KINDS = {"contract-fixture", "target-observation", "target-execution"}
SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|authorization|cookie|api[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"(://[^/\s:@]+:[^@\s]+@|(?:password|passwd|secret|token|api[_-]?key)=)",
    re.IGNORECASE,
)
CONTAINER_IDENTITY_RE = re.compile(r"container(_|-)?(id|name)|container_identity", re.IGNORECASE)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} root must be an object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{name} must use an explicit UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must use UTC")
    return parsed


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def require_number(value: Any, name: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return number


def walk_for_sensitive_values(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            text_key = str(key)
            if SECRET_KEY_RE.search(text_key):
                raise ValueError(f"secret-like field is not allowed: {path}.{text_key}")
            if CONTAINER_IDENTITY_RE.search(text_key):
                raise ValueError(f"container identity field is not allowed: {path}.{text_key}")
            walk_for_sensitive_values(item, f"{path}.{text_key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            walk_for_sensitive_values(item, f"{path}[{index}]")
    elif isinstance(value, str) and SECRET_VALUE_RE.search(value):
        raise ValueError(f"credential-like value is not allowed at {path}")


def successive_pairs(values: list[datetime]) -> list[tuple[datetime, datetime]]:
    return list(zip(values, values[1:]))  # noqa: RUF007 - target host Python 3.9


def validate_source_shape(source: dict[str, Any]) -> dict[str, Any]:
    if source.get("schema") != SCHEMA:
        raise ValueError("unexpected stability session schema")
    if source.get("environment") != "staging":
        raise ValueError("environment must be staging")
    if source.get("synthetic_data_only") is not True:
        raise ValueError("stability session must use synthetic data only")
    evidence_kind = source.get("evidence_kind")
    if evidence_kind not in EVIDENCE_KINDS:
        raise ValueError("unsupported evidence_kind")
    started = parse_utc(source.get("started_at"), "started_at")
    finished = parse_utc(source.get("finished_at"), "finished_at")
    if finished <= started:
        raise ValueError("finished_at must be later than started_at")
    clock = source.get("clock")
    if not isinstance(clock, dict) or clock.get("timezone") != "UTC":
        raise ValueError("clock.timezone must be UTC")
    maximum_skew = require_number(clock.get("maximum_skew_seconds"), "clock.maximum_skew_seconds")
    observed_skew = require_number(clock.get("observed_skew_seconds"), "clock.observed_skew_seconds")
    if maximum_skew > 30 or observed_skew > maximum_skew:
        raise ValueError("clock skew exceeds the allowed boundary")

    samples = source.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("samples cannot be empty")
    sample_times: list[datetime] = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise TypeError(f"samples[{index}] must be an object")
        observed = parse_utc(sample.get("observed_at"), f"samples[{index}].observed_at")
        if not started <= observed <= finished:
            raise ValueError(f"samples[{index}] falls outside the session timeline")
        sample_times.append(observed)
        sample_counts = sample.get("service_container_counts")
        if sample_counts is not None:
            if not isinstance(sample_counts, dict) or set(sample_counts) != set(RESOURCE_NAMES):
                raise ValueError(
                    f"samples[{index}].service_container_counts must cover API, Worker, MySQL and Redis"
                )
            for name in RESOURCE_NAMES:
                if int(require_number(sample_counts.get(name), f"samples[{index}].service_container_counts.{name}")) < 1:
                    raise ValueError(
                        f"samples[{index}].service_container_counts.{name} must be at least one"
                    )
        resources = sample.get("resources")
        if not isinstance(resources, dict) or set(resources) != set(RESOURCE_NAMES):
            raise ValueError(f"samples[{index}] must cover API, Worker, MySQL and Redis")
        for name in RESOURCE_NAMES:
            resource = resources[name]
            if not isinstance(resource, dict):
                raise TypeError(f"samples[{index}].resources.{name} must be an object")
            require_number(resource.get("cpu_percent"), f"samples[{index}].resources.{name}.cpu_percent")
            require_number(resource.get("memory_mebibytes"), f"samples[{index}].resources.{name}.memory_mebibytes")
        require_number(sample.get("database_connections"), f"samples[{index}].database_connections")
        require_number(sample.get("celery_queue_depth"), f"samples[{index}].celery_queue_depth")
    if any(current <= previous for previous, current in successive_pairs(sample_times)):
        raise ValueError("resource sample timestamps must be strictly increasing")

    windows = source.get("probe_windows")
    if not isinstance(windows, list) or not windows:
        raise ValueError("probe_windows cannot be empty")
    previous_finished: Optional[datetime] = None  # noqa: UP045 - target host Python 3.9
    for index, window in enumerate(windows):
        if not isinstance(window, dict):
            raise TypeError(f"probe_windows[{index}] must be an object")
        window_started = parse_utc(window.get("started_at"), f"probe_windows[{index}].started_at")
        window_finished = parse_utc(window.get("finished_at"), f"probe_windows[{index}].finished_at")
        if not started <= window_started < window_finished <= finished:
            raise ValueError(f"probe_windows[{index}] falls outside the session timeline")
        if previous_finished is not None and window_started < previous_finished:
            raise ValueError("probe windows cannot overlap")
        previous_finished = window_finished
        operations = window.get("operations")
        if not isinstance(operations, dict) or set(operations) != set(OPERATION_NAMES):
            raise ValueError(f"probe_windows[{index}] must cover all operation types")
        for name in OPERATION_NAMES:
            operation = operations[name]
            if not isinstance(operation, dict):
                raise TypeError(f"probe_windows[{index}].operations.{name} must be an object")
            count = int(require_number(operation.get("count"), f"probe_windows[{index}].operations.{name}.count"))
            errors = int(require_number(operation.get("error_count"), f"probe_windows[{index}].operations.{name}.error_count"))
            consecutive = int(require_number(operation.get("max_consecutive_errors"), f"probe_windows[{index}].operations.{name}.max_consecutive_errors"))
            require_number(operation.get("p95_ms"), f"probe_windows[{index}].operations.{name}.p95_ms")
            if errors > count or consecutive > errors:
                raise ValueError(f"probe_windows[{index}].operations.{name} error counters are invalid")

    events = source.get("events")
    if not isinstance(events, list) or len(events) != 2:
        raise ValueError("events must contain one Worker loss and recovery")
    event_types: list[str] = []
    event_times: list[datetime] = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise TypeError(f"events[{index}] must be an object")
        event_types.append(str(event.get("type")))
        observed = parse_utc(event.get("observed_at"), f"events[{index}].observed_at")
        if not started <= observed <= finished:
            raise ValueError(f"events[{index}] falls outside the session timeline")
        event_times.append(observed)
    if event_types != ["worker_lost", "worker_recovered"] or event_times[1] <= event_times[0]:
        raise ValueError("Worker loss and recovery events must be ordered")
    walk_for_sensitive_values(source)
    return {
        "started": started,
        "finished": finished,
        "sample_times": sample_times,
        "evidence_kind": evidence_kind,
    }


def evaluate_eligibility(source: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    shape = validate_source_shape(source)
    stability = profile.get("stability")
    topology = profile.get("topology")
    pool = profile.get("database_pool")
    limits = profile.get("resource_limits")
    if not all(isinstance(value, dict) for value in (stability, topology, pool, limits)):
        raise TypeError("staging profile is missing required sections")
    duration = int((shape["finished"] - shape["started"]).total_seconds())
    interval = int(source.get("sample_interval_seconds", 0))
    expected_interval = int(stability["resource_sample_interval_seconds"])
    sample_times = shape["sample_times"]
    expected_samples = math.floor(duration / expected_interval) + 1
    coverage = min(100.0, round(len(sample_times) / expected_samples * 100, 3))
    gaps = [(current - previous).total_seconds() for previous, current in successive_pairs(sample_times)]
    maximum_gap = max(gaps) if gaps else duration

    totals = {
        name: {"count": 0, "errors": 0, "max_consecutive_errors": 0, "p95_ms": 0.0}
        for name in OPERATION_NAMES
    }
    for window in source["probe_windows"]:
        for name in OPERATION_NAMES:
            operation = window["operations"][name]
            totals[name]["count"] += int(operation["count"])
            totals[name]["errors"] += int(operation["error_count"])
            totals[name]["max_consecutive_errors"] = max(
                totals[name]["max_consecutive_errors"], int(operation["max_consecutive_errors"])
            )
            totals[name]["p95_ms"] = max(totals[name]["p95_ms"], float(operation["p95_ms"]))
    total_operations = sum(value["count"] for value in totals.values())
    total_errors = sum(value["errors"] for value in totals.values())
    error_rate = round(total_errors / total_operations * 100, 6) if total_operations else 100.0

    event_summary = source.get("worker_event_summary", {})
    initial_workers = int(event_summary.get("initial_workers", 0)) if isinstance(event_summary, dict) else 0
    degraded_workers = int(event_summary.get("degraded_workers", 0)) if isinstance(event_summary, dict) else 0
    recovered_workers = int(event_summary.get("recovered_workers", 0)) if isinstance(event_summary, dict) else 0
    required_workers = int(topology["worker_replicas"])

    resource_ok = True
    for sample in source["samples"]:
        for name in RESOURCE_NAMES:
            resource_ok = resource_ok and float(sample["resources"][name]["cpu_percent"]) <= float(limits[name]["max_cpu_percent"])
            resource_ok = resource_ok and float(sample["resources"][name]["memory_mebibytes"]) <= float(limits[name]["max_memory_mebibytes"])
    mysql_allowed = math.floor(
        (int(pool["mysql_max_connections"]) - int(pool["reserved_connections"]))
        * int(pool["max_budget_utilization_percent"])
        / 100
    )
    connection_peak = max(int(sample["database_connections"]) for sample in source["samples"])
    final_queue_depth = int(source["samples"][-1]["celery_queue_depth"])

    checks: dict[str, bool] = {
        "duration": duration >= int(stability["duration_seconds"]),
        "sample_interval": interval == expected_interval,
        "sample_coverage": coverage >= 95 and maximum_gap <= expected_interval * 2,
        "error_rate": error_rate <= float(stability["max_error_rate_percent"]),
        "max_consecutive_errors": max(value["max_consecutive_errors"] for value in totals.values()) <= int(stability["max_consecutive_errors"]),
        "operation_minimums": all(totals[name]["count"] >= int(stability["minimum_operations"][name]) for name in OPERATION_NAMES),
        "operation_p95": all(totals[name]["p95_ms"] <= float(stability["p95_limits_ms"][name]) for name in OPERATION_NAMES),
        "worker_loss_recovery": initial_workers >= required_workers and degraded_workers == initial_workers - 1 and recovered_workers >= initial_workers,
        "resource_limits": resource_ok,
        "database_connections": connection_peak <= mysql_allowed,
        "queue_drained": final_queue_depth == 0,
    }
    return {
        "eligible": all(checks.values()),
        "checks": checks,
        "duration_seconds": duration,
        "coverage_percent": coverage,
        "maximum_sample_gap_seconds": maximum_gap,
        "error_rate_percent": error_rate,
        "operation_totals": totals,
        "database_connection_peak": connection_peak,
        "database_connection_allowed": mysql_allowed,
        "final_queue_depth": final_queue_depth,
    }


def assemble_session(
    resource: dict[str, Any],
    probe: dict[str, Any],
    worker_events: dict[str, Any],
    profile: dict[str, Any],
    *,
    request_target_execution: bool,
    execution_group_id: Optional[str] = None,  # noqa: UP045 - target host Python 3.9
    execution_id: Optional[str] = None,  # noqa: UP045 - target host Python 3.9
    observed_clock_skew_seconds: float = 0,
) -> dict[str, Any]:
    if resource.get("schema") != RESOURCE_SCHEMA or resource.get("status") != "passed":
        raise ValueError("resource observation did not pass")
    if probe.get("schema") != PROBE_SCHEMA:
        raise ValueError("operation probe must use multi-instance-stability-probe-v2")
    if worker_events.get("schema") != EVENT_SCHEMA or worker_events.get("status") != "passed":
        raise ValueError("Worker recovery event report did not pass")
    started = parse_utc(resource.get("started_at"), "resource.started_at")
    finished = parse_utc(resource.get("finished_at"), "resource.finished_at")
    probe_started = parse_utc(probe.get("started_at"), "probe.started_at")
    probe_finished = parse_utc(probe.get("finished_at"), "probe.finished_at")
    if probe_started < started or probe_finished > finished:
        raise ValueError("operation probe timeline must be contained by resource observation")
    event_rows = worker_events.get("events")
    if not isinstance(event_rows, list):
        raise TypeError("worker event report events must be an array")
    events = [
        {"type": row.get("type"), "observed_at": row.get("observed_at")}
        for row in event_rows
        if isinstance(row, dict)
    ]
    summary = worker_events.get("summary")
    if not isinstance(summary, dict):
        raise TypeError("worker event report summary must be an object")
    source: dict[str, Any] = {
        "schema": SCHEMA,
        "evidence_kind": "target-observation",
        "execution_status": "observation-only",
        "eligible_for_target_execution": False,
        "environment": "staging",
        "synthetic_data_only": True,
        "execution_group_id": execution_group_id or f"wp4-staging-{uuid.uuid4().hex}",
        "execution_id": execution_id or f"resource-session-{uuid.uuid4().hex}",
        "source_adapter": "staging-session-orchestrator-v1",
        "collector_version": ASSEMBLER_VERSION,
        "clock": {
            "timezone": "UTC",
            "maximum_skew_seconds": 30,
            "observed_skew_seconds": observed_clock_skew_seconds,
        },
        "started_at": format_utc(started),
        "finished_at": format_utc(finished),
        "sample_interval_seconds": int(resource["sample_interval_seconds"]),
        "samples": resource["samples"],
        "probe_windows": probe["probe_windows"],
        "events": events,
        "worker_event_summary": {
            "initial_workers": int(summary.get("initial_workers", 0)),
            "degraded_workers": int(summary.get("degraded_workers", 0)),
            "recovered_workers": int(summary.get("recovered_workers", 0)),
            "recovery_seconds": float(summary.get("recovery_seconds", 0)),
        },
    }
    evaluation = evaluate_eligibility(source, profile)
    source["eligibility"] = evaluation
    if request_target_execution and evaluation["eligible"]:
        source["evidence_kind"] = "target-execution"
        source["execution_status"] = "target-execution"
        source["eligible_for_target_execution"] = True
    else:
        source["limitations"] = [
            name for name, passed in evaluation["checks"].items() if not passed
        ]
    validate_session(source, profile)
    return source


def validate_session(source: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    shape = validate_source_shape(source)
    evaluation = evaluate_eligibility(source, profile)
    evidence_kind = shape["evidence_kind"]
    eligible_flag = source.get("eligible_for_target_execution")
    execution_status = source.get("execution_status")
    if evidence_kind == "target-execution":
        if eligible_flag is not True or execution_status != "target-execution" or not evaluation["eligible"]:
            raise ValueError("target-execution requires every staging eligibility check to pass")
    else:
        if eligible_flag is not False:
            raise ValueError("non-target evidence must not be eligible for target execution")
        if execution_status not in {"observation-only", "contract-only"}:
            raise ValueError("non-target evidence must retain an observation or contract boundary")
    return {
        "schema": "staging-stability-session-verification-v1",
        "status": "passed",
        "evidence_kind": evidence_kind,
        "execution_status": execution_status,
        "eligible_for_target_execution": bool(eligible_flag),
        **evaluation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble a sanitized WP4 Staging stability session source.")
    parser.add_argument("--resource-observation", type=Path, required=True)
    parser.add_argument("--probe-report", type=Path, required=True)
    parser.add_argument("--worker-events", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request-target-execution", action="store_true")
    parser.add_argument("--execution-group-id")
    parser.add_argument("--execution-id")
    parser.add_argument("--observed-clock-skew-seconds", type=float, default=0)
    args = parser.parse_args()
    try:
        source = assemble_session(
            load_json(args.resource_observation),
            load_json(args.probe_report),
            load_json(args.worker_events),
            load_json(args.profile),
            request_target_execution=args.request_target_execution,
            execution_group_id=args.execution_group_id,
            execution_id=args.execution_id,
            observed_clock_skew_seconds=args.observed_clock_skew_seconds,
        )
        write_json(args.output, source)
        print(json.dumps(validate_session(source, load_json(args.profile)), ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"staging stability session assembly failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
