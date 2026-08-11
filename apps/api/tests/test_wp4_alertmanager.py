from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load_script(relative_path: str, module_name: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot import {relative_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_notification_gateway_redacts_sensitive_labels_and_annotations():
    receiver = load_script("scripts/alertmanager_receiver.py", "alertmanager_receiver")
    event = receiver.normalize_alertmanager_payload(
        {
            "status": "firing",
            "receiver": "password-detective-notification-gateway",
            "groupKey": "synthetic-group",
            "commonLabels": {"alertname": "SyntheticAlert", "user_id": "usr-secret"},
            "commonAnnotations": {"secret_value": "synthetic-secret"},
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "SyntheticAlert",
                        "severity": "warning",
                        "service": "worker",
                        "email": "synthetic@example.invalid",
                    },
                    "annotations": {
                        "summary": "Synthetic notification",
                        "access_token": "synthetic-token",
                    },
                    "startsAt": "2026-08-10T00:00:00Z",
                    "endsAt": "2026-08-10T00:10:00Z",
                    "fingerprint": "synthetic-fingerprint",
                }
            ],
        }
    )
    assert event["common_labels"]["user_id"] == receiver.REDACTED
    assert event["common_annotations"]["secret_value"] == receiver.REDACTED
    assert event["alerts"][0]["labels"]["email"] == receiver.REDACTED
    assert event["alerts"][0]["annotations"]["access_token"] == receiver.REDACTED
    assert event["alerts"][0]["fingerprint"] == receiver.REDACTED
    assert event["alerts"][0]["labels"]["alertname"] == "SyntheticAlert"


def test_alertmanager_config_is_wired_for_grouping_and_resolved_delivery():
    validator = load_script("scripts/verify_monitoring_config.py", "monitoring_validator_v2")
    report = validator.validate_monitoring_files(ROOT)
    assert report["schema"] == "monitoring-config-v4"
    assert "infra/monitoring/alertmanager/alertmanager.yml" in report["files"]
    assert "scripts/alertmanager_receiver.py" in report["files"]
