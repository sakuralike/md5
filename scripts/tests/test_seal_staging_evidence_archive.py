from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from materialize_staging_execution_evidence import (
    generate_contract_sources,
    materialize_bundle,
)
from seal_staging_evidence_archive import seal_archive, verify_archive
from verify_staging_execution_evidence import validate_bundle
from verify_staging_readiness_profile import build_plan

PROFILE_PATH = ROOT / "infra/staging/readiness-profile.example.json"
FIXTURE_DIR = ROOT / "infra/staging"
REPORT_NAMES = (
    "resource-trend-report.json",
    "mysql-ha-failover-report.json",
    "redis-ha-failover-report.json",
)


def _make_bundle(tmp_path: Path, evidence_kind: str = "contract-fixture", adapter: str | None = None) -> Path:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    sources = evidence / "sources"
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    source_paths = generate_contract_sources(sources, profile)
    if evidence_kind == "target-execution" or adapter is not None:
        for source_path in source_paths:
            source = json.loads(source_path.read_text(encoding="utf-8"))
            source["evidence_kind"] = evidence_kind
            if adapter is not None:
                source["source_adapter"] = adapter
            source_path.write_text(json.dumps(source, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    materialized = materialize_bundle(PROFILE_PATH, *source_paths, evidence)
    shutil.copy2(PROFILE_PATH, evidence / "readiness-profile.json")
    plan = build_plan(profile, ROOT, PROFILE_PATH)
    plan_path = evidence / "staging-readiness-plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validate_bundle(
        PROFILE_PATH,
        plan_path,
        materialized["resource"],
        materialized["mysql"],
        materialized["redis"],
        evidence / "staging-execution-evidence-summary.json",
        True,
    )
    checksum_path = evidence / "checksums.sha256"
    checksum_lines = checksum_path.read_text(encoding="utf-8").replace("readiness-profile.example.json", "readiness-profile.json")
    checksum_path.write_text(checksum_lines, encoding="utf-8")
    return evidence


def _seal(tmp_path: Path, evidence_kind: str = "contract-fixture", adapter: str | None = None, candidate: str | None = None) -> tuple[Path, dict]:
    evidence = _make_bundle(tmp_path, evidence_kind, adapter)
    output = tmp_path / "archive"
    manifest = seal_archive(evidence, output, "2026-08-10T05:00:00Z", candidate)
    return output, manifest


def test_seals_contract_fixture_without_promoting_execution(tmp_path: Path) -> None:
    output, manifest = _seal(tmp_path)
    assert manifest["status"] == "contract-sealed"
    assert manifest["handoff_status"] == "blocked-by-contract-fixture"
    assert manifest["execution_status"] == "not-run"
    assert manifest["go_no_go_status"] == "pending-evidence"
    assert (output / "staging-evidence-archive.zip").is_file()
    assert verify_archive(output / "staging-evidence-archive.zip", output / "staging-evidence-archive-manifest.json")["evidence_set_sha256"] == manifest["evidence_set_sha256"]


def test_target_execution_is_ready_for_approval_handoff(tmp_path: Path) -> None:
    _output, manifest = _seal(tmp_path, "target-execution", "prometheus-range-export-v1", "a" * 40)
    assert manifest["status"] == "evidence-sealed"
    assert manifest["handoff_status"] == "ready-for-approvals"
    assert manifest["execution_status"] == "evidence-valid"
    assert manifest["go_no_go_status"] == "pending-approvals"
    assert manifest["candidate_commit"] == "a" * 40


def test_rejects_candidate_commit_on_contract_fixture(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="contract-fixture archives"):
        _seal(tmp_path, candidate="a" * 40)


def test_rejects_target_execution_without_commit(tmp_path: Path) -> None:
    evidence = _make_bundle(tmp_path, "target-execution", "prometheus-range-export-v1")
    with pytest.raises(ValueError, match="require a 40- or 64-character"):
        seal_archive(evidence, tmp_path / "archive", "2026-08-10T05:00:00Z", None)


def test_rejects_target_execution_using_fixture_adapter(tmp_path: Path) -> None:
    evidence = _make_bundle(tmp_path, "target-execution", "prometheus-range-export-v1")
    for name in REPORT_NAMES:
        path = evidence / name
        report = json.loads(path.read_text(encoding="utf-8"))
        report["provenance"]["source_adapter"] = "prometheus-contract-fixture-v1"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksum_path = evidence / "checksums.sha256"
    lines = []
    for raw_line in checksum_path.read_text(encoding="utf-8").splitlines():
        digest, name = raw_line.split()
        if name in REPORT_NAMES:
            digest = __import__("hashlib").sha256((evidence / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot use fixture"):
        seal_archive(evidence, tmp_path / "archive", "2026-08-10T05:00:00Z", "a" * 40)


def test_rejects_mixed_execution_group(tmp_path: Path) -> None:
    evidence = _make_bundle(tmp_path)
    path = evidence / "redis-ha-failover-report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["provenance"]["execution_group_id"] = "other-group"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        seal_archive(evidence, tmp_path / "archive", "2026-08-10T05:00:00Z", None)


def test_rejects_source_checksum_mismatch(tmp_path: Path) -> None:
    evidence = _make_bundle(tmp_path)
    path = evidence / "source-checksums.sha256"
    path.write_text("0" * 64 + "  resource-source.json\n" + "1" * 64 + "  mysql-source.json\n" + "2" * 64 + "  redis-source.json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match report"):
        seal_archive(evidence, tmp_path / "archive", "2026-08-10T05:00:00Z", None)


def test_rejects_early_seal_time(tmp_path: Path) -> None:
    evidence = _make_bundle(tmp_path)
    with pytest.raises(ValueError, match="sealed_at"):
        seal_archive(evidence, tmp_path / "archive", "2026-08-10T03:59:59Z", None)


def test_archive_is_deterministic_for_same_evidence(tmp_path: Path) -> None:
    evidence = _make_bundle(tmp_path)
    first = tmp_path / "archive-one"
    second = tmp_path / "archive-two"
    seal_archive(evidence, first, "2026-08-10T05:00:00Z", None)
    seal_archive(evidence, second, "2026-08-10T05:00:00Z", None)
    assert (first / "staging-evidence-archive.zip").read_bytes() == (second / "staging-evidence-archive.zip").read_bytes()
    assert (first / "staging-evidence-archive.zip.sha256").read_text(encoding="utf-8") == (second / "staging-evidence-archive.zip.sha256").read_text(encoding="utf-8")


def test_detects_tampered_archive(tmp_path: Path) -> None:
    output, _ = _seal(tmp_path)
    archive_path = output / "staging-evidence-archive.zip"
    tampered_path = output / "tampered.zip"
    with zipfile.ZipFile(archive_path) as source, zipfile.ZipFile(tampered_path, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            if name == "resource-trend-report.json":
                data = data.replace(b'"sample_count": 961', b'"sample_count": 960')
            target.writestr(name, data)
    with pytest.raises(ValueError, match="archive checksum mismatch"):
        verify_archive(tampered_path, output / "staging-evidence-archive-manifest.json")
