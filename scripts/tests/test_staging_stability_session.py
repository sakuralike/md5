from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from assemble_staging_stability_session import (
    assemble_session,
    evaluate_eligibility,
    validate_session,
)
from multi_instance_stability_probe import (
    OPERATION_NAMES,
    build_probe_report,
    new_operation_stats,
)


def load_fixture() -> dict[str, Any]:
    return json.loads(
        (ROOT / "infra/staging/stability-session.example.json").read_text(encoding="utf-8")
    )


def load_profile() -> dict[str, Any]:
    return json.loads(
        (ROOT / "infra/staging/readiness-profile.example.json").read_text(encoding="utf-8")
    )


def relaxed_profile() -> dict[str, Any]:
    profile = load_profile()
    profile["stability"]["duration_seconds"] = 60
    profile["stability"]["minimum_operations"] = {name: 1 for name in OPERATION_NAMES}
    profile["topology"]["worker_replicas"] = 2
    return profile


def assembler_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    fixture = load_fixture()
    resource = {
        "schema": "staging-resource-observation-v1",
        "status": "passed",
        "started_at": fixture["started_at"],
        "finished_at": fixture["finished_at"],
        "sample_interval_seconds": fixture["sample_interval_seconds"],
        "samples": fixture["samples"],
    }
    operations = {
        name: {
            **fixture["probe_windows"][0]["operations"][name],
            "max_ms": fixture["probe_windows"][0]["operations"][name]["p95_ms"],
        }
        for name in OPERATION_NAMES
    }
    probe = {
        "schema": "multi-instance-stability-probe-v2",
        "status": "passed",
        "started_at": fixture["probe_windows"][0]["started_at"],
        "finished_at": fixture["probe_windows"][0]["finished_at"],
        "probe_windows": fixture["probe_windows"],
        "operations": operations,
        "error_count": 0,
        "errors": [],
    }
    worker_events = {
        "schema": "staging-worker-recovery-events-v1",
        "status": "passed",
        "events": fixture["events"],
        "summary": fixture["worker_event_summary"],
    }
    return resource, probe, worker_events


def test_contract_fixture_validates_but_is_not_target_execution() -> None:
    report = validate_session(load_fixture(), load_profile())

    assert report["status"] == "passed"
    assert report["evidence_kind"] == "contract-fixture"
    assert report["eligible_for_target_execution"] is False
    assert report["checks"]["duration"] is False


def test_assembler_keeps_short_target_run_observation_only() -> None:
    resource, probe, events = assembler_inputs()
    source = assemble_session(
        resource,
        probe,
        events,
        load_profile(),
        request_target_execution=True,
        execution_group_id="wp4-short-observation",
        execution_id="wp4-short-observation-1",
    )

    assert source["evidence_kind"] == "target-observation"
    assert source["eligible_for_target_execution"] is False
    assert "duration" in source["limitations"]


def test_assembler_promotes_only_when_every_relaxed_gate_passes() -> None:
    resource, probe, events = assembler_inputs()
    source = assemble_session(
        resource,
        probe,
        events,
        relaxed_profile(),
        request_target_execution=True,
        execution_group_id="wp4-eligible-session",
        execution_id="wp4-eligible-session-1",
    )

    assert source["evidence_kind"] == "target-execution"
    assert source["eligible_for_target_execution"] is True
    assert evaluate_eligibility(source, relaxed_profile())["eligible"] is True


def test_target_execution_claim_is_rejected_when_duration_is_short() -> None:
    source = load_fixture()
    source["evidence_kind"] = "target-execution"
    source["execution_status"] = "target-execution"
    source["eligible_for_target_execution"] = True

    with pytest.raises(ValueError, match="every staging eligibility check"):
        validate_session(source, load_profile())


def test_sensitive_container_identity_is_rejected() -> None:
    source = copy.deepcopy(load_fixture())
    source["events"][0]["container_name"] = "runtime-worker-1"

    with pytest.raises(ValueError, match="container identity"):
        validate_session(source, load_profile())


def test_probe_report_builds_fixed_windows_and_consecutive_error_counts() -> None:
    start = datetime(2026, 8, 11, 3, 0, tzinfo=timezone.utc)
    aggregate = {name: new_operation_stats() for name in OPERATION_NAMES}
    windows = [{name: new_operation_stats() for name in OPERATION_NAMES} for _ in range(2)]
    for stats in (aggregate["api"], windows[0]["api"]):
        stats.update(
            {
                "count": 3,
                "error_count": 2,
                "max_consecutive_errors": 2,
                "current_consecutive_errors": 2,
                "latencies_ms": [25.0],
            }
        )
    report = build_probe_report(
        started_at=start,
        finished_at=start + timedelta(seconds=60),
        window_seconds=30,
        aggregate=aggregate,
        windows=windows,
        errors=[{"probe": "api", "observed_at": "2026-08-11T03:00:10Z", "error": "synthetic"}],
    )

    assert report["schema"] == "multi-instance-stability-probe-v2"
    assert len(report["probe_windows"]) == 2
    assert report["operations"]["api"]["count"] == 3
    assert report["operations"]["api"]["max_consecutive_errors"] == 2
    assert report["operations"]["api"]["p95_ms"] == 25.0
