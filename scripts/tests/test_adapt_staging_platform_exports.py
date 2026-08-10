from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from adapt_staging_platform_exports import (
    adapt_bundle,
    adapt_ha_export,
    adapt_resource_export,
    generate_contract_exports,
)
from materialize_staging_execution_evidence import materialize_bundle

PROFILE_PATH = ROOT / "infra/staging/readiness-profile.example.json"
PROFILE = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def generated_exports(tmp_path: Path) -> tuple[Path, Path, Path]:
    return generate_contract_exports(tmp_path / "exports", PROFILE)


def test_adapts_contract_exports_and_materializes_evidence(tmp_path: Path) -> None:
    resource_export, mysql_export, redis_export = generated_exports(tmp_path)
    sources = adapt_bundle(
        PROFILE_PATH,
        resource_export,
        mysql_export,
        redis_export,
        tmp_path / "sources",
    )
    reports = materialize_bundle(PROFILE_PATH, *sources, tmp_path / "reports")

    resource = load_json(sources[0])
    mysql = load_json(sources[1])
    assert len(resource["samples"]) == 961
    assert resource["samples"][0]["resources"]["api"]["cpu_percent"] == 42
    assert mysql["events"][0]["provider_event_sha256"]
    assert load_json(reports["resource"])["evidence_kind"] == "contract-fixture"


def test_adapts_non_fixture_platform_exports_as_target_execution(tmp_path: Path) -> None:
    paths = generated_exports(tmp_path)
    adapters = (
        "prometheus-query-range-v1",
        "managed-mysql-events-v1",
        "managed-redis-events-v1",
    )
    for path, adapter in zip(paths, adapters, strict=True):
        export = load_json(path)
        export["evidence_kind"] = "target-execution"
        export["source_adapter"] = adapter
        write_json(path, export)

    sources = adapt_bundle(PROFILE_PATH, *paths, tmp_path / "sources")

    assert load_json(sources[0])["evidence_kind"] == "target-execution"
    assert load_json(sources[1])["source_adapter"] == "managed-mysql-events-v1"


def test_rejects_target_execution_from_fixture_export(tmp_path: Path) -> None:
    resource_path, _, _ = generated_exports(tmp_path)
    resource = load_json(resource_path)
    resource["evidence_kind"] = "target-execution"

    with pytest.raises(ValueError, match="cannot use a fixture"):
        adapt_resource_export(resource, PROFILE)


def test_rejects_missing_canonical_prometheus_metric(tmp_path: Path) -> None:
    resource_path, _, _ = generated_exports(tmp_path)
    resource = load_json(resource_path)
    del resource["series"]["redis_memory_mebibytes"]

    with pytest.raises(ValueError, match="canonical metrics"):
        adapt_resource_export(resource, PROFILE)


def test_rejects_fractional_sample_interval(tmp_path: Path) -> None:
    resource_path, _, _ = generated_exports(tmp_path)
    resource = load_json(resource_path)
    resource["sample_interval_seconds"] = 15.5

    with pytest.raises(ValueError, match="whole number"):
        adapt_resource_export(resource, PROFILE)


def test_rejects_misaligned_prometheus_timestamps(tmp_path: Path) -> None:
    resource_path, _, _ = generated_exports(tmp_path)
    resource = load_json(resource_path)
    resource["series"]["mysql_cpu_percent"]["data"]["result"][0]["values"][4][0] += 1

    with pytest.raises(ValueError, match="timestamps do not align"):
        adapt_resource_export(resource, PROFILE)


def test_rejects_duplicate_prometheus_timestamp(tmp_path: Path) -> None:
    resource_path, _, _ = generated_exports(tmp_path)
    resource = load_json(resource_path)
    values = resource["series"]["api_cpu_percent"]["data"]["result"][0]["values"]
    values[3][0] = values[2][0]

    with pytest.raises(ValueError, match="strictly increasing"):
        adapt_resource_export(resource, PROFILE)


def test_rejects_non_integral_connection_metric(tmp_path: Path) -> None:
    resource_path, _, _ = generated_exports(tmp_path)
    resource = load_json(resource_path)
    values = resource["series"]["database_connections"]["data"]["result"][0]["values"]
    values[10][1] = "82.5"

    with pytest.raises(ValueError, match="whole-number"):
        adapt_resource_export(resource, PROFILE)


def test_rejects_secret_like_prometheus_label(tmp_path: Path) -> None:
    resource_path, _, _ = generated_exports(tmp_path)
    resource = load_json(resource_path)
    metric = resource["series"]["api_cpu_percent"]["data"]["result"][0]["metric"]
    metric["authorization"] = "synthetic"

    with pytest.raises(ValueError, match="secret-like field"):
        adapt_resource_export(resource, PROFILE)


def test_rejects_raw_ha_provider_identifier(tmp_path: Path) -> None:
    _, mysql_path, _ = generated_exports(tmp_path)
    mysql = load_json(mysql_path)
    mysql["events"][0]["provider_event_id"] = "raw-provider-event"

    with pytest.raises(ValueError, match="unsupported fields"):
        adapt_ha_export(mysql, PROFILE, "mysql")


def test_rejects_fractional_lost_records(tmp_path: Path) -> None:
    _, mysql_path, _ = generated_exports(tmp_path)
    mysql = load_json(mysql_path)
    mysql["durability"]["lost_records"] = 0.5

    with pytest.raises(ValueError, match="whole number"):
        adapt_ha_export(mysql, PROFILE, "mysql")


def test_rejects_invalid_ha_provider_digest(tmp_path: Path) -> None:
    _, mysql_path, _ = generated_exports(tmp_path)
    mysql = load_json(mysql_path)
    mysql["events"][0]["provider_event_sha256"] = "not-a-digest"

    with pytest.raises(ValueError, match="lowercase SHA-256"):
        adapt_ha_export(mysql, PROFILE, "mysql")


def test_rejects_mixed_platform_export_groups(tmp_path: Path) -> None:
    resource_path, mysql_path, redis_path = generated_exports(tmp_path)
    mysql = load_json(mysql_path)
    mysql["execution_group_id"] = "another-group"
    write_json(mysql_path, mysql)

    with pytest.raises(ValueError, match="share one execution_group_id"):
        adapt_bundle(
            PROFILE_PATH,
            resource_path,
            mysql_path,
            redis_path,
            tmp_path / "sources",
        )


def test_rejects_ha_dependency_mismatch(tmp_path: Path) -> None:
    _, mysql_path, _ = generated_exports(tmp_path)
    mysql = copy.deepcopy(load_json(mysql_path))
    mysql["dependency"] = "redis"

    with pytest.raises(ValueError, match="must be mysql"):
        adapt_ha_export(mysql, PROFILE, "mysql")
