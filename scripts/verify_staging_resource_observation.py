from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA = "staging-resource-observation-v1"
REQUIRED_SERVICES = {"api", "worker", "mysql", "redis"}
EVIDENCE_KINDS = {"contract-fixture", "target-observation"}
SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|authorization|cookie|api[_-]?key|private[_-]?key|container[_-]?(?:id|name))",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"(://[^/\s:@]+:[^@\s]+@|(?:password|passwd|secret|token|api[_-]?key)=)",
    re.IGNORECASE,
)


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{name} must be an array")
    return value


def _require_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} cannot be negative or non-finite")
    return number


def _parse_utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{name} must be an explicit UTC Z timestamp")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must use UTC")
    return parsed.astimezone(timezone.utc)


def _successive_pairs(values: list[datetime]):
    for index in range(1, len(values)):
        yield values[index - 1], values[index]


def _walk_for_secrets(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                raise ValueError(
                    f"secret or container identity field is not allowed: {path}.{key}"
                )
            _walk_for_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_for_secrets(item, f"{path}[{index}]")
    elif isinstance(value, str) and SECRET_VALUE_RE.search(value):
        raise ValueError(f"credential-like value is not allowed at {path}")


def validate_observation(document: dict[str, Any]) -> dict[str, Any]:
    _walk_for_secrets(document)
    if document.get("schema") != SCHEMA:
        raise ValueError(f"unexpected schema; expected {SCHEMA}")
    if document.get("status") != "passed":
        raise ValueError("observation status must be passed")
    evidence_kind = document.get("evidence_kind")
    if evidence_kind not in EVIDENCE_KINDS:
        raise ValueError("unsupported evidence_kind")
    if document.get("execution_status") != "observation-only":
        raise ValueError("execution_status must remain observation-only")
    if document.get("eligible_for_target_execution") is not False:
        raise ValueError(
            "resource observation must not be eligible for target-execution"
        )
    if document.get("environment") != "staging":
        raise ValueError("environment must be staging")
    if document.get("synthetic_data_only") is not True:
        raise ValueError("observation must be synthetic-data-only")
    collector = document.get("collector_adapter")
    version = document.get("collector_version")
    if not isinstance(collector, str) or not collector.strip():
        raise TypeError("collector_adapter must be a non-empty string")
    if not isinstance(version, str) or not version.strip():
        raise TypeError("collector_version must be a non-empty string")

    started = _parse_utc(document.get("started_at"), "started_at")
    finished = _parse_utc(document.get("finished_at"), "finished_at")
    if finished < started:
        raise ValueError("finished_at cannot precede started_at")
    interval = int(
        _require_number(
            document.get("sample_interval_seconds"), "sample_interval_seconds"
        )
    )
    if interval < 1:
        raise ValueError("sample_interval_seconds must be at least one")

    counts = _require_object(
        document.get("service_container_counts"), "service_container_counts"
    )
    if set(counts) != REQUIRED_SERVICES:
        raise ValueError(
            "service_container_counts must cover API, Worker, MySQL and Redis"
        )
    for service in REQUIRED_SERVICES:
        if (
            int(_require_number(counts[service], f"service_container_counts.{service}"))
            < 1
        ):
            raise ValueError(f"service_container_counts.{service} must be at least one")

    samples = _require_list(document.get("samples"), "samples")
    if not samples:
        raise ValueError("samples cannot be empty")
    if document.get("sample_count") != len(samples):
        raise ValueError("sample_count does not match samples")
    sample_times: list[datetime] = []
    for index, raw_sample in enumerate(samples):
        sample = _require_object(raw_sample, f"samples[{index}]")
        observed = _parse_utc(
            sample.get("observed_at"), f"samples[{index}].observed_at"
        )
        if observed < started or observed > finished:
            raise ValueError(f"samples[{index}] falls outside the observation timeline")
        sample_times.append(observed)
        sample_counts = sample.get("service_container_counts")
        if sample_counts is not None:
            sample_counts = _require_object(
                sample_counts, f"samples[{index}].service_container_counts"
            )
            if set(sample_counts) != REQUIRED_SERVICES:
                raise ValueError(
                    f"samples[{index}].service_container_counts must cover API, Worker, MySQL and Redis"
                )
            for service in REQUIRED_SERVICES:
                if int(
                    _require_number(
                        sample_counts[service],
                        f"samples[{index}].service_container_counts.{service}",
                    )
                ) < 1:
                    raise ValueError(
                        f"samples[{index}].service_container_counts.{service} must be at least one"
                    )
        resources = _require_object(
            sample.get("resources"), f"samples[{index}].resources"
        )
        if set(resources) != REQUIRED_SERVICES:
            raise ValueError(
                f"samples[{index}] must cover API, Worker, MySQL and Redis"
            )
        for service in REQUIRED_SERVICES:
            resource = _require_object(
                resources[service], f"samples[{index}].resources.{service}"
            )
            if set(resource) != {"cpu_percent", "memory_mebibytes"}:
                raise ValueError(f"samples[{index}].resources.{service} fields drifted")
            _require_number(
                resource["cpu_percent"],
                f"samples[{index}].resources.{service}.cpu_percent",
            )
            _require_number(
                resource["memory_mebibytes"],
                f"samples[{index}].resources.{service}.memory_mebibytes",
            )
        _require_number(
            sample.get("database_connections"), f"samples[{index}].database_connections"
        )
        _require_number(
            sample.get("celery_queue_depth"), f"samples[{index}].celery_queue_depth"
        )
    if any(
        current <= previous for previous, current in _successive_pairs(sample_times)
    ):
        raise ValueError("resource observation timestamps must be strictly increasing")
    if len(sample_times) > 1:
        maximum_gap = max(
            (current - previous).total_seconds()
            for previous, current in _successive_pairs(sample_times)
        )
        if maximum_gap > interval * 2:
            raise ValueError(
                "resource observation gap exceeds twice the configured interval"
            )

    limitations = _require_list(document.get("limitations"), "limitations")
    required_limitations = {
        "operation probe windows are not collected",
        "single Worker loss and recovery are not executed",
        "MySQL and Redis HA failover are not executed",
        "this observation cannot be used as target-execution evidence",
    }
    if not required_limitations <= {str(value) for value in limitations}:
        raise ValueError("observation limitations are incomplete")
    peak_resources = {
        service: {
            "cpu_percent": max(
                float(sample["resources"][service]["cpu_percent"]) for sample in samples
            ),
            "memory_mebibytes": max(
                float(sample["resources"][service]["memory_mebibytes"])
                for sample in samples
            ),
        }
        for service in sorted(REQUIRED_SERVICES)
    }
    return {
        "schema": "staging-resource-observation-verification-v1",
        "status": "passed",
        "evidence_kind": evidence_kind,
        "execution_status": "observation-only",
        "eligible_for_target_execution": False,
        "sample_count": len(samples),
        "peak_database_connections": max(
            int(sample["database_connections"]) for sample in samples
        ),
        "peak_celery_queue_depth": max(
            int(sample["celery_queue_depth"]) for sample in samples
        ),
        "peak_resources": peak_resources,
    }


def write_verification(
    input_path: Path, output_path: Path, write_checksums: bool
) -> dict[str, Any]:
    document = json.loads(input_path.read_text(encoding="utf-8"))
    report = validate_observation(_require_object(document, "observation"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if write_checksums:
        lines = [
            f"{hashlib.sha256(input_path.read_bytes()).hexdigest()}  {input_path.name}",
            f"{hashlib.sha256(output_path.read_bytes()).hexdigest()}  {output_path.name}",
        ]
        output_path.with_name("checksums.sha256").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a WP4 Staging resource observation."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    try:
        report = write_verification(args.input, args.output, args.write_checksums)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(
            f"staging resource observation verification failed: {exc}", file=sys.stderr
        )
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
