from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from materialize_staging_execution_evidence import (
    generate_contract_sources,
    materialize_bundle,
    materialize_ha_report,
    materialize_resource_report,
)
from verify_staging_execution_evidence import (
    validate_ha_report,
    validate_resource_report,
)
from verify_staging_readiness_profile import normalized_file_sha256

PROFILE_PATH = ROOT / "infra/staging/readiness-profile.example.json"
PROFILE = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
PROFILE_SHA = normalized_file_sha256(PROFILE_PATH)


def load_generated_sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    return generate_contract_sources(tmp_path / "sources", PROFILE)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_materializes_sanitized_contract_reports(tmp_path: Path) -> None:
    resource_source, mysql_source, redis_source = load_generated_sources(tmp_path)

    reports = materialize_bundle(
        PROFILE_PATH,
        resource_source,
        mysql_source,
        redis_source,
        tmp_path / "reports",
    )

    resource = load_json(reports["resource"])
    mysql = load_json(reports["mysql"])
    redis = load_json(reports["redis"])
    assert resource["sample_count"] == 961
    assert resource["coverage_percent"] == 100
    assert resource["celery_queue"]["final_depth"] == 0
    assert "samples" not in resource
    assert resource["provenance"]["source_sha256"]
    assert mysql["rto_seconds"] == 42
    assert redis["rto_seconds"] == 28
    validate_resource_report(resource, PROFILE, PROFILE_SHA)
    validate_ha_report(mysql, PROFILE, PROFILE_SHA, "mysql")
    validate_ha_report(redis, PROFILE, PROFILE_SHA, "redis")


def test_materializes_real_adapter_sources_as_target_execution(tmp_path: Path) -> None:
    resource_source, mysql_source, redis_source = load_generated_sources(tmp_path)
    for path, adapter in (
        (resource_source, "prometheus-resource-export-v1"),
        (mysql_source, "managed-mysql-event-export-v1"),
        (redis_source, "managed-redis-event-export-v1"),
    ):
        source = load_json(path)
        source["evidence_kind"] = "target-execution"
        source["source_adapter"] = adapter
        path.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")

    reports = materialize_bundle(
        PROFILE_PATH,
        resource_source,
        mysql_source,
        redis_source,
        tmp_path / "target-reports",
    )

    assert load_json(reports["resource"])["evidence_kind"] == "target-execution"
    assert load_json(reports["mysql"])["evidence_kind"] == "target-execution"
    assert (tmp_path / "target-reports/source-checksums.sha256").is_file()


def test_rejects_mixed_execution_groups(tmp_path: Path) -> None:
    resource_source, mysql_source, redis_source = load_generated_sources(tmp_path)
    mysql = load_json(mysql_source)
    mysql["execution_group_id"] = "different-execution-group"
    mysql_source.write_text(json.dumps(mysql, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="share one execution_group_id"):
        materialize_bundle(
            PROFILE_PATH,
            resource_source,
            mysql_source,
            redis_source,
            tmp_path / "reports",
        )


def test_rejects_secret_like_source_fields(tmp_path: Path) -> None:
    resource_source, _, _ = load_generated_sources(tmp_path)
    source = load_json(resource_source)
    source["access_token"] = "synthetic-value"

    with pytest.raises(ValueError, match="secret-like field"):
        materialize_resource_report(source, PROFILE, PROFILE_SHA, "0" * 64)


def test_rejects_target_execution_from_fixture_adapter(tmp_path: Path) -> None:
    resource_source, _, _ = load_generated_sources(tmp_path)
    source = load_json(resource_source)
    source["evidence_kind"] = "target-execution"

    with pytest.raises(ValueError, match="cannot use a fixture"):
        materialize_resource_report(source, PROFILE, PROFILE_SHA, "0" * 64)


def test_rejects_sparse_resource_timeline(tmp_path: Path) -> None:
    resource_source, _, _ = load_generated_sources(tmp_path)
    source = load_json(resource_source)
    del source["samples"][100:104]

    with pytest.raises(ValueError, match="sample gap"):
        materialize_resource_report(source, PROFILE, PROFILE_SHA, "0" * 64)


def test_rejects_non_utc_timestamps(tmp_path: Path) -> None:
    resource_source, _, _ = load_generated_sources(tmp_path)
    source = load_json(resource_source)
    source["samples"][0]["observed_at"] = "2026-08-10T08:00:00+08:00"

    with pytest.raises(ValueError, match="UTC Z"):
        materialize_resource_report(source, PROFILE, PROFILE_SHA, "0" * 64)


def test_rejects_excessive_observed_clock_skew(tmp_path: Path) -> None:
    _, mysql_source, _ = load_generated_sources(tmp_path)
    source = load_json(mysql_source)
    source["clock"]["observed_skew_seconds"] = 6

    with pytest.raises(ValueError, match="clock skew"):
        materialize_ha_report(source, PROFILE, PROFILE_SHA, "0" * 64, "mysql")


def test_rejects_missing_ha_rollback_event(tmp_path: Path) -> None:
    _, mysql_source, _ = load_generated_sources(tmp_path)
    source = load_json(mysql_source)
    source["events"] = [event for event in source["events"] if event["type"] != "rollback_ready"]

    with pytest.raises(ValueError, match="events missing: rollback_ready"):
        materialize_ha_report(source, PROFILE, PROFILE_SHA, "0" * 64, "mysql")


def test_rejects_out_of_order_ha_events(tmp_path: Path) -> None:
    _, mysql_source, _ = load_generated_sources(tmp_path)
    source = load_json(mysql_source)
    changed = copy.deepcopy(source)
    changed["events"][2]["observed_at"] = changed["events"][0]["observed_at"]

    with pytest.raises(ValueError, match="strictly increasing"):
        materialize_ha_report(changed, PROFILE, PROFILE_SHA, "0" * 64, "mysql")
