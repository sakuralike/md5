from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load_monitoring_validator():
    path = ROOT / "scripts/verify_monitoring_config.py"
    spec = importlib.util.spec_from_file_location("verify_monitoring_config", path)
    if spec is None or spec.loader is None:
        raise AssertionError("monitoring validator cannot be imported")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prometheus_and_grafana_baseline_is_valid():
    report = load_monitoring_validator().validate_monitoring_files(ROOT)
    assert report["status"] == "passed"
    assert report["rule_count"] == 7
    assert report["dashboard_panel_count"] >= 5


def test_worker_backlog_alert_has_a_safe_low_cardinality_expression():
    rules_path = ROOT / "infra/monitoring/prometheus/alerts/password-detective.yml"
    rules = rules_path.read_text(encoding="utf-8")
    assert "PasswordDetectiveWorkerQueueBacklog" in rules
    assert "password_detective_worker_queue_depth >= 20" in rules
    forbidden_terms = (
        "request_id",
        "user_id",
        "email",
        "fingerprint",
        "access_token",
        "refresh_token",
        "secret_value",
    )
    for forbidden in forbidden_terms:
        assert forbidden not in rules.lower()
