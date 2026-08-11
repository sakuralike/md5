from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from staging_topology_preflight import (
    build_topology_preflight,
    discover_service_counts,
)


class FakeRunner:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows
        self.arguments: list[str] = []

    def run(self, arguments: Sequence[str]) -> str:
        self.arguments = list(arguments)
        return "\n".join(json.dumps(row) for row in self.rows)


def load_profile() -> dict:
    return json.loads(
        (ROOT / "infra/staging/readiness-profile.example.json").read_text(
            encoding="utf-8"
        )
    )


def test_discovers_counts_without_exporting_container_identity() -> None:
    runner = FakeRunner(
        [
            {"Service": "api", "State": "running", "Name": "private-api-1"},
            {"Service": "api", "State": "running", "Name": "private-api-2"},
            {"Service": "worker", "State": "running", "Name": "private-worker-1"},
            {"Service": "worker", "State": "running", "Name": "private-worker-2"},
            {"Service": "worker", "State": "running", "Name": "private-worker-3"},
            {"Service": "scheduler", "State": "running", "Name": "private-scheduler"},
            {"Service": "mysql", "State": "running", "Name": "private-mysql"},
            {"Service": "redis", "State": "running", "Name": "private-redis"},
        ]
    )

    counts, prefix = discover_service_counts(runner, ["docker-compose.yml"], None)

    assert counts == {"api": 2, "worker": 3, "scheduler": 1, "mysql": 1, "redis": 1}
    assert prefix == ["docker", "compose", "--file", "docker-compose.yml"]
    assert "private-api-1" not in json.dumps(counts)


def test_builds_ready_capacity_preflight_for_target_topology() -> None:
    report = build_topology_preflight(
        load_profile(),
        {"api": 2, "worker": 3, "scheduler": 1, "mysql": 1, "redis": 1},
    )

    assert report["status"] == "passed"
    assert report["ready_for_target_execution"] is True
    assert report["capacity_budget"]["requested_connections"] == 110
    assert report["capacity_budget"]["allowed_connections"] == 136
    assert report["limitations"] == []


def test_reports_api_replica_gap_without_leaking_runtime_identity() -> None:
    report = build_topology_preflight(
        load_profile(),
        {"api": 1, "worker": 3, "scheduler": 1, "mysql": 1, "redis": 1},
    )

    assert report["status"] == "blocked"
    assert report["checks"]["api_replicas"] is False
    assert report["limitations"] == ["api_replicas"]
    assert "container" not in json.dumps(report).lower()
