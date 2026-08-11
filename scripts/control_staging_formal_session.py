from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA = "staging-formal-session-control-v1"
DEFAULT_COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.staging.override.yml",
    "infra/staging/docker-compose.staging.api-ha.yml",
    "infra/monitoring/docker-compose.monitoring.yml",
    "infra/staging/docker-compose.staging.monitoring.yml",
)


def format_utc(value: Optional[datetime] = None) -> str:  # noqa: UP045 - target host Python 3.9
    current = value or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    temporary.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError(f"JSON object required: {path}")
    return parsed


def process_start_marker(pid: int) -> Optional[str]:  # noqa: UP045 - target host Python 3.9
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        remainder = stat_path.read_text(encoding="utf-8").rpartition(") ")[2]
    except OSError:
        return None
    fields = remainder.split()
    return fields[19] if len(fields) > 19 else None


def process_is_running(pid: int, marker: Optional[str] = None) -> bool:  # noqa: UP045 - target host Python 3.9
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
            process_query_limited_information, False, pid
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(  # type: ignore[attr-defined]
                handle, ctypes.byref(exit_code)
            ):
                return False
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    current_marker = process_start_marker(pid)
    return marker is None or current_marker is None or current_marker == marker


@contextmanager
def state_lock(state_path: Path) -> Iterator[None]:
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(2):
        try:
            descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"pid": os.getpid(), "created_at": format_utc()}))
            break
        except FileExistsError:
            if attempt > 0:
                raise RuntimeError(f"session control is locked: {lock_path}") from None
            try:
                lock = load_json(lock_path)
                owner_pid = int(lock.get("pid", 0))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                owner_pid = 0
            if process_is_running(owner_pid):
                raise RuntimeError(f"session control is locked by process {owner_pid}") from None
            lock_path.unlink(missing_ok=True)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def summarize_verification(path: Path) -> dict[str, Any]:
    report = load_json(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "verification_sha256": digest,
        "verification_status": report.get("status"),
        "eligible_for_target_execution": bool(report.get("eligible_for_target_execution", False)),
        "execution_status": report.get("execution_status"),
        "duration_seconds": report.get("duration_seconds"),
        "error_rate_percent": report.get("error_rate_percent"),
        "coverage_percent": report.get("coverage_percent"),
        "final_queue_depth": report.get("final_queue_depth"),
        "checks": report.get("checks", {}),
    }


def public_state(state: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "schema",
        "run_id",
        "status",
        "source_revision",
        "started_at",
        "finished_at",
        "pid",
        "duration_seconds",
        "output_directory",
        "log_file",
        "exit_code",
        "failure",
        "verification",
    )
    return {key: state[key] for key in allowed if key in state}


def reconcile_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {"schema": SCHEMA, "status": "idle"}
    state = load_json(state_path)
    if state.get("schema") != SCHEMA:
        raise ValueError(f"unsupported session control schema: {state.get('schema')}")
    if state.get("status") not in {"launching", "running"}:
        return state
    pid = int(state.get("pid") or 0)
    marker_value = state.get("process_start_marker")
    marker = str(marker_value) if marker_value is not None else None
    if process_is_running(pid, marker):
        return state
    verification_path = Path(str(state["output_directory"])) / "staging-resource-samples-verification.json"
    state["finished_at"] = format_utc()
    if verification_path.exists():
        state["verification"] = summarize_verification(verification_path)
        state["status"] = "completed" if state["verification"]["verification_status"] == "passed" else "failed"
    else:
        state["status"] = "interrupted"
        state["failure"] = "supervisor exited before producing a verification report"
    atomic_write_json(state_path, state)
    return state


