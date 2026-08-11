from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from verify_staging_readiness_profile import build_plan, validate_profile


def repository_root(tmp_path: Path) -> Path:
    runbook = tmp_path / "docs/runbooks/wp4-staging-readiness.md"
    template = tmp_path / "docs/templates/wp4-staging-release-decision.md"
    runbook.parent.mkdir(parents=True)
    template.parent.mkdir(parents=True)
    runbook.write_text("# Runbook\n", encoding="utf-8")
    template.write_text("# Template\n", encoding="utf-8")
    return tmp_path


def valid_profile() -> dict:
    probes = {name: 10_000 for name in ("api", "mysql", "redis", "celery")}
    p95 = {"api": 750, "mysql": 750, "redis": 250, "celery": 5_000}
    return {
        "schema": "staging-readiness-profile-v1",
        "environment": "staging",
        "synthetic_data_only": True,
        "stability": {
            "duration_seconds": 14_400,
            "probe_interval_seconds": 1,
            "resource_sample_interval_seconds": 15,
            "single_worker_loss_required": True,
            "max_error_rate_percent": 0.1,
            "max_consecutive_errors": 3,
            "minimum_operations": probes,
            "p95_limits_ms": p95,
        },
        "topology": {
            "api_replicas": 2,
            "api_processes_per_replica": 2,
            "worker_replicas": 3,
            "worker_processes_per_replica": 2,
            "scheduler_replicas": 1,
        },
        "database_pool": {
            "pool_size": 5,
            "max_overflow": 5,
            "mysql_max_connections": 200,
            "reserved_connections": 30,
            "max_budget_utilization_percent": 80,
        },
        "resource_accounting": {
            "cpu_scope": "per-running-replica-average",
            "memory_scope": "service-aggregate",
        },
        "resource_limits": {
            name: {"max_cpu_percent": 80, "max_memory_mebibytes": 1024}
            for name in ("api", "worker", "mysql", "redis")
        },
        "high_availability": {
            "mysql": {
                "mode": "managed-ha",
                "failover_runbook": "docs/runbooks/wp4-staging-readiness.md",
                "rto_seconds": 120,
                "rpo_seconds": 30,
                "evidence_file": "mysql-ha-failover-report.json",
            },
            "redis": {
                "mode": "sentinel-or-managed-ha",
                "failover_runbook": "docs/runbooks/wp4-staging-readiness.md",
                "rto_seconds": 60,
                "rpo_seconds": 5,
                "evidence_file": "redis-ha-failover-report.json",
            },
        },
        "release_decision": {
            "mode": "automated-evidence-gate",
            "template": "docs/templates/wp4-staging-release-decision.md",
        },
    }


def test_accepts_valid_profile_and_builds_capacity_plan(tmp_path: Path) -> None:
    root = repository_root(tmp_path)
    profile = valid_profile()
    profile_path = tmp_path / "profile.json"
    profile_path.write_text("{}\n", encoding="utf-8")
    plan = build_plan(profile, root, profile_path)
    assert plan["status"] == "contract-valid"
    assert plan["execution_status"] == "not-run"
    assert plan["capacity_budget"] == {
        "client_processes": 11,
        "connections_per_process": 10,
        "requested_connections": 110,
        "usable_connections": 170,
        "allowed_connections": 136,
        "remaining_connections": 26,
    }


def test_rejects_short_stability_window(tmp_path: Path) -> None:
    root = repository_root(tmp_path)
    profile = valid_profile()
    profile["stability"]["duration_seconds"] = 3_600
    with pytest.raises(ValueError, match="at least 14400"):
        validate_profile(profile, root)


def test_rejects_database_pool_overcommit(tmp_path: Path) -> None:
    root = repository_root(tmp_path)
    profile = valid_profile()
    profile["database_pool"]["pool_size"] = 20
    profile["database_pool"]["max_overflow"] = 20
    with pytest.raises(ValueError, match="overcommitted"):
        validate_profile(profile, root)


def test_rejects_multiple_schedulers(tmp_path: Path) -> None:
    root = repository_root(tmp_path)
    profile = valid_profile()
    profile["topology"]["scheduler_replicas"] = 2
    with pytest.raises(ValueError, match="at most 1"):
        validate_profile(profile, root)


def test_rejects_standalone_high_availability_dependency(tmp_path: Path) -> None:
    root = repository_root(tmp_path)
    profile = valid_profile()
    profile["high_availability"]["redis"]["mode"] = "single"
    with pytest.raises(ValueError, match="high availability mode"):
        validate_profile(profile, root)


def test_rejects_non_automated_release_decision_mode(tmp_path: Path) -> None:
    root = repository_root(tmp_path)
    profile = valid_profile()
    profile["release_decision"]["mode"] = "manual-approval"
    with pytest.raises(ValueError, match="automated-evidence-gate"):
        validate_profile(profile, root)


def test_rejects_secret_like_profile_content(tmp_path: Path) -> None:
    root = repository_root(tmp_path)
    profile = copy.deepcopy(valid_profile())
    profile["database_password"] = "synthetic"
    with pytest.raises(ValueError, match="secret-like field"):
        validate_profile(profile, root)


def test_rejects_aggregate_cpu_accounting_scope(tmp_path: Path) -> None:
    root = repository_root(tmp_path)
    profile = valid_profile()
    profile["resource_accounting"]["cpu_scope"] = "service-aggregate"
    with pytest.raises(ValueError, match="per-running-replica-average"):
        validate_profile(profile, root)
