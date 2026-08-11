from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from control_staging_formal_session import (
    DEFAULT_COMPOSE_FILES,
    SCHEMA,
    build_runner_command,
    create_launch_state,
    process_is_running,
    process_start_marker,
    reconcile_state,
    summarize_verification,
    validate_start_values,
)


def make_args(root: Path) -> argparse.Namespace:
    return argparse.Namespace(
        profile=str(root / "infra/staging/readiness-profile.example.json"),
        duration_seconds=75,
        probe_interval_seconds=1,
        probe_window_seconds=30,
        resource_sample_interval_seconds=15,
        worker_count=3,
        worker_loss_after_seconds=30,
        worker_loss_duration_seconds=10,
        api_metrics_url="http://127.0.0.1:8000/api/v1/metrics",
        compose_files=list(DEFAULT_COMPOSE_FILES),
        project_directory=str(root),
        observation_only=False,
        source_revision="synthetic-revision",
    )


def test_formal_command_uses_target_defaults(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    command = build_runner_command(args, tmp_path, tmp_path / "output")

    assert command[command.index("--duration-seconds") + 1] == "75"
    assert command[command.index("--probe-window-seconds") + 1] == "30"
    assert command[command.index("--worker-loss-after-seconds") + 1] == "30"
    assert command.count("--compose-file") == len(DEFAULT_COMPOSE_FILES)
    assert "--request-target-execution" in command


def test_launch_state_contains_no_environment_or_secret_values(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    output = tmp_path / "output"
    state = create_launch_state(
        args,
        tmp_path,
        output,
        output / "formal-session.log",
        ["python", "runner.py"],
        "synthetic-run",
    )

    serialized = json.dumps(state).lower()
    assert state["schema"] == SCHEMA
    assert "environment" not in state
    assert "password" not in serialized
    assert "token" not in serialized
    assert "secret" not in serialized


def test_reconcile_marks_missing_supervisor_as_interrupted(tmp_path: Path) -> None:
    state_path = tmp_path / "control.json"
    state_path.write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "run_id": "stale-run",
                "status": "running",
                "pid": 999_999_999,
                "process_start_marker": "not-current",
                "output_directory": str(tmp_path / "output"),
            }
        ),
        encoding="utf-8",
    )

    reconciled = reconcile_state(state_path)

    assert reconciled["status"] == "interrupted"
    assert "verification" not in reconciled
    assert "finished_at" in reconciled


def test_verification_summary_is_digest_bound(tmp_path: Path) -> None:
    report_path = tmp_path / "staging-resource-samples-verification.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "eligible_for_target_execution": True,
                "execution_status": "target-execution",
                "duration_seconds": 14400,
                "error_rate_percent": 0,
                "coverage_percent": 100,
                "final_queue_depth": 0,
                "checks": {"duration": True},
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_verification(report_path)

    assert summary["verification_status"] == "passed"
    assert summary["eligible_for_target_execution"] is True
    assert len(summary["verification_sha256"]) == 64


def test_current_process_marker_can_guard_against_pid_reuse() -> None:
    marker = process_start_marker(os.getpid())
    assert process_is_running(os.getpid(), marker)
    if marker is not None:
        assert not process_is_running(os.getpid(), marker + "-different")


def test_reconcile_rejects_unknown_schema(tmp_path: Path) -> None:
    state_path = tmp_path / "control.json"
    state_path.write_text(json.dumps({"schema": "unknown"}), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported session control schema"):
        reconcile_state(state_path)


def test_target_start_requires_a_hexadecimal_source_revision(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    args.source_revision = "unknown"
    args.allow_short_session = False

    with pytest.raises(ValueError, match="hexadecimal source revision"):
        validate_start_values(args)
