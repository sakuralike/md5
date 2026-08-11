from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from materialize_staging_execution_evidence import generate_contract_sources
from verify_staging_readiness_profile import validate_profile

RESOURCE_EXPORT_SCHEMA = "staging-prometheus-range-export-v1"
HA_EXPORT_SCHEMA = "staging-ha-platform-export-v1"
RESOURCE_SOURCE_SCHEMA = "staging-resource-samples-v1"
HA_SOURCE_SCHEMA = "staging-ha-events-v1"
EVIDENCE_KINDS = {"contract-fixture", "target-execution"}
RESOURCE_METRICS = {
    "api_cpu_percent": ("api", "cpu_percent"),
    "api_memory_mebibytes": ("api", "memory_mebibytes"),
    "worker_cpu_percent": ("worker", "cpu_percent"),
    "worker_memory_mebibytes": ("worker", "memory_mebibytes"),
    "mysql_cpu_percent": ("mysql", "cpu_percent"),
    "mysql_memory_mebibytes": ("mysql", "memory_mebibytes"),
    "redis_cpu_percent": ("redis", "cpu_percent"),
    "redis_memory_mebibytes": ("redis", "memory_mebibytes"),
}
REPLICA_COUNT_METRICS = {
    "api_running_replicas": "api",
    "worker_running_replicas": "worker",
    "mysql_running_replicas": "mysql",
    "redis_running_replicas": "redis",
}
INTEGER_METRICS = {
    "database_connections",
    "celery_queue_depth",
    *REPLICA_COUNT_METRICS,
}
REQUIRED_METRICS = set(RESOURCE_METRICS) | INTEGER_METRICS
FIXTURE_ADAPTER_RE = re.compile(r"(fixture|synthetic|test|mock)", re.IGNORECASE)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|authorization|cookie|api[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"(://[^/\s:@]+:[^@\s]+@|(?:password|passwd|secret|token|api[_-]?key)=)",
    re.IGNORECASE,
)
COMMON_EXPORT_KEYS = {
    "schema",
    "environment",
    "synthetic_data_only",
    "evidence_kind",
    "execution_group_id",
    "execution_id",
    "source_adapter",
    "collector_version",
    "clock",
}
RESOURCE_EXPORT_KEYS = COMMON_EXPORT_KEYS | {
    "started_at",
    "finished_at",
    "sample_interval_seconds",
    "series",
    "probe_windows",
    "events",
}
HA_EXPORT_KEYS = COMMON_EXPORT_KEYS | {
    "dependency",
    "mode",
    "started_at",
    "finished_at",
    "durability",
    "events",
}
HA_EVENT_KEYS = {"type", "observed_at", "status", "provider_event_sha256"}


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
        raise TypeError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise ValueError(f"{name} must be finite and at least {minimum}")
    return number


def _require_integer(value: Any, name: str, minimum: int = 0) -> int:
    number = _require_number(value, name, minimum)
    if not number.is_integer():
        raise ValueError(f"{name} must be a whole number")
    return int(number)