def validate_start_values(args: argparse.Namespace) -> None:
    if (
        not args.observation_only
        and re.fullmatch(r"[0-9a-fA-F]{7,64}", args.source_revision) is None
    ):
        raise ValueError(
            "target execution requires a 7-64 character hexadecimal source revision"
        )
    if args.duration_seconds < 14400 and not args.allow_short_session:
        raise ValueError("formal session duration must be at least 14400 seconds")
    if args.duration_seconds < 60:
        raise ValueError("duration must be at least 60 seconds")
    if args.worker_count < 2:
        raise ValueError("at least two Workers are required")
    if not 15 <= args.worker_loss_after_seconds <= args.duration_seconds - 30:
        raise ValueError("Worker loss timing does not fit inside the session")
    if not 5 <= args.worker_loss_duration_seconds <= args.duration_seconds - args.worker_loss_after_seconds - 10:
        raise ValueError("Worker loss duration does not fit inside the session")
    if not 5 <= args.probe_window_seconds <= args.duration_seconds - 5:
        raise ValueError("probe window does not fit inside the session")


def build_runner_command(args: argparse.Namespace, root: Path, output_directory: Path) -> list[str]:
    command = [
        sys.executable,
        str(root / "scripts/run_staging_stability_session.py"),
        "--profile",
        str(Path(args.profile).resolve()),
        "--duration-seconds",
        str(args.duration_seconds),
        "--probe-interval-seconds",
        str(args.probe_interval_seconds),
        "--probe-window-seconds",
        str(args.probe_window_seconds),
        "--resource-sample-interval-seconds",
        str(args.resource_sample_interval_seconds),
        "--worker-count",
        str(args.worker_count),
        "--worker-loss-after-seconds",
        str(args.worker_loss_after_seconds),
        "--worker-loss-duration-seconds",
        str(args.worker_loss_duration_seconds),
        "--api-metrics-url",
        args.api_metrics_url,
        "--output-directory",
        str(output_directory),
    ]
    for compose_file in args.compose_files:
        command.extend(["--compose-file", compose_file])
    if args.project_directory:
        command.extend(["--project-directory", str(Path(args.project_directory).resolve())])
    if not args.observation_only:
        command.append("--request-target-execution")
    return command


def create_launch_state(
    args: argparse.Namespace,
    root: Path,
    output_directory: Path,
    log_file: Path,
    command: Sequence[str],
    run_id: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "run_id": run_id,
        "status": "launching",
        "source_revision": args.source_revision,
        "started_at": format_utc(),
        "pid": None,
        "process_start_marker": None,
        "duration_seconds": args.duration_seconds,
        "output_directory": str(output_directory),
        "log_file": str(log_file),
        "project_directory": str(root),
        "command": list(command),
    }


