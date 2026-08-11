from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from verify_staging_execution_evidence import (
    validate_ha_report,
    validate_resource_report,
)
from verify_staging_readiness_profile import normalized_file_sha256, validate_profile

PROFILE_PATH = ROOT / "infra/staging/readiness-profile.example.json"
PROFILE = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
PROFILE_SHA = normalized_file_sha256(PROFILE_PATH)


def load_fixture(name: str) -> dict:
    return json.loads((ROOT / "infra/staging" / name).read_text(encoding="utf-8"))


def test_accepts_valid_resource_trend_fixture() -> None:
    validate_profile(PROFILE, ROOT)
    result = validate_resource_report(load_fixture("resource-trend-report.example.json"), PROFILE, PROFILE_SHA)
    assert result["sample_count"] == 6
    assert result["database_peak"] == 94


def test_rejects_resource_trend_shorter_than_profile() -> None:
    report = load_fixture("resource-trend-report.example.json")
    report["duration_seconds"] = 30
    report["finished_at"] = "2026-08-11T00:00:30Z"
    with pytest.raises(ValueError, match="duration"):
        validate_resource_report(report, PROFILE, PROFILE_SHA)


def test_rejects_resource_limit_breach() -> None:
    report = load_fixture("resource-trend-report.example.json")
    report["resources"]["mysql"]["memory_mebibytes"]["max"] = 4096
    with pytest.raises(ValueError, match="memory resource limit"):
        validate_resource_report(report, PROFILE, PROFILE_SHA)


def test_rejects_connection_budget_breach() -> None:
    report = load_fixture("resource-trend-report.example.json")
    report["database_connections"]["peak"] = 141
    report["database_connections"]["remaining_at_peak"] = 59
    with pytest.raises(ValueError, match="connection peak"):
        validate_resource_report(report, PROFILE, PROFILE_SHA)


def test_rejects_sparse_resource_samples() -> None:
    report = load_fixture("resource-trend-report.example.json")
    report["sample_count"] = 4
    with pytest.raises(ValueError, match="samples"):
        validate_resource_report(report, PROFILE, PROFILE_SHA)


def test_accepts_valid_mysql_ha_fixture() -> None:
    result = validate_ha_report(load_fixture("mysql-ha-failover-report.example.json"), PROFILE, PROFILE_SHA, "mysql")
    assert result["rto_seconds"] == 42
    assert result["rpo_seconds"] == 0


def test_rejects_standalone_redis_mode() -> None:
    report = load_fixture("redis-ha-failover-report.example.json")
    report["mode"] = "standalone"
    with pytest.raises(ValueError, match="mode"):
        validate_ha_report(report, PROFILE, PROFILE_SHA, "redis")


def test_rejects_ha_rto_breach() -> None:
    report = load_fixture("mysql-ha-failover-report.example.json")
    report["rto_seconds"] = 121
    with pytest.raises(ValueError, match="RTO"):
        validate_ha_report(report, PROFILE, PROFILE_SHA, "mysql")


def test_rejects_missing_redis_recovery_check() -> None:
    report = copy.deepcopy(load_fixture("redis-ha-failover-report.example.json"))
    del report["checks"]["celery_recovered"]
    with pytest.raises(ValueError, match="checks missing"):
        validate_ha_report(report, PROFILE, PROFILE_SHA, "redis")


def test_rejects_secret_like_evidence() -> None:
    report = copy.deepcopy(load_fixture("mysql-ha-failover-report.example.json"))
    report["operator_token"] = "synthetic-marker"
    with pytest.raises(ValueError, match="secret-like field"):
        validate_ha_report(report, PROFILE, PROFILE_SHA, "mysql")


def test_rejects_resource_accounting_drift() -> None:
    report = load_fixture("resource-trend-report.example.json")
    report["resource_accounting"]["cpu_scope"] = "service-aggregate"
    with pytest.raises(ValueError, match="resource accounting"):
        validate_resource_report(report, PROFILE, PROFILE_SHA)
