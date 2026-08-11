from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from verify_multi_instance_stability_evidence import validate_report


def valid_report() -> dict:
    operations = {
        name: {"count": 20, "p95_ms": 10.0, "max_ms": 20.0}
        for name in ("api", "mysql", "redis", "celery")
    }
    return {
        "schema": "multi-instance-stability-drill-v1",
        "status": "passed",
        "configuration": {"worker_count": 3, "duration_seconds": 60},
        "checks": {
            "initial_workers": {"status": "passed", "observed": 3},
            "single_worker_loss": {
                "status": "passed",
                "observed": 2,
                "worker_dependency_up": 1,
            },
            "worker_replacement": {"status": "passed", "observed": 3},
            "queue_drained": {"status": "passed", "observed_depth": 0},
            "final_readiness": {"status": "passed", "http_status": 200},
        },
        "probe": {
            "schema": "multi-instance-stability-probe-v1",
            "status": "passed",
            "error_count": 0,
            "operations": operations,
        },
    }


def test_accepts_valid_report() -> None:
    validate_report(valid_report())


def test_rejects_worker_dependency_outage() -> None:
    report = valid_report()
    report["checks"]["single_worker_loss"]["worker_dependency_up"] = 0
    with pytest.raises(ValueError, match="became unavailable"):
        validate_report(report)


def test_rejects_short_or_sparse_probe() -> None:
    report = valid_report()
    report["probe"]["operations"]["mysql"]["count"] = 9
    with pytest.raises(ValueError, match="at least ten"):
        validate_report(report)


def test_rejects_secret_like_evidence() -> None:
    report = copy.deepcopy(valid_report())
    report["unexpected_password"] = "synthetic"
    with pytest.raises(ValueError, match="secret-like field"):
        validate_report(report)


def test_accepts_v2_windowed_probe_report() -> None:
    report = valid_report()
    report["probe"]["schema"] = "multi-instance-stability-probe-v2"
    report["probe"]["probe_windows"] = []
    validate_report(report)