def start_session(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    validate_start_values(args)
    state_path = Path(args.state_file).resolve()
    output_root = Path(args.output_root).resolve()
    with state_lock(state_path):
        existing = reconcile_state(state_path)
        if existing.get("status") in {"launching", "running"}:
            raise RuntimeError(f"formal session already active: {existing.get('run_id')}")
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{uuid.uuid4().hex[:8]}"
        output_directory = output_root / run_id
        output_directory.mkdir(parents=True, exist_ok=False)
        try:
            os.chmod(output_directory, 0o700)
        except OSError:
            pass
        log_file = output_directory / "formal-session.log"
        command = build_runner_command(args, root, output_directory)
        state = create_launch_state(args, root, output_directory, log_file, command, run_id)
        atomic_write_json(state_path, state)
        supervisor_command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "_supervise",
            "--state-file",
            str(state_path),
            "--run-id",
            run_id,
        ]
        with log_file.open("ab", buffering=0) as log_handle:
            try:
                os.chmod(log_file, 0o600)
            except OSError:
                pass
            process = subprocess.Popen(
                supervisor_command,
                cwd=str(root),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        state["pid"] = process.pid
        state["process_start_marker"] = process_start_marker(process.pid)
        state["status"] = "running"
        atomic_write_json(state_path, state)
        return state


def supervise_session(state_path: Path, run_id: str) -> int:
    state: Optional[dict[str, Any]] = None  # noqa: UP045 - target host Python 3.9
    for _ in range(100):
        try:
            candidate = load_json(state_path)
        except (OSError, ValueError, json.JSONDecodeError):
            time.sleep(0.1)
            continue
        if candidate.get("run_id") == run_id and int(candidate.get("pid") or 0) == os.getpid():
            state = candidate
            break
        time.sleep(0.1)
    if state is None:
        print("formal session supervisor could not acquire its launch state", file=sys.stderr)
        return 2
    exit_code = 1
    failure: Optional[str] = None  # noqa: UP045 - target host Python 3.9
    try:
        completed = subprocess.run(
            [str(value) for value in state["command"]],
            cwd=str(state["project_directory"]),
            check=False,
        )
        exit_code = completed.returncode
    except (OSError, ValueError, TypeError) as exc:
        failure = str(exc)
    with state_lock(state_path):
        latest = load_json(state_path)
        if latest.get("run_id") != run_id:
            print("formal session state changed while supervisor was running", file=sys.stderr)
            return 3
        latest["finished_at"] = format_utc()
        latest["exit_code"] = exit_code
        verification_path = Path(str(latest["output_directory"])) / "staging-resource-samples-verification.json"
        if verification_path.exists():
            latest["verification"] = summarize_verification(verification_path)
        if failure is not None:
            latest["failure"] = failure
        verification_passed = latest.get("verification", {}).get("verification_status") == "passed"
        latest["status"] = "completed" if exit_code == 0 and verification_passed else "failed"
        if latest["status"] == "failed" and "failure" not in latest:
            latest["failure"] = f"session runner exited with code {exit_code}"
        atomic_write_json(state_path, latest)
    return exit_code


def add_start_arguments(parser: argparse.ArgumentParser, root: Path) -> None:
    parser.add_argument("--state-file", default=str(root / ".local/staging-formal-session-control.json"))
    parser.add_argument("--output-root", default=str(root / ".local/staging-stability-session-formal"))
    parser.add_argument("--source-revision", default="unknown")
    parser.add_argument("--profile", default=str(root / "infra/staging/readiness-profile.example.json"))
    parser.add_argument("--duration-seconds", type=int, default=14400)
    parser.add_argument("--probe-interval-seconds", type=float, default=1)
    parser.add_argument("--probe-window-seconds", type=int, default=300)
    parser.add_argument("--resource-sample-interval-seconds", type=int, default=15)
    parser.add_argument("--worker-count", type=int, default=3)
    parser.add_argument("--worker-loss-after-seconds", type=int, default=3600)
    parser.add_argument("--worker-loss-duration-seconds", type=int, default=60)
    parser.add_argument("--api-metrics-url", default="http://127.0.0.1:8000/api/v1/metrics")
    parser.add_argument("--compose-file", action="append", dest="compose_files")
    parser.add_argument("--project-directory", default=str(root))
    parser.add_argument("--observation-only", action="store_true")
    parser.add_argument("--allow-short-session", action="store_true", help=argparse.SUPPRESS)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Control a durable WP4 formal Staging stability session.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    start_parser = subparsers.add_parser("start", help="launch a detached formal session")
    add_start_arguments(start_parser, root)
    status_parser = subparsers.add_parser("status", help="report and reconcile the latest session")
    status_parser.add_argument("--state-file", default=str(root / ".local/staging-formal-session-control.json"))
    supervise_parser = subparsers.add_parser("_supervise", help=argparse.SUPPRESS)
    supervise_parser.add_argument("--state-file", required=True)
    supervise_parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.command == "_supervise":
        return supervise_session(Path(args.state_file).resolve(), args.run_id)
    try:
        if args.command == "start":
            args.compose_files = args.compose_files or list(DEFAULT_COMPOSE_FILES)
            state = start_session(args, root)
        else:
            state_path = Path(args.state_file).resolve()
            with state_lock(state_path):
                state = reconcile_state(state_path)
        print(json.dumps(public_state(state), ensure_ascii=False, indent=2))
        return 0
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"formal Staging session control failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
