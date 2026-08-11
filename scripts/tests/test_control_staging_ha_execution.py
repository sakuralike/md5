from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from control_staging_ha_execution import SCHEMA, build_preflight
from verify_staging_readiness_profile import normalized_file_sha256

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "infra/staging/readiness-profile.example.json"


def write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def make_completed_state(tmp_path: Path) -> Path:
    output = tmp_path / "formal-output"
    verification_path = output / "staging-resource-samples-verification.json"
    write_json(
        verification_path,
        {
            "status": "passed",
            "eligible_for_target_execution": True,
            "execution_status": "target-execution",
            "duration_seconds": 14400,
        },
    )
    state_path = tmp_path / "formal-control.json"
    write_json(
        state_path,
        {
            "schema": "staging-formal-session-control-v1",
            "run_id": "formal-synthetic-run",
            "status": "completed",
            "source_revision": "a" * 40,
            "output_directory": str(output),
            "verification": {
                "verification_status": "passed",
                "eligible_for_target_execution": True,
                "execution_status": "target-execution",
                "duration_seconds": 14400,
                "verification_sha256": hashlib.sha256(
                    verification_path.read_bytes()
                ).hexdigest(),
            },
        },
    )
    return state_path


def make_mysql_report(tmp_path: Path, evidence_kind: str = "target-execution") -> Path:
    source = ROOT / "infra/staging/mysql-ha-failover-report.example.json"
    report = json.loads(source.read_text(encoding="utf-8"))
    report["evidence_kind"] = evidence_kind
    report["profile_sha256"] = normalized_file_sha256(PROFILE)
    path = tmp_path / "mysql-ha-failover-report.json"
    write_json(path, report)
    return path


def make_capability(
    tmp_path: Path, dependency: str, evidence_kind: str = "target-observation"
) -> Path:
    source = ROOT / f"infra/staging/{dependency}-ha-target-capability.example.json"
    report = json.loads(source.read_text(encoding="utf-8"))
    report["evidence_kind"] = evidence_kind
    report["source_adapter"] = (
        "managed-platform-capability-export-v1"
        if evidence_kind == "target-observation"
        else "contract-fixture-generator-v1"
    )
    path = tmp_path / f"{dependency}-ha-target-capability.json"
    write_json(path, report)
    return path


def test_mysql_ready_after_completed_digest_bound_formal_session(
    tmp_path: Path,
) -> None:
    report = build_preflight(
        make_completed_state(tmp_path),
        PROFILE,
        ROOT,
        "mysql",
        capability_path=make_capability(tmp_path, "mysql"),
    )

    assert report["schema"] == SCHEMA
    assert report["status"] == "ready"
    assert report["blocked_reasons"] == []
    assert all(report["checks"].values())


def test_running_formal_session_blocks_mysql(tmp_path: Path) -> None:
    state_path = make_completed_state(tmp_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "running"
    state.pop("verification")
    write_json(state_path, state)

    report = build_preflight(
        state_path,
        PROFILE,
        ROOT,
        "mysql",
        capability_path=make_capability(tmp_path, "mysql"),
    )

    assert report["status"] == "blocked"
    assert report["checks"]["formal_completed"] is False
    assert report["checks"]["verification_passed"] is False


def test_changed_verification_report_blocks_execution(tmp_path: Path) -> None:
    state_path = make_completed_state(tmp_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    report_path = (
        Path(str(state["output_directory"]))
        / "staging-resource-samples-verification.json"
    )
    report_path.write_text(
        report_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )

    report = build_preflight(
        state_path,
        PROFILE,
        ROOT,
        "mysql",
        capability_path=make_capability(tmp_path, "mysql"),
    )

    assert report["status"] == "blocked"
    assert report["checks"]["verification_digest"] is False


def test_redis_requires_mysql_target_execution_evidence(tmp_path: Path) -> None:
    report = build_preflight(
        make_completed_state(tmp_path),
        PROFILE,
        ROOT,
        "redis",
        capability_path=make_capability(tmp_path, "redis"),
    )

    assert report["status"] == "blocked"
    assert report["checks"]["mysql_evidence_present"] is False
    assert report["checks"]["mysql_target_execution_passed"] is False


def test_redis_rejects_mysql_contract_fixture(tmp_path: Path) -> None:
    report = build_preflight(
        make_completed_state(tmp_path),
        PROFILE,
        ROOT,
        "redis",
        make_mysql_report(tmp_path, "contract-fixture"),
        make_capability(tmp_path, "redis"),
    )

    assert report["status"] == "blocked"
    assert report["checks"]["mysql_evidence_present"] is True
    assert report["checks"]["mysql_target_execution_passed"] is False


def test_redis_ready_after_mysql_target_execution(tmp_path: Path) -> None:
    report = build_preflight(
        make_completed_state(tmp_path),
        PROFILE,
        ROOT,
        "redis",
        make_mysql_report(tmp_path),
        make_capability(tmp_path, "redis"),
    )

    assert report["status"] == "ready"
    assert report["prerequisite"]["dependency"] == "mysql"
    assert len(report["prerequisite"]["report_sha256"]) == 64


def test_mysql_requires_target_capability_evidence(tmp_path: Path) -> None:
    report = build_preflight(make_completed_state(tmp_path), PROFILE, ROOT, "mysql")

    assert report["status"] == "blocked"
    assert report["checks"]["target_capability_present"] is False


def test_mysql_rejects_capability_contract_fixture(tmp_path: Path) -> None:
    report = build_preflight(
        make_completed_state(tmp_path),
        PROFILE,
        ROOT,
        "mysql",
        capability_path=make_capability(tmp_path, "mysql", "contract-fixture"),
    )

    assert report["status"] == "blocked"
    assert report["checks"]["target_capability_valid"] is True
    assert report["checks"]["target_capability_observed"] is False


def test_gate_output_does_not_include_secret_like_fields(tmp_path: Path) -> None:
    serialized = json.dumps(
        build_preflight(
            make_completed_state(tmp_path),
            PROFILE,
            ROOT,
            "mysql",
            capability_path=make_capability(tmp_path, "mysql"),
        )
    ).lower()

    assert "password" not in serialized
    assert "token" not in serialized
    assert "connection_string" not in serialized
