from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

from verify_staging_execution_evidence import (
    validate_ha_report,
    validate_resource_report,
)
from verify_staging_readiness_profile import normalized_file_sha256, validate_profile

RESOURCE_SOURCE_SCHEMA = "staging-resource-samples-v1"
HA_SOURCE_SCHEMA = "staging-ha-events-v1"
RESOURCE_REPORT_SCHEMA = "staging-resource-trend-report-v1"
HA_REPORT_SCHEMA = "staging-ha-failover-report-v1"
RESOURCE_NAMES = ("api", "worker", "mysql", "redis")
OPERATION_NAMES = ("api", "mysql", "redis", "celery")
EVIDENCE_KINDS = {"contract-fixture", "target-execution"}
SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|authorization|cookie|api[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"(://[^/\s:@]+:[^@\s]+@|(?:password|passwd|secret|token|api[_-]?key)=)",
    re.IGNORECASE,
)
FIXTURE_ADAPTER_RE = re.compile(r"(fixture|synthetic|test|mock)", re.IGNORECASE)
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


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} root must be an object")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{name} must be an array")
    return value


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return value.strip()


def _require_number(value: Any, name: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return number


def _parse_utc(value: Any, name: str) -> datetime:
    text = _require_string(value, name)
    if not text.endswith("Z"):
        raise ValueError(f"{name} must use an explicit UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be UTC")
    return parsed


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _walk_for_secrets(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                raise ValueError(f"secret-like field is not allowed: {path}.{key}")
            _walk_for_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_for_secrets(item, f"{path}[{index}]")
    elif isinstance(value, str) and SECRET_VALUE_RE.search(value):
        raise ValueError(f"credential-like value is not allowed at {path}")


def _validate_common_source(
    source: dict[str, Any], expected_schema: str
) -> tuple[str, str, str]:
    if source.get("schema") != expected_schema:
        raise ValueError(f"unexpected source schema; expected {expected_schema}")
    if source.get("environment") != "staging":
        raise ValueError("source environment must be staging")
    if source.get("synthetic_data_only") is not True:
        raise ValueError("source must be synthetic-data-only")
    evidence_kind = _require_string(source.get("evidence_kind"), "evidence_kind")
    if evidence_kind not in EVIDENCE_KINDS:
        raise ValueError("evidence_kind must be contract-fixture or target-execution")
    execution_group_id = _require_string(
        source.get("execution_group_id"), "execution_group_id"
    )
    execution_id = _require_string(source.get("execution_id"), "execution_id")
    source_adapter = _require_string(source.get("source_adapter"), "source_adapter")
    _require_string(source.get("collector_version"), "collector_version")
    if evidence_kind == "target-execution" and FIXTURE_ADAPTER_RE.search(source_adapter):
        raise ValueError("target-execution cannot use a fixture, synthetic, test or mock adapter")
    clock = _require_object(source.get("clock"), "clock")
    if clock.get("timezone") != "UTC":
        raise ValueError("clock.timezone must be UTC")
    maximum_skew = _require_number(
        clock.get("maximum_skew_seconds"), "clock.maximum_skew_seconds"
    )
    observed_skew = _require_number(
        clock.get("observed_skew_seconds"), "clock.observed_skew_seconds"
    )
    if maximum_skew > 30:
        raise ValueError("clock.maximum_skew_seconds cannot exceed 30")
    if observed_skew > maximum_skew:
        raise ValueError("observed clock skew exceeds the declared maximum")
    _walk_for_secrets(source)
    return evidence_kind, execution_group_id, execution_id


def _nearest_rank_p95(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot calculate p95 from an empty sample set")
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return round(ordered[index], 3)


def _validate_strict_timeline(timestamps: list[datetime], name: str) -> None:
    if any(current <= previous for previous, current in pairwise(timestamps)):
        raise ValueError(f"{name} timestamps must be strictly increasing")


def materialize_resource_report(
    source: dict[str, Any], profile: dict[str, Any], profile_sha256: str, source_sha256: str
) -> dict[str, Any]:
    evidence_kind, execution_group_id, execution_id = _validate_common_source(
        source, RESOURCE_SOURCE_SCHEMA
    )
    stability = _require_object(profile.get("stability"), "profile.stability")
    accounting = _require_object(
        profile.get("resource_accounting"), "profile.resource_accounting"
    )
    if accounting.get("cpu_scope") != "per-running-replica-average":
        raise ValueError("unsupported CPU resource accounting scope")
    if accounting.get("memory_scope") != "service-aggregate":
        raise ValueError("unsupported memory resource accounting scope")
    started = _parse_utc(source.get("started_at"), "started_at")
    finished = _parse_utc(source.get("finished_at"), "finished_at")
    duration = int((finished - started).total_seconds())
    required_duration = int(stability["duration_seconds"])
    if duration < required_duration:
        raise ValueError(f"source timeline must cover at least {required_duration} seconds")

    configured_interval = int(stability["resource_sample_interval_seconds"])
    samples = _require_list(source.get("samples"), "samples")
    if not samples:
        raise ValueError("samples cannot be empty")
    sample_times: list[datetime] = []
    resource_values: dict[str, dict[str, list[float]]] = {
        name: {"cpu": [], "memory": []} for name in RESOURCE_NAMES
    }
    connection_values: list[int] = []
    queue_values: list[int] = []
    for index, raw_sample in enumerate(samples):
        sample = _require_object(raw_sample, f"samples[{index}]")
        observed = _parse_utc(sample.get("observed_at"), f"samples[{index}].observed_at")
        if observed < started or observed > finished:
            raise ValueError(f"samples[{index}] falls outside the execution timeline")
        sample_times.append(observed)
        resources = _require_object(sample.get("resources"), f"samples[{index}].resources")
        if set(resources) != set(RESOURCE_NAMES):
            raise ValueError(f"samples[{index}] must cover API, Worker, MySQL and Redis")
        replica_counts = _require_object(
            sample.get("service_container_counts"),
            f"samples[{index}].service_container_counts",
        )
        if set(replica_counts) != set(RESOURCE_NAMES):
            raise ValueError(
                f"samples[{index}].service_container_counts must cover all resources"
            )
        for name in RESOURCE_NAMES:
            resource = _require_object(resources[name], f"samples[{index}].resources.{name}")
            replica_count = int(
                _require_number(
                    replica_counts.get(name),
                    f"samples[{index}].service_container_counts.{name}",
                )
            )
            if replica_count < 1:
                raise ValueError(
                    f"samples[{index}].service_container_counts.{name} must be at least one"
                )
            aggregate_cpu = _require_number(
                resource.get("cpu_percent"),
                f"samples[{index}].resources.{name}.cpu_percent",
            )
            resource_values[name]["cpu"].append(aggregate_cpu / replica_count)
            resource_values[name]["memory"].append(
                _require_number(
                    resource.get("memory_mebibytes"),
                    f"samples[{index}].resources.{name}.memory_mebibytes",
                )
            )
        connection_values.append(
            int(_require_number(sample.get("database_connections"), f"samples[{index}].database_connections"))
        )
        queue_values.append(
            int(_require_number(sample.get("celery_queue_depth"), f"samples[{index}].celery_queue_depth"))
        )
    _validate_strict_timeline(sample_times, "resource sample")
    if sample_times[0] > started + timedelta(seconds=configured_interval):
        raise ValueError("resource samples start too late")
    if sample_times[-1] < finished - timedelta(seconds=configured_interval):
        raise ValueError("resource samples finish too early")
    maximum_gap = max(
        (current - previous).total_seconds()
        for previous, current in pairwise(sample_times)
    ) if len(sample_times) > 1 else duration
    if maximum_gap > configured_interval * 2:
        raise ValueError("resource sample gap exceeds twice the configured interval")
    expected_samples = math.floor(duration / configured_interval) + 1
    coverage = min(100.0, round(len(samples) / expected_samples * 100, 3))
    if coverage < 95:
        raise ValueError("resource sample coverage is below 95 percent")

    probe_windows = _require_list(source.get("probe_windows"), "probe_windows")
    if not probe_windows:
        raise ValueError("probe_windows cannot be empty")
    operation_totals = {
        name: {"count": 0, "errors": 0, "max_consecutive_errors": 0, "p95_ms": 0.0}
        for name in OPERATION_NAMES
    }
    previous_window_end: datetime | None = None
    for index, raw_window in enumerate(probe_windows):
        window = _require_object(raw_window, f"probe_windows[{index}]")
        window_started = _parse_utc(window.get("started_at"), f"probe_windows[{index}].started_at")
        window_finished = _parse_utc(window.get("finished_at"), f"probe_windows[{index}].finished_at")
        if not started <= window_started < window_finished <= finished:
            raise ValueError(f"probe_windows[{index}] falls outside the execution timeline")
        if previous_window_end is not None and window_started < previous_window_end:
            raise ValueError("probe windows cannot overlap")
        previous_window_end = window_finished
        operations = _require_object(window.get("operations"), f"probe_windows[{index}].operations")
        if set(operations) != set(OPERATION_NAMES):
            raise ValueError(f"probe_windows[{index}] must cover all operation types")
        for name in OPERATION_NAMES:
            operation = _require_object(operations[name], f"probe_windows[{index}].operations.{name}")
            count = int(_require_number(operation.get("count"), f"probe_windows[{index}].operations.{name}.count"))
            errors = int(_require_number(operation.get("error_count"), f"probe_windows[{index}].operations.{name}.error_count"))
            consecutive = int(
                _require_number(
                    operation.get("max_consecutive_errors"),
                    f"probe_windows[{index}].operations.{name}.max_consecutive_errors",
                )
            )
            if errors > count:
                raise ValueError(f"probe_windows[{index}].operations.{name} has more errors than operations")
            p95 = _require_number(operation.get("p95_ms"), f"probe_windows[{index}].operations.{name}.p95_ms")
            totals = operation_totals[name]
            totals["count"] += count
            totals["errors"] += errors
            totals["max_consecutive_errors"] = max(totals["max_consecutive_errors"], consecutive)
            totals["p95_ms"] = max(totals["p95_ms"], p95)

    events = _require_list(source.get("events"), "events")
    event_times: list[datetime] = []
    event_types: list[str] = []
    for index, raw_event in enumerate(events):
        event = _require_object(raw_event, f"events[{index}]")
        event_type = _require_string(event.get("type"), f"events[{index}].type")
        observed = _parse_utc(event.get("observed_at"), f"events[{index}].observed_at")
        if observed < started or observed > finished:
            raise ValueError(f"events[{index}] falls outside the execution timeline")
        event_types.append(event_type)
        event_times.append(observed)
    _validate_strict_timeline(event_times, "resource event")
    if event_types != ["worker_lost", "worker_recovered"]:
        raise ValueError("resource events must contain one ordered Worker loss and recovery")

    total_operations = sum(int(value["count"]) for value in operation_totals.values())
    total_errors = sum(int(value["errors"]) for value in operation_totals.values())
    error_rate = round(total_errors / total_operations * 100, 6) if total_operations else 100.0
    max_consecutive_errors = max(
        int(value["max_consecutive_errors"]) for value in operation_totals.values()
    )
    resource_summary: dict[str, Any] = {}
    for name in RESOURCE_NAMES:
        cpu_values = resource_values[name]["cpu"]
        memory_values = resource_values[name]["memory"]
        resource_summary[name] = {
            "cpu_percent": {"p95": _nearest_rank_p95(cpu_values), "max": max(cpu_values)},
            "memory_mebibytes": {
                "p95": _nearest_rank_p95(memory_values),
                "max": max(memory_values),
            },
        }

    pool = _require_object(profile.get("database_pool"), "profile.database_pool")
    mysql_max = int(pool["mysql_max_connections"])
    reserved = int(pool["reserved_connections"])
    allowed = math.floor(
        (mysql_max - reserved) * int(pool["max_budget_utilization_percent"]) / 100
    )
    connection_peak = max(connection_values)
    provenance = {
        "execution_group_id": execution_group_id,
        "execution_id": execution_id,
        "source_adapter": source["source_adapter"],
        "collector_version": source["collector_version"],
        "source_sha256": source_sha256,
        "clock": source["clock"],
        "maximum_sample_gap_seconds": maximum_gap,
    }
    return {
        "schema": RESOURCE_REPORT_SCHEMA,
        "evidence_kind": evidence_kind,
        "status": "passed",
        "environment": "staging",
        "synthetic_data_only": True,
        "profile_sha256": profile_sha256,
        "started_at": _format_utc(started),
        "finished_at": _format_utc(finished),
        "duration_seconds": duration,
        "sample_interval_seconds": configured_interval,
        "sample_count": len(samples),
        "coverage_percent": coverage,
        "single_worker_loss": True,
        "error_rate_percent": error_rate,
        "max_consecutive_errors": max_consecutive_errors,
        "resource_accounting": accounting,
        "operations": {
            name: {
                "count": int(operation_totals[name]["count"]),
                "p95_ms": operation_totals[name]["p95_ms"],
            }
            for name in OPERATION_NAMES
        },
        "resources": resource_summary,
        "database_connections": {
            "peak": connection_peak,
            "allowed": allowed,
            "remaining_at_peak": mysql_max - connection_peak,
        },
        "celery_queue": {"peak_depth": max(queue_values), "final_depth": queue_values[-1]},
        "provenance": provenance,
    }


def materialize_ha_report(
    source: dict[str, Any],
    profile: dict[str, Any],
    profile_sha256: str,
    source_sha256: str,
    dependency: str,
) -> dict[str, Any]:
    evidence_kind, execution_group_id, execution_id = _validate_common_source(
        source, HA_SOURCE_SCHEMA
    )
    if dependency not in REQUIRED_HA_CHECKS:
        raise ValueError(f"unsupported HA dependency: {dependency}")
    if source.get("dependency") != dependency:
        raise ValueError(f"HA source dependency must be {dependency}")
    expected = _require_object(
        _require_object(profile.get("high_availability"), "profile.high_availability").get(dependency),
        f"profile.high_availability.{dependency}",
    )
    if source.get("mode") != expected["mode"]:
        raise ValueError(f"{dependency} HA mode does not match the profile")
    started = _parse_utc(source.get("started_at"), f"{dependency}.started_at")
    finished = _parse_utc(source.get("finished_at"), f"{dependency}.finished_at")
    if finished <= started:
        raise ValueError(f"{dependency} HA finish must be after start")

    events = _require_list(source.get("events"), f"{dependency}.events")
    required_types = REQUIRED_HA_CHECKS[dependency] | {"failover_triggered"}
    by_type: dict[str, dict[str, Any]] = {}
    timestamps: list[datetime] = []
    for index, raw_event in enumerate(events):
        event = _require_object(raw_event, f"{dependency}.events[{index}]")
        event_type = _require_string(event.get("type"), f"{dependency}.events[{index}].type")
        if event_type in by_type:
            raise ValueError(f"duplicate {dependency} HA event: {event_type}")
        if event_type not in required_types:
            raise ValueError(f"unexpected {dependency} HA event: {event_type}")
        observed = _parse_utc(
            event.get("observed_at"), f"{dependency}.events[{index}].observed_at"
        )
        if not started <= observed <= finished:
            raise ValueError(f"{dependency}.events[{index}] falls outside the HA timeline")
        if event_type != "failover_triggered" and event.get("status") != "passed":
            raise ValueError(f"{dependency} HA check did not pass: {event_type}")
        by_type[event_type] = {"event": event, "observed": observed}
        timestamps.append(observed)
    _validate_strict_timeline(timestamps, f"{dependency} HA event")
    missing = required_types - set(by_type)
    if missing:
        raise ValueError(f"{dependency} HA events missing: {', '.join(sorted(missing))}")

    triggered = by_type["failover_triggered"]["observed"]
    failover_observed = by_type["failover_observed"]["observed"]
    primary_changed = by_type["primary_changed"]["observed"]
    recovered = by_type["application_readiness_recovered"]["observed"]
    rollback_ready = by_type["rollback_ready"]["observed"]
    if not started <= triggered <= failover_observed <= primary_changed <= recovered <= rollback_ready <= finished:
        raise ValueError(f"{dependency} HA lifecycle events are not ordered")

    last_durable = _parse_utc(
        source.get("last_confirmed_durable_at"), f"{dependency}.last_confirmed_durable_at"
    )
    recovery_point = _parse_utc(
        source.get("recovery_point_at"), f"{dependency}.recovery_point_at"
    )
    if last_durable > triggered or recovery_point > recovered:
        raise ValueError(f"{dependency} durability timestamps fall outside failover recovery")
    rto = round((recovered - triggered).total_seconds(), 3)
    rpo = round(abs((recovery_point - last_durable).total_seconds()), 3)
    lost_records = int(_require_number(source.get("lost_records"), f"{dependency}.lost_records"))
    checks = {name: {"status": "passed"} for name in sorted(REQUIRED_HA_CHECKS[dependency])}
    return {
        "schema": HA_REPORT_SCHEMA,
        "evidence_kind": evidence_kind,
        "status": "passed",
        "environment": "staging",
        "synthetic_data_only": True,
        "profile_sha256": profile_sha256,
        "dependency": dependency,
        "mode": expected["mode"],
        "started_at": _format_utc(started),
        "failover_triggered_at": _format_utc(triggered),
        "recovered_at": _format_utc(recovered),
        "finished_at": _format_utc(finished),
        "rto_seconds": rto,
        "rpo_seconds": rpo,
        "lost_records": lost_records,
        "checks": checks,
        "provenance": {
            "execution_group_id": execution_group_id,
            "execution_id": execution_id,
            "source_adapter": source["source_adapter"],
            "collector_version": source["collector_version"],
            "source_sha256": source_sha256,
            "clock": source["clock"],
            "event_count": len(events),
        },
    }


def _fixture_common(evidence_kind: str, execution_id: str) -> dict[str, Any]:
    return {
        "evidence_kind": evidence_kind,
        "environment": "staging",
        "synthetic_data_only": True,
        "execution_group_id": "wp4-iteration-14-contract",
        "execution_id": execution_id,
        "source_adapter": "contract-fixture-generator-v1",
        "collector_version": "1.0.0",
        "clock": {
            "timezone": "UTC",
            "maximum_skew_seconds": 5,
            "observed_skew_seconds": 0,
        },
    }


def generate_contract_sources(directory: Path, profile: dict[str, Any]) -> tuple[Path, Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 8, 10, 0, 0, tzinfo=UTC)
    duration = int(profile["stability"]["duration_seconds"])
    interval = int(profile["stability"]["resource_sample_interval_seconds"])
    finish = start + timedelta(seconds=duration)
    samples: list[dict[str, Any]] = []
    for offset in range(0, duration + 1, interval):
        observed = start + timedelta(seconds=offset)
        wave = (offset // interval) % 20
        samples.append(
            {
                "observed_at": _format_utc(observed),
                "service_container_counts": {
                    "api": int(profile["topology"]["api_replicas"]),
                    "worker": int(profile["topology"]["worker_replicas"]),
                    "mysql": 1,
                    "redis": 1,
                },
                "resources": {
                    "api": {"cpu_percent": (42 + wave / 2) * int(profile["topology"]["api_replicas"]), "memory_mebibytes": 480 + wave},
                    "worker": {"cpu_percent": (46 + wave / 2) * int(profile["topology"]["worker_replicas"]), "memory_mebibytes": 540 + wave},
                    "mysql": {"cpu_percent": 38 + wave / 3, "memory_mebibytes": 1240 + wave * 2},
                    "redis": {"cpu_percent": 26 + wave / 4, "memory_mebibytes": 490 + wave},
                },
                "database_connections": 82 + wave // 4,
                "celery_queue_depth": 0 if offset == duration else wave,
            }
        )
    minimum_operations = profile["stability"]["minimum_operations"]
    windows: list[dict[str, Any]] = []
    for hour in range(4):
        window_start = start + timedelta(hours=hour)
        window_finish = min(finish, window_start + timedelta(hours=1))
        operations = {}
        for name, p95 in {"api": 184.2, "mysql": 92.4, "redis": 18.6, "celery": 612.5}.items():
            operations[name] = {
                "count": math.ceil(int(minimum_operations[name]) / 4),
                "error_count": 0,
                "max_consecutive_errors": 0,
                "p95_ms": p95,
            }
        windows.append(
            {
                "started_at": _format_utc(window_start),
                "finished_at": _format_utc(window_finish),
                "operations": operations,
            }
        )
    resource_source = {
        "schema": RESOURCE_SOURCE_SCHEMA,
        **_fixture_common("contract-fixture", "wp4-iteration-14-resource-contract"),
        "started_at": _format_utc(start),
        "finished_at": _format_utc(finish),
        "samples": samples,
        "probe_windows": windows,
        "events": [
            {"type": "worker_lost", "observed_at": _format_utc(start + timedelta(hours=2))},
            {"type": "worker_recovered", "observed_at": _format_utc(start + timedelta(hours=2, seconds=30))},
        ],
    }

    def build_ha_source(dependency: str, ha_start: datetime) -> dict[str, Any]:
        check_order = (
            [
                "preflight_health",
                "failover_triggered",
                "failover_observed",
                "primary_changed",
                "application_readiness_recovered",
            ]
            + sorted(
                REQUIRED_HA_CHECKS[dependency]
                - {
                    "preflight_health",
                    "failover_observed",
                    "primary_changed",
                    "application_readiness_recovered",
                    "rollback_ready",
                }
            )
            + ["rollback_ready"]
        )
        offsets = {
            "preflight_health": 0,
            "failover_triggered": 60,
            "failover_observed": 62,
            "primary_changed": 70,
            "application_readiness_recovered": 102 if dependency == "mysql" else 88,
        }
        current_offset = offsets["application_readiness_recovered"]
        events: list[dict[str, Any]] = []
        for event_type in check_order:
            if event_type not in offsets:
                current_offset += 2
                offsets[event_type] = current_offset
            event = {"type": event_type, "observed_at": _format_utc(ha_start + timedelta(seconds=offsets[event_type]))}
            if event_type != "failover_triggered":
                event["status"] = "passed"
            events.append(event)
        return {
            "schema": HA_SOURCE_SCHEMA,
            **_fixture_common("contract-fixture", f"wp4-iteration-14-{dependency}-contract"),
            "dependency": dependency,
            "mode": profile["high_availability"][dependency]["mode"],
            "started_at": _format_utc(ha_start),
            "finished_at": _format_utc(ha_start + timedelta(minutes=4)),
            "last_confirmed_durable_at": _format_utc(ha_start + timedelta(seconds=59)),
            "recovery_point_at": _format_utc(ha_start + timedelta(seconds=59)),
            "lost_records": 0,
            "events": events,
        }

    resource_path = directory / "resource-source.json"
    mysql_path = directory / "mysql-ha-source.json"
    redis_path = directory / "redis-ha-source.json"
    _write_json(resource_path, resource_source)
    _write_json(mysql_path, build_ha_source("mysql", finish + timedelta(minutes=10)))
    _write_json(redis_path, build_ha_source("redis", finish + timedelta(minutes=20)))
    return resource_path, mysql_path, redis_path


def materialize_bundle(
    profile_path: Path,
    resource_source_path: Path,
    mysql_source_path: Path,
    redis_source_path: Path,
    output_directory: Path,
) -> dict[str, Path]:
    profile = _load_json(profile_path)
    validate_profile(profile, profile_path.resolve().parents[2])
    profile_sha256 = normalized_file_sha256(profile_path)
    resource_source = _load_json(resource_source_path)
    mysql_source = _load_json(mysql_source_path)
    redis_source = _load_json(redis_source_path)
    kinds = {
        resource_source.get("evidence_kind"),
        mysql_source.get("evidence_kind"),
        redis_source.get("evidence_kind"),
    }
    if len(kinds) != 1:
        raise ValueError("all source files must use the same evidence_kind")
    execution_group_ids = {
        resource_source.get("execution_group_id"),
        mysql_source.get("execution_group_id"),
        redis_source.get("execution_group_id"),
    }
    if len(execution_group_ids) != 1 or any(
        not isinstance(value, str) or not value for value in execution_group_ids
    ):
        raise ValueError("all source files must share one execution_group_id")
    resource_report = materialize_resource_report(
        resource_source, profile, profile_sha256, _sha256(resource_source_path)
    )
    mysql_report = materialize_ha_report(
        mysql_source, profile, profile_sha256, _sha256(mysql_source_path), "mysql"
    )
    redis_report = materialize_ha_report(
        redis_source, profile, profile_sha256, _sha256(redis_source_path), "redis"
    )
    validate_resource_report(resource_report, profile, profile_sha256)
    validate_ha_report(mysql_report, profile, profile_sha256, "mysql")
    validate_ha_report(redis_report, profile, profile_sha256, "redis")
    output_directory.mkdir(parents=True, exist_ok=True)
    source_manifest = output_directory / "source-checksums.sha256"
    source_manifest.write_text(
        "\n".join(
            [
                f"{_sha256(resource_source_path)}  {resource_source_path.name}",
                f"{_sha256(mysql_source_path)}  {mysql_source_path.name}",
                f"{_sha256(redis_source_path)}  {redis_source_path.name}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    paths = {
        "resource": output_directory / "resource-trend-report.json",
        "mysql": output_directory / "mysql-ha-failover-report.json",
        "redis": output_directory / "redis-ha-failover-report.json",
    }
    _write_json(paths["resource"], resource_report)
    _write_json(paths["mysql"], mysql_report)
    _write_json(paths["redis"], redis_report)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize sanitized WP4 staging resource and HA adapter evidence."
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--emit-contract-sources", type=Path)
    parser.add_argument("--resource-source", type=Path)
    parser.add_argument("--mysql-source", type=Path)
    parser.add_argument("--redis-source", type=Path)
    parser.add_argument("--output-directory", type=Path)
    args = parser.parse_args()
    try:
        profile = _load_json(args.profile)
        validate_profile(profile, args.profile.resolve().parents[2])
        if args.emit_contract_sources:
            paths = generate_contract_sources(args.emit_contract_sources, profile)
            print(json.dumps({"sources": [str(path) for path in paths]}, sort_keys=True))
            return 0
        required = {
            "--resource-source": args.resource_source,
            "--mysql-source": args.mysql_source,
            "--redis-source": args.redis_source,
            "--output-directory": args.output_directory,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(f"missing materialization arguments: {', '.join(missing)}")
        paths = materialize_bundle(
            args.profile,
            args.resource_source,
            args.mysql_source,
            args.redis_source,
            args.output_directory,
        )
        print(json.dumps({name: str(path) for name, path in paths.items()}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"staging evidence materialization failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
