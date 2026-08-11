from __future__ import annotations

import copy
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from collect_staging_resource_observation import (
    collect_observation,
    parse_memory_mebibytes,
    parse_percent,
)
from verify_staging_resource_observation import validate_observation


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, arguments: list[str]) -> str:
        self.commands.append(list(arguments))
        if "ps" in arguments:
            return "\n".join(
                json.dumps(
                    {"Service": service, "State": "running", "Name": f"pd-{service}-1"}
                )
                for service in ("api", "worker", "mysql", "redis")
            )
        if arguments[:2] == ["docker", "stats"]:
            values = {
                "api": ("12.5%", "96.25MiB / 8GiB"),
                "worker": ("3.25%", "210.5MiB / 8GiB"),
                "mysql": ("4.5%", "0.5GiB / 8GiB"),
                "redis": ("0.75%", "16.5MiB / 8GiB"),
            }
            return "\n".join(
                json.dumps(
                    {"Name": f"pd-{service}-1", "CPUPerc": cpu, "MemUsage": memory}
                )
                for service, (cpu, memory) in values.items()
            )
        if "exec" in arguments and "mysql" in arguments:
            return "8\n"
        raise AssertionError(f"unexpected command: {arguments}")




class WorkerLossRunner(FakeRunner):
    def __init__(self) -> None:
        super().__init__()
        self.ps_calls = 0

    def run(self, arguments: list[str]) -> str:
        self.commands.append(list(arguments))
        if "ps" in arguments:
            worker_names = (
                ["pd-worker-1", "pd-worker-2"]
                if self.ps_calls != 1
                else ["pd-worker-2"]
            )
            self.ps_calls += 1
            rows = [
                {"Service": service, "State": "running", "Name": f"pd-{service}-1"}
                for service in ("api", "mysql", "redis")
            ]
            rows.extend(
                {"Service": "worker", "State": "running", "Name": name}
                for name in worker_names
            )
            return "\n".join(json.dumps(row) for row in rows)
        if arguments[:2] == ["docker", "stats"]:
            rows = []
            for name in arguments[5:]:
                rows.append(
                    {
                        "Name": name,
                        "CPUPerc": "1.0%",
                        "MemUsage": "32MiB / 8GiB",
                    }
                )
            return "\n".join(json.dumps(row) for row in rows)
        if "exec" in arguments and "mysql" in arguments:
            return "8\n"
        raise AssertionError(f"unexpected command: {arguments}")


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)

    def now(self) -> datetime:
        current = self.value
        self.value += timedelta(seconds=15)
        return current


def load_example() -> dict[str, Any]:
    return json.loads(
        (ROOT / "infra/staging/resource-observation.example.json").read_text(
            encoding="utf-8"
        )
    )


def test_docker_stat_parsers_support_binary_and_decimal_units() -> None:
    assert parse_percent("12.50%") == 12.5
    assert parse_memory_mebibytes("512MiB / 8GiB") == 512
    assert parse_memory_mebibytes("1.5GiB / 8GiB") == 1536
    assert parse_memory_mebibytes("100MB / 8GB") == pytest.approx(95.367, abs=0.001)


def test_collector_aggregates_required_services_without_container_identity() -> None:
    runner = FakeRunner()
    clock = Clock()
    monotonic_values = iter([0.0, 0.0])
    observation = collect_observation(
        runner,
        ["docker-compose.yml", "docker-compose.staging.override.yml"],
        None,
        "http://127.0.0.1:8000/api/v1/metrics",
        duration_seconds=0,
        sample_interval_seconds=15,
        timeout_seconds=5,
        now=clock.now,
        sleeper=lambda _seconds: None,
        monotonic=lambda: next(monotonic_values),
        metrics_fetcher=lambda _url, _timeout: (
            "password_detective_worker_queue_depth 3\n"
        ),
    )

    assert observation["evidence_kind"] == "target-observation"
    assert observation["eligible_for_target_execution"] is False
    assert observation["sample_count"] == 1
    assert observation["samples"][0]["resources"]["mysql"]["memory_mebibytes"] == 512
    assert observation["samples"][0]["database_connections"] == 8
    assert observation["samples"][0]["celery_queue_depth"] == 3
    assert "pd-api-1" not in json.dumps(observation)


def test_example_observation_contract_passes() -> None:
    report = validate_observation(load_example())

    assert report["status"] == "passed"
    assert report["evidence_kind"] == "contract-fixture"
    assert report["eligible_for_target_execution"] is False
    assert report["sample_count"] == 2


def test_observation_cannot_claim_target_execution() -> None:
    observation = load_example()
    observation["eligible_for_target_execution"] = True

    with pytest.raises(ValueError, match="must not be eligible"):
        validate_observation(observation)


def test_observation_rejects_container_identity_and_missing_service() -> None:
    observation = load_example()
    observation["samples"][0]["container_name"] = "sensitive-runtime-name"
    with pytest.raises(ValueError, match="container identity"):
        validate_observation(observation)

    observation = copy.deepcopy(load_example())
    del observation["service_container_counts"]["redis"]
    with pytest.raises(ValueError, match="must cover"):
        validate_observation(observation)


def test_collector_rediscovers_running_workers_during_loss_and_recovery() -> None:
    runner = WorkerLossRunner()
    clock = Clock()
    observation = collect_observation(
        runner,
        ["docker-compose.yml"],
        None,
        "http://127.0.0.1:8000/api/v1/metrics",
        duration_seconds=30,
        sample_interval_seconds=15,
        timeout_seconds=5,
        now=clock.now,
        sleeper=lambda _seconds: None,
        monotonic=lambda: 0.0,
        metrics_fetcher=lambda _url, _timeout: (
            "password_detective_worker_queue_depth 0\n"
        ),
    )

    assert observation["service_container_counts"]["worker"] == 2
    assert [
        sample["service_container_counts"]["worker"]
        for sample in observation["samples"]
    ] == [2, 1, 2]
    assert observation["samples"][1]["resources"]["worker"]["memory_mebibytes"] == 32
    assert "pd-worker" not in json.dumps(observation)
    validate_observation(observation)
