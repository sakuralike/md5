from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "verify_performance_evidence.py"
SPEC = importlib.util.spec_from_file_location("verify_performance_evidence", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def valid_report() -> dict:
    metrics = {name: True for name in MODULE._REQUIRED_METRICS}
    workloads = []
    for name, p95, threshold, qps in (
        ("liveness_100qps", 20.0, 250.0, 100.0),
        ("archives_search", 30.0, 500.0, 10.0),
    ):
        workloads.append(
            {
                "name": name,
                "status": "passed",
                "target_qps": qps,
                "achieved_qps": qps,
                "error_rate": 0.0,
                "latency_ms": {"p95": p95},
                "thresholds": {
                    "p95_ms": threshold,
                    "max_error_rate": 0.01,
                    "min_target_qps_ratio": 0.8,
                },
            }
        )
    return {
        "schema": "performance-baseline-v1",
        "status": "passed",
        "environment": "isolated-integration",
        "workloads": workloads,
        "observability": {
            "status": "passed",
            "required_metrics": metrics,
            "normalized_archive_route": True,
            "request_id_echo": True,
            "request_id_not_exported": True,
            "sensitive_query_not_exported": True,
        },
        "summary": {"passed": 3, "failed": 0},
    }


def test_accepts_valid_report():
    MODULE.verify_report(valid_report())


def test_rejects_p95_regression():
    report = valid_report()
    report["workloads"][1]["latency_ms"]["p95"] = 501.0
    with pytest.raises(ValueError, match="p95 exceeded"):
        MODULE.verify_report(report)


def test_rejects_high_cardinality_sensitive_value():
    report = copy.deepcopy(valid_report())
    report["unexpected"] = "a" * 64
    with pytest.raises(ValueError, match="secret-like value"):
        MODULE.verify_report(report)
