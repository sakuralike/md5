from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from verify_staging_ha_target_capability import load_json, validate_capability

ROOT = Path(__file__).resolve().parents[2]
PROFILE = load_json(ROOT / "infra/staging/readiness-profile.example.json")


def capability(dependency: str) -> dict[str, object]:
    return load_json(
        ROOT / f"infra/staging/{dependency}-ha-target-capability.example.json"
    )


def target_observation(dependency: str) -> dict[str, object]:
    report = capability(dependency)
    report["evidence_kind"] = "target-observation"
    report["source_adapter"] = "managed-platform-capability-export-v1"
    return report


def test_mysql_contract_fixture_is_valid_but_remains_fixture() -> None:
    summary = validate_capability(capability("mysql"), PROFILE, ROOT, "mysql")

    assert summary["evidence_kind"] == "contract-fixture"
    assert summary["deployment_model"] == "managed-service"


def test_mysql_target_observation_is_accepted() -> None:
    summary = validate_capability(target_observation("mysql"), PROFILE, ROOT, "mysql")

    assert summary["evidence_kind"] == "target-observation"
    assert summary["failure_domains"] == 2


def test_mysql_rejects_single_node_compose_capability() -> None:
    report = target_observation("mysql")
    topology = report["topology"]
    assert isinstance(topology, dict)
    topology["deployment_model"] = "single-node-compose"
    topology["failure_domains"] = 1
    topology["standby_replicas"] = 0

    with pytest.raises(ValueError, match="managed-service"):
        validate_capability(report, PROFILE, ROOT, "mysql")


def test_target_observation_rejects_fixture_adapter() -> None:
    report = capability("redis")
    report["evidence_kind"] = "target-observation"

    with pytest.raises(ValueError, match="cannot use a fixture"):
        validate_capability(report, PROFILE, ROOT, "redis")


def test_redis_sentinel_requires_three_sentinels() -> None:
    report = target_observation("redis")
    topology = report["topology"]
    assert isinstance(topology, dict)
    topology["deployment_model"] = "self-managed-sentinel"
    topology["sentinel_replicas"] = 2

    with pytest.raises(ValueError, match="at least 3"):
        validate_capability(report, PROFILE, ROOT, "redis")


def test_capability_rejects_target_addresses_and_secrets() -> None:
    report = target_observation("mysql")
    report["database_endpoint"] = "synthetic.invalid"

    with pytest.raises(ValueError, match="target address"):
        validate_capability(report, PROFILE, ROOT, "mysql")


def test_capability_rejects_rto_above_profile() -> None:
    report = copy.deepcopy(target_observation("mysql"))
    limits = report["limits"]
    assert isinstance(limits, dict)
    limits["rto_seconds"] = 121

    with pytest.raises(ValueError, match="RTO"):
        validate_capability(report, PROFILE, ROOT, "mysql")


def test_examples_are_serializable_without_secret_fields() -> None:
    serialized = json.dumps(
        {"mysql": capability("mysql"), "redis": capability("redis")}
    ).lower()

    assert "password" not in serialized
    assert "token" not in serialized
    assert "endpoint" not in serialized
