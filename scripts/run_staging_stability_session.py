from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from assemble_staging_stability_session import assemble_session, load_json, write_json
from collect_staging_resource_observation import compose_prefix
from staging_topology_preflight import (
    SubprocessRunner,
    build_topology_preflight,
    discover_service_counts,
)
from verify_staging_stability_session import validate_session

EVENT_SCHEMA = "staging-worker-recovery-events-v1"


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_checked(arguments: Sequence[str], *, input_bytes: Optional[bytes] = None) -> bytes:  # noqa: UP045 - target host Python 3.9
    completed = subprocess.run(
        list(arguments),
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"command failed ({completed.returncode}): {arguments[0]}: {detail[:400]}")
    return completed.stdout


def parse_compose_rows(value: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in value.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        if isinstance(parsed, list):
            rows.extend(row for row in parsed if isinstance(row, dict))
        elif isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def running_worker_names(prefix: Sequence[str]) -> list[str]:
    rows = parse_compose_rows(
        run_checked([*prefix, "ps", "--status", "running", "--format", "json", "worker"])
    )
    names = [str(row.get("Name") or row.get("Names") or "") for row in rows]
    return sorted(name for name in names if name)


def wait_for_worker_count(prefix: Sequence[str], expected: int, timeout_seconds: int) -> int:
    deadline = time.monotonic() + timeout_seconds
    last_count = -1
    while time.monotonic() < deadline:
        last_count = len(running_worker_names(prefix))
        if last_count == expected:
            return last_count
        time.sleep(2)
    raise RuntimeError(f"Worker count did not reach {expected}; last observed count was {last_count}")


def scale_workers(prefix: Sequence[str], count: int) -> None:
    run_checked([*prefix, "up", "--detach", "--no-deps", "--scale", f"worker={count}", "worker"])
    wait_for_worker_count(prefix, count, 120)


def parse_probe_stdout(value: bytes) -> dict[str, Any]:
    for line in reversed(value.decode("utf-8", errors="replace").splitlines()):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and parsed.get("schema") == "multi-instance-stability-probe-v2":
            return parsed
    raise ValueError("operation probe did not emit a v2 JSON report")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a WP4 Staging stability observation session.")
    parser.add_argument("--compose-file", action="append", dest="compose_files", required=True)
    parser.add_argument("--project-directory")
    parser.add_argument("--profile", type=Path, default=Path("infra/staging/readiness-profile.example.json"))
    parser.add_argument("--duration-seconds", type=int, default=120)
    parser.add_argument("--probe-interval-seconds", type=float, default=1)
    parser.add_argument("--probe-window-seconds", type=int, default=30)
    parser.add_argument("--resource-sample-interval-seconds", type=int, default=15)
    parser.add_argument("--worker-count", type=int, default=3)
    parser.add_argument("--worker-loss-after-seconds", type=int, default=40)
    parser.add_argument("--worker-loss-duration-seconds", type=int, default=20)
    parser.add_argument("--api-metrics-url", default="http://127.0.0.1:8000/api/v1/metrics")
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--request-target-execution", action="store_true")
    parser.add_argument("--observed-clock-skew-seconds", type=float, default=0)
    args = parser.parse_args()
    if args.duration_seconds < 60:
        parser.error("duration must be at least 60 seconds")
    if args.worker_count < 2:
        parser.error("at least two Workers are required for a single-Worker loss session")
    if not 15 <= args.worker_loss_after_seconds <= args.duration_seconds - 30:
        parser.error("Worker loss must leave at least 15 seconds before and 30 seconds after the event")
    if not 5 <= args.worker_loss_duration_seconds <= args.duration_seconds - args.worker_loss_after_seconds - 10:
        parser.error("Worker loss duration does not fit inside the session")
    probe_duration = args.duration_seconds - 5
    if not 5 <= args.probe_window_seconds <= probe_duration:
        parser.error("probe window does not fit inside the operation probe duration")

    root = Path(__file__).resolve().parent.parent
    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    resource_path = output_directory / "resource-observation.json"
    probe_path = output_directory / "operation-probe.json"
    event_path = output_directory / "worker-recovery-events.json"
    preflight_path = output_directory / "topology-capacity-preflight.json"
    source_path = output_directory / "staging-resource-samples.json"
    verification_path = output_directory / "staging-resource-samples-verification.json"
    prefix = compose_prefix(args.compose_files, args.project_directory)
    original_worker_count = 0
    resource_process: Optional[subprocess.Popen[bytes]] = None  # noqa: UP045 - target host Python 3.9
    probe_process: Optional[subprocess.Popen[bytes]] = None  # noqa: UP045 - target host Python 3.9
    try:
        profile = load_json(args.profile)
        required_workers = int(profile["topology"]["worker_replicas"])
        if args.worker_count != required_workers:
            raise ValueError(
                f"worker-count must match profile topology ({required_workers})"
            )
        original_worker_count = len(running_worker_names(prefix))
        if original_worker_count < 1:
            raise RuntimeError("Staging must have at least one running Worker before the session")
        scale_workers(prefix, args.worker_count)
        service_counts, _ = discover_service_counts(
            SubprocessRunner(), args.compose_files, args.project_directory
        )
        topology_preflight = build_topology_preflight(profile, service_counts)
        write_json(preflight_path, topology_preflight)

        resource_command = [
            sys.executable,
            str(root / "scripts/collect_staging_resource_observation.py"),
            "--api-metrics-url",
            args.api_metrics_url,
            "--duration-seconds",
            str(args.duration_seconds),
            "--sample-interval-seconds",
            str(args.resource_sample_interval_seconds),
            "--output",
            str(resource_path),
        ]
        if args.project_directory:
            resource_command.extend(["--project-directory", args.project_directory])
        for compose_file in args.compose_files:
            resource_command.extend(["--compose-file", compose_file])
        resource_process = subprocess.Popen(
            resource_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(1)

        probe_source = (root / "scripts/multi_instance_stability_probe.py").read_bytes()
        probe_command = [
            *prefix,
            "exec",
            "-T",
            "api",
            "python",
            "-",
            "--duration-seconds",
            str(probe_duration),
            "--interval-seconds",
            str(args.probe_interval_seconds),
            "--window-seconds",
            str(args.probe_window_seconds),
        ]
        probe_process = subprocess.Popen(
            probe_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if probe_process.stdin is None:
            raise RuntimeError("operation probe stdin was not created")
        probe_process.stdin.write(probe_source)
        probe_process.stdin.close()
        session_started_monotonic = time.monotonic()

        loss_deadline = session_started_monotonic + args.worker_loss_after_seconds
        time.sleep(max(0, loss_deadline - time.monotonic()))
        worker_names = running_worker_names(prefix)
        if len(worker_names) != args.worker_count:
            raise RuntimeError("Worker scale changed before the loss event")
        selected_worker = worker_names[0]
        run_checked(["docker", "stop", "--time", "10", selected_worker])
        lost_at = datetime.now(timezone.utc)
        degraded_workers = wait_for_worker_count(prefix, args.worker_count - 1, 45)

        time.sleep(args.worker_loss_duration_seconds)
        recovery_started = datetime.now(timezone.utc)
        run_checked(["docker", "start", selected_worker])
        recovered_workers = wait_for_worker_count(prefix, args.worker_count, 90)
        recovered_at = datetime.now(timezone.utc)
        worker_events = {
            "schema": EVENT_SCHEMA,
            "status": "passed",
            "environment": "staging",
            "synthetic_data_only": True,
            "events": [
                {"type": "worker_lost", "observed_at": format_utc(lost_at)},
                {"type": "worker_recovered", "observed_at": format_utc(recovered_at)},
            ],
            "summary": {
                "initial_workers": args.worker_count,
                "degraded_workers": degraded_workers,
                "recovered_workers": recovered_workers,
                "recovery_seconds": round((recovered_at - recovery_started).total_seconds(), 3),
            },
        }
        write_json(event_path, worker_events)

        probe_return = probe_process.wait(timeout=probe_duration + 60)
        probe_stdout = probe_process.stdout.read() if probe_process.stdout is not None else b""
        probe_stderr = probe_process.stderr.read() if probe_process.stderr is not None else b""
        probe_report = parse_probe_stdout(probe_stdout)
        write_json(probe_path, probe_report)
        if probe_return not in (0, 1):
            detail = probe_stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"operation probe failed with exit code {probe_return}: {detail[:300]}")

        resource_return = resource_process.wait(timeout=args.duration_seconds + 90)
        if resource_return != 0:
            detail = resource_process.stderr.read().decode("utf-8", errors="replace") if resource_process.stderr is not None else ""
            raise RuntimeError(f"resource collector failed with exit code {resource_return}: {detail[:300]}")

        source = assemble_session(
            load_json(resource_path),
            probe_report,
            worker_events,
            topology_preflight,
            profile,
            request_target_execution=args.request_target_execution,
            observed_clock_skew_seconds=args.observed_clock_skew_seconds,
        )
        write_json(source_path, source)
        report = validate_session(source, profile)
        write_json(verification_path, report)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"Staging stability session failed: {exc}", file=sys.stderr)
        return 1
    finally:
        for process in (probe_process, resource_process):
            if process is not None and process.poll() is None:
                process.terminate()
        if original_worker_count > 0:
            try:
                scale_workers(prefix, original_worker_count)
            except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                print(f"warning: failed to restore original Worker scale: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
