from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from verify_recovery_evidence import validate_report


@pytest.fixture
def report() -> dict:
    return {
        "schema": "recovery-drill-v1",
        "status": "passed",
        "summary": {"passed": 3, "failed": 0},
        "timings": {
            "mysql_rpo_seconds": 1.2,
            "mysql_rto_seconds": 4.1,
            "redis_rto_seconds": 3.0,
            "worker_rto_seconds": 5.2,
        },
        "checks": {
            "mysql_backup_restore": {"status": "passed"},
            "redis_loss_recovery": {"status": "passed"},
            "worker_restart_idempotency": {"status": "passed"},
        },
    }


def test_validate_recovery_report(report: dict) -> None:
    validate_report(report)


def test_rejects_slow_recovery(report: dict) -> None:
    report["timings"]["worker_rto_seconds"] = 181
    with pytest.raises(ValueError, match="exceeds threshold"):
        validate_report(report)


def test_rejects_secret_like_fields(report: dict) -> None:
    report["checks"]["redis_loss_recovery"]["token"] = "synthetic"
    with pytest.raises(ValueError, match="secret-like field"):
        validate_report(report)