def _parse_utc(value: Any, name: str) -> datetime:
    text = _require_string(value, name)
    if not text.endswith("Z"):
        raise ValueError(f"{name} must use UTC Z timestamps")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{name} is not a valid timestamp") from exc
    if parsed.tzinfo != UTC:
        raise ValueError(f"{name} must use UTC")
    return parsed


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _reject_unknown_keys(value: dict[str, Any], allowed: set[str], name: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{name} contains unsupported fields: {', '.join(unknown)}")


def _walk_for_secrets(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                raise ValueError(f"secret-like field is not allowed at {path}.{key}")
            _walk_for_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_for_secrets(item, f"{path}[{index}]")
    elif isinstance(value, str) and SECRET_VALUE_RE.search(value):
        raise ValueError(f"credential-like value is not allowed at {path}")


def _validate_common_export(
    export: dict[str, Any], expected_schema: str, allowed_keys: set[str]
) -> dict[str, Any]:
    _reject_unknown_keys(export, allowed_keys, "export")
    if export.get("schema") != expected_schema:
        raise ValueError(f"unexpected export schema; expected {expected_schema}")
    if export.get("environment") != "staging":
        raise ValueError("export environment must be staging")
    if export.get("synthetic_data_only") is not True:
        raise ValueError("export must be synthetic-data-only")
    evidence_kind = _require_string(export.get("evidence_kind"), "evidence_kind")
    if evidence_kind not in EVIDENCE_KINDS:
        raise ValueError("evidence_kind must be contract-fixture or target-execution")
    source_adapter = _require_string(export.get("source_adapter"), "source_adapter")
    if evidence_kind == "target-execution" and FIXTURE_ADAPTER_RE.search(source_adapter):
        raise ValueError("target-execution cannot use a fixture, synthetic, test or mock adapter")
    clock = _require_object(export.get("clock"), "clock")
    _reject_unknown_keys(
        clock,
        {"timezone", "maximum_skew_seconds", "observed_skew_seconds"},
        "clock",
    )
    if clock.get("timezone") != "UTC":
        raise ValueError("clock.timezone must be UTC")
    maximum_skew = _require_number(clock.get("maximum_skew_seconds"), "maximum_skew_seconds")
    observed_skew = _require_number(clock.get("observed_skew_seconds"), "observed_skew_seconds")
    if maximum_skew > 30 or observed_skew > maximum_skew:
        raise ValueError("clock skew exceeds the allowed maximum")
    _walk_for_secrets(export)
    return {
        "environment": "staging",
        "synthetic_data_only": True,
        "evidence_kind": evidence_kind,
        "execution_group_id": _require_string(
            export.get("execution_group_id"), "execution_group_id"
        ),
        "execution_id": _require_string(export.get("execution_id"), "execution_id"),
        "source_adapter": source_adapter,
        "collector_version": _require_string(
            export.get("collector_version"), "collector_version"
        ),
        "clock": clock,
    }


def _parse_prometheus_timestamp(value: Any, name: str) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a Unix timestamp number")
    timestamp = float(value)
    if not math.isfinite(timestamp) or not timestamp.is_integer():
        raise ValueError(f"{name} must be a finite whole-second Unix timestamp")
    try:
        return datetime.fromtimestamp(timestamp, UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"{name} is outside the supported timestamp range") from exc


def _parse_prometheus_value(value: Any, name: str) -> float:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a Prometheus numeric string")
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return number


def _extract_prometheus_series(envelope: Any, metric_name: str) -> list[tuple[datetime, float]]:
    response = _require_object(envelope, f"series.{metric_name}")
    _reject_unknown_keys(response, {"status", "data"}, f"series.{metric_name}")
    if response.get("status") != "success":
        raise ValueError(f"series.{metric_name}.status must be success")
    data = _require_object(response.get("data"), f"series.{metric_name}.data")
    _reject_unknown_keys(data, {"resultType", "result"}, f"series.{metric_name}.data")
    if data.get("resultType") != "matrix":
        raise ValueError(f"series.{metric_name}.data.resultType must be matrix")
    result = _require_list(data.get("result"), f"series.{metric_name}.data.result")
    if len(result) != 1:
        raise ValueError(f"series.{metric_name} must contain exactly one normalized time series")
    time_series = _require_object(result[0], f"series.{metric_name}.data.result[0]")
    _reject_unknown_keys(
        time_series,
        {"metric", "values"},
        f"series.{metric_name}.data.result[0]",
    )
    labels = _require_object(
        time_series.get("metric"), f"series.{metric_name}.data.result[0].metric"
    )
    _walk_for_secrets(labels, f"$.series.{metric_name}.data.result[0].metric")
    values = _require_list(
        time_series.get("values"), f"series.{metric_name}.data.result[0].values"
    )
    if not values:
        raise ValueError(f"series.{metric_name} cannot be empty")
    parsed: list[tuple[datetime, float]] = []
    previous: datetime | None = None
    for index, raw_point in enumerate(values):
        point = _require_list(raw_point, f"series.{metric_name}.values[{index}]")
        if len(point) != 2:
            raise ValueError(f"series.{metric_name}.values[{index}] must contain timestamp and value")
        observed_at = _parse_prometheus_timestamp(
            point[0], f"series.{metric_name}.values[{index}][0]"
        )
        if previous is not None and observed_at <= previous:
            raise ValueError(f"series.{metric_name} timestamps must be strictly increasing")
        parsed.append(
            (
                observed_at,
                _parse_prometheus_value(point[1], f"series.{metric_name}.values[{index}][1]"),
            )
        )
        previous = observed_at
    return parsed


def adapt_resource_export(export: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    common = _validate_common_export(export, RESOURCE_EXPORT_SCHEMA, RESOURCE_EXPORT_KEYS)
    started = _parse_utc(export.get("started_at"), "started_at")
    finished = _parse_utc(export.get("finished_at"), "finished_at")
    if finished <= started:
        raise ValueError("finished_at must be later than started_at")
    interval = _require_integer(
        export.get("sample_interval_seconds"), "sample_interval_seconds", 1
    )
    configured_interval = int(profile["stability"]["resource_sample_interval_seconds"])
    if interval != configured_interval:
        raise ValueError("sample_interval_seconds must match the staging readiness profile")
    series = _require_object(export.get("series"), "series")
    if set(series) != REQUIRED_METRICS:
        missing = sorted(REQUIRED_METRICS - set(series))
        extra = sorted(set(series) - REQUIRED_METRICS)
        raise ValueError(f"series must contain canonical metrics; missing={missing}, extra={extra}")
    parsed_series = {
        name: _extract_prometheus_series(series[name], name) for name in sorted(REQUIRED_METRICS)
    }
    canonical_times = [timestamp for timestamp, _ in parsed_series["api_cpu_percent"]]
    for metric_name, points in parsed_series.items():
        if [timestamp for timestamp, _ in points] != canonical_times:
            raise ValueError(f"series.{metric_name} timestamps do not align with canonical samples")
    if canonical_times[0] != started or canonical_times[-1] != finished:
        raise ValueError("Prometheus series must start and finish at the declared execution boundaries")
    if any(
        int((current - previous).total_seconds()) != interval
        for previous, current in pairwise(canonical_times)
    ):
        raise ValueError("Prometheus series cadence does not match sample_interval_seconds")

    values_by_metric = {
        name: [value for _, value in points] for name, points in parsed_series.items()
    }
    for name in INTEGER_METRICS:
        if any(not value.is_integer() for value in values_by_metric[name]):
            raise ValueError(f"series.{name} must contain whole-number values")
    for name in REPLICA_COUNT_METRICS:
        if any(value < 1 for value in values_by_metric[name]):
            raise ValueError(f"series.{name} must be at least 1 for every sample")

    samples: list[dict[str, Any]] = []
    for index, observed_at in enumerate(canonical_times):
        resources = {
            resource: {
                value_name: values_by_metric[metric_name][index]
                for metric_name, (mapped_resource, value_name) in RESOURCE_METRICS.items()
                if mapped_resource == resource
            }
            for resource in ("api", "worker", "mysql", "redis")
        }
        samples.append(
            {
                "observed_at": _format_utc(observed_at),
                "service_container_counts": {
                    resource: int(values_by_metric[metric_name][index])
                    for metric_name, resource in REPLICA_COUNT_METRICS.items()
                },
                "resources": resources,
                "database_connections": int(values_by_metric["database_connections"][index]),
                "celery_queue_depth": int(values_by_metric["celery_queue_depth"][index]),
            }
        )
    return {
        "schema": RESOURCE_SOURCE_SCHEMA,
        **common,
        "started_at": _format_utc(started),
        "finished_at": _format_utc(finished),
        "samples": samples,
        "probe_windows": _require_list(export.get("probe_windows"), "probe_windows"),
        "events": _require_list(export.get("events"), "events"),
    }


def adapt_ha_export(
    export: dict[str, Any], profile: dict[str, Any], expected_dependency: str
) -> dict[str, Any]:
    common = _validate_common_export(export, HA_EXPORT_SCHEMA, HA_EXPORT_KEYS)
    dependency = _require_string(export.get("dependency"), "dependency")
    if dependency != expected_dependency:
        raise ValueError(f"HA export dependency must be {expected_dependency}")
    mode = _require_string(export.get("mode"), "mode")
    if mode != profile["high_availability"][dependency]["mode"]:
        raise ValueError(f"{dependency} HA mode must match the staging readiness profile")
    started = _parse_utc(export.get("started_at"), "started_at")
    finished = _parse_utc(export.get("finished_at"), "finished_at")
    if finished <= started:
        raise ValueError("finished_at must be later than started_at")
    durability = _require_object(export.get("durability"), "durability")
    _reject_unknown_keys(
        durability,
        {"last_confirmed_durable_at", "recovery_point_at", "lost_records"},
        "durability",
    )
    events = _require_list(export.get("events"), "events")
    sanitized_events: list[dict[str, Any]] = []
    for index, raw_event in enumerate(events):
        event = _require_object(raw_event, f"events[{index}]")
        _reject_unknown_keys(event, HA_EVENT_KEYS, f"events[{index}]")
        sanitized = {
            "type": _require_string(event.get("type"), f"events[{index}].type"),
            "observed_at": _format_utc(
                _parse_utc(event.get("observed_at"), f"events[{index}].observed_at")
            ),
        }
        if "status" in event:
            sanitized["status"] = _require_string(
                event.get("status"), f"events[{index}].status"
            )
        if "provider_event_sha256" in event:
            digest = _require_string(
                event.get("provider_event_sha256"),
                f"events[{index}].provider_event_sha256",
            )
            if not SHA256_RE.fullmatch(digest):
                raise ValueError(f"events[{index}].provider_event_sha256 must be lowercase SHA-256")
            sanitized["provider_event_sha256"] = digest
        sanitized_events.append(sanitized)
    return {
        "schema": HA_SOURCE_SCHEMA,
        **common,
        "dependency": dependency,
        "mode": mode,
        "started_at": _format_utc(started),
        "finished_at": _format_utc(finished),
        "last_confirmed_durable_at": _format_utc(
            _parse_utc(
                durability.get("last_confirmed_durable_at"),
                "durability.last_confirmed_durable_at",
            )
        ),
        "recovery_point_at": _format_utc(
            _parse_utc(durability.get("recovery_point_at"), "durability.recovery_point_at")
        ),
        "lost_records": _require_integer(durability.get("lost_records"), "lost_records"),
        "events": sanitized_events,
    }


def _prometheus_envelope(name: str, values: list[list[Any]]) -> dict[str, Any]:
    return {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [{"metric": {"canonical_metric": name}, "values": values}],
        },
    }


def generate_contract_exports(directory: Path, profile: dict[str, Any]) -> tuple[Path, Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temporary_directory:
        source_paths = generate_contract_sources(Path(temporary_directory), profile)
        resource_source, mysql_source, redis_source = map(_load_json, source_paths)

    execution_group_id = "wp4-iteration-15-platform-export-contract"
    samples = _require_list(resource_source["samples"], "samples")
    metric_values: dict[str, list[list[Any]]] = {name: [] for name in REQUIRED_METRICS}
    for raw_sample in samples:
        sample = _require_object(raw_sample, "sample")
        timestamp = _parse_utc(sample["observed_at"], "observed_at").timestamp()
        resources = _require_object(sample["resources"], "resources")
        for metric_name, (resource, value_name) in RESOURCE_METRICS.items():
            metric_values[metric_name].append([timestamp, str(resources[resource][value_name])])
        replica_counts = _require_object(
            sample["service_container_counts"], "service_container_counts"
        )
        for metric_name, resource in REPLICA_COUNT_METRICS.items():
            metric_values[metric_name].append([timestamp, str(replica_counts[resource])])
        metric_values["database_connections"].append(
            [timestamp, str(sample["database_connections"])]
        )
        metric_values["celery_queue_depth"].append(
            [timestamp, str(sample["celery_queue_depth"])]
        )

    common = {
        "environment": "staging",
        "synthetic_data_only": True,
        "evidence_kind": "contract-fixture",
        "execution_group_id": execution_group_id,
        "collector_version": "1.0.0",
        "clock": resource_source["clock"],
    }
    resource_export = {
        "schema": RESOURCE_EXPORT_SCHEMA,
        **common,
        "execution_id": "wp4-iteration-15-prometheus-contract",
        "source_adapter": "prometheus-contract-fixture-v1",
        "started_at": resource_source["started_at"],
        "finished_at": resource_source["finished_at"],
        "sample_interval_seconds": profile["stability"]["resource_sample_interval_seconds"],
        "series": {
            name: _prometheus_envelope(name, metric_values[name])
            for name in sorted(REQUIRED_METRICS)
        },
        "probe_windows": resource_source["probe_windows"],
        "events": resource_source["events"],
    }

    def ha_export(source: dict[str, Any]) -> dict[str, Any]:
        dependency = source["dependency"]
        events = []
        for index, event in enumerate(source["events"]):
            normalized = dict(event)
            normalized["provider_event_sha256"] = hashlib.sha256(
                f"{dependency}-contract-event-{index}".encode()
            ).hexdigest()
            events.append(normalized)
        return {
            "schema": HA_EXPORT_SCHEMA,
            **common,
            "execution_id": f"wp4-iteration-15-{dependency}-platform-contract",
            "source_adapter": f"managed-{dependency}-contract-fixture-v1",
            "dependency": dependency,
            "mode": source["mode"],
            "started_at": source["started_at"],
            "finished_at": source["finished_at"],
            "durability": {
                "last_confirmed_durable_at": source["last_confirmed_durable_at"],
                "recovery_point_at": source["recovery_point_at"],
                "lost_records": source["lost_records"],
            },
            "events": events,
        }

    paths = (
        directory / "prometheus-resource-export.json",
        directory / "mysql-ha-platform-export.json",
        directory / "redis-ha-platform-export.json",
    )
    _write_json(paths[0], resource_export)
    _write_json(paths[1], ha_export(mysql_source))
    _write_json(paths[2], ha_export(redis_source))
    return paths


def adapt_bundle(
    profile_path: Path,
    resource_export_path: Path,
    mysql_export_path: Path,
    redis_export_path: Path,
    output_directory: Path,
) -> tuple[Path, Path, Path]:
    profile = _load_json(profile_path)
    validate_profile(profile, profile_path.resolve().parents[2])
    resource_export = _load_json(resource_export_path)
    mysql_export = _load_json(mysql_export_path)
    redis_export = _load_json(redis_export_path)
    group_ids = {
        resource_export.get("execution_group_id"),
        mysql_export.get("execution_group_id"),
        redis_export.get("execution_group_id"),
    }
    if len(group_ids) != 1 or any(not isinstance(value, str) or not value for value in group_ids):
        raise ValueError("all platform exports must share one execution_group_id")
    kinds = {
        resource_export.get("evidence_kind"),
        mysql_export.get("evidence_kind"),
        redis_export.get("evidence_kind"),
    }
    if len(kinds) != 1:
        raise ValueError("all platform exports must use the same evidence_kind")
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = (
        output_directory / "resource-source.json",
        output_directory / "mysql-ha-source.json",
        output_directory / "redis-ha-source.json",
    )
    _write_json(paths[0], adapt_resource_export(resource_export, profile))
    _write_json(paths[1], adapt_ha_export(mysql_export, profile, "mysql"))
    _write_json(paths[2], adapt_ha_export(redis_export, profile, "redis"))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Adapt sanitized Prometheus and HA platform exports into WP4 source evidence."
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--emit-contract-exports", type=Path)
    parser.add_argument("--resource-export", type=Path)
    parser.add_argument("--mysql-export", type=Path)
    parser.add_argument("--redis-export", type=Path)
    parser.add_argument("--output-directory", type=Path)
    args = parser.parse_args()
    try:
        profile = _load_json(args.profile)
        validate_profile(profile, args.profile.resolve().parents[2])
        if args.emit_contract_exports:
            paths = generate_contract_exports(args.emit_contract_exports, profile)
            print(f"Generated staging platform export contract fixtures: {', '.join(map(str, paths))}")
            return 0
        required = {
            "--resource-export": args.resource_export,
            "--mysql-export": args.mysql_export,
            "--redis-export": args.redis_export,
            "--output-directory": args.output_directory,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            parser.error(f"required for adaptation: {', '.join(missing)}")
        paths = adapt_bundle(
            args.profile,
            args.resource_export,
            args.mysql_export,
            args.redis_export,
            args.output_directory,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"staging platform export adaptation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Adapted staging platform exports: {', '.join(map(str, paths))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
