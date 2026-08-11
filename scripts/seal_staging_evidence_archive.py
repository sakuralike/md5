from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from verify_staging_execution_evidence import (
    validate_ha_report,
    validate_resource_report,
)
from verify_staging_readiness_profile import validate_profile

ARCHIVE_SCHEMA = "staging-evidence-archive-manifest-v1"
REQUIRED_EVIDENCE_FILES = (
    "readiness-profile.json",
    "staging-readiness-plan.json",
    "resource-trend-report.json",
    "mysql-ha-failover-report.json",
    "redis-ha-failover-report.json",
    "staging-execution-evidence-summary.json",
    "checksums.sha256",
    "source-checksums.sha256",
)
REPORT_FILES = (
    "resource-trend-report.json",
    "mysql-ha-failover-report.json",
    "redis-ha-failover-report.json",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
FIXTURE_ADAPTER_RE = re.compile(r"(fixture|synthetic|test|mock)", re.IGNORECASE)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} root must be an object")
    return value


def _parse_timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return value


def _parse_manifest(path: Path, expected_names: set[str]) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2 or not SHA256_RE.fullmatch(parts[0]):
            raise ValueError(f"invalid checksum manifest line {line_number}: {raw_line}")
        digest, name = parts
        if Path(name).name != name or not SAFE_NAME_RE.fullmatch(name):
            raise ValueError(f"checksum manifest contains an unsafe filename: {name}")
        if name in entries:
            raise ValueError(f"checksum manifest contains duplicate filename: {name}")
        entries[name] = digest
    if set(entries) != expected_names:
        missing = sorted(expected_names - set(entries))
        extra = sorted(set(entries) - expected_names)
        raise ValueError(f"checksum manifest file set mismatch; missing={missing}, extra={extra}")
    return entries


def _validate_main_checksums(evidence_directory: Path) -> list[dict[str, Any]]:
    expected = set(REQUIRED_EVIDENCE_FILES[:-2])
    manifest_path = evidence_directory / "checksums.sha256"
    entries = _parse_manifest(manifest_path, expected)
    files: list[dict[str, Any]] = []
    for name in sorted(expected):
        path = evidence_directory / name
        if not path.is_file():
            raise FileNotFoundError(f"required evidence file is missing: {path}")
        digest = _sha256(path)
        if digest != entries[name]:
            raise ValueError(f"checksum mismatch for {name}")
        files.append({"path": name, "size_bytes": path.stat().st_size, "sha256": digest})
    return files


def _report_provenance(report: dict[str, Any], name: str) -> dict[str, Any]:
    value = report.get("provenance")
    if not isinstance(value, dict):
        raise TypeError(f"{name}.provenance must be an object")
    return value


def _validate_source_checksums(evidence_directory: Path, reports: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    path = evidence_directory / "source-checksums.sha256"
    lines = [line for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if len(lines) != 3:
        raise ValueError("source-checksums.sha256 must contain exactly three source files")
    sources: list[dict[str, str]] = []
    for line_number, raw_line in enumerate(lines, 1):
        parts = raw_line.split()
        if len(parts) != 2 or not SHA256_RE.fullmatch(parts[0]):
            raise ValueError(f"invalid source checksum line {line_number}")
        digest, name = parts
        if Path(name).name != name or not SAFE_NAME_RE.fullmatch(name):
            raise ValueError(f"source checksum contains an unsafe filename: {name}")
        if any(source["path"] == name for source in sources):
            raise ValueError(f"duplicate source checksum filename: {name}")
        sources.append({"path": name, "sha256": digest})
    report_digests = []
    for index, report in enumerate(reports):
        provenance = _report_provenance(report, f"report[{index}]")
        digest = _require_string(provenance.get("source_sha256"), "report.provenance.source_sha256")
        if not SHA256_RE.fullmatch(digest):
            raise ValueError("report.provenance.source_sha256 must be a lowercase SHA-256 digest")
        report_digests.append(digest)
    if sorted(source["sha256"] for source in sources) != sorted(report_digests):
        raise ValueError("source-checksums.sha256 does not match report source_sha256 values")
    return sources, [{"path": path.name, "size_bytes": path.stat().st_size, "sha256": _sha256(path)}]


def _validate_metadata(evidence_directory: Path) -> dict[str, Any]:
    summary = _load_object(evidence_directory / "staging-execution-evidence-summary.json")
    profile = _load_object(evidence_directory / "readiness-profile.json")
    plan = _load_object(evidence_directory / "staging-readiness-plan.json")
    reports = [_load_object(evidence_directory / name) for name in REPORT_FILES]
    validate_profile(profile, REPOSITORY_ROOT)
    profile_sha256 = _normalized_sha256(evidence_directory / "readiness-profile.json")
    validate_resource_report(reports[0], profile, profile_sha256)
    validate_ha_report(reports[1], profile, profile_sha256, "mysql")
    validate_ha_report(reports[2], profile, profile_sha256, "redis")
    expected_kind = _require_string(summary.get("evidence_kind"), "summary.evidence_kind")
    if expected_kind not in {"contract-fixture", "target-execution"}:
        raise ValueError("summary.evidence_kind must be contract-fixture or target-execution")
    if summary.get("schema") != "staging-execution-evidence-bundle-v1":
        raise ValueError("unexpected staging evidence summary schema")
    if summary.get("profile_sha256") != profile_sha256:
        raise ValueError("summary profile_sha256 does not match readiness-profile.json")
    expected_status = {
        "contract-fixture": ("contract-valid", "not-run", "pending-evidence"),
        "target-execution": ("evidence-valid", "evidence-valid", "go"),
    }[expected_kind]
    if tuple(summary.get(key) for key in ("status", "execution_status", "go_no_go_status")) != expected_status:
        raise ValueError("summary status boundary is inconsistent with evidence_kind")
    if plan.get("profile_sha256") != summary["profile_sha256"] or plan.get("status") != "contract-valid":
        raise ValueError("readiness plan is not bound to the evidence profile")
    if any(report.get("evidence_kind") != expected_kind for report in reports):
        raise ValueError("all evidence reports must match summary.evidence_kind")
    provenances = [_report_provenance(report, name) for name, report in zip(REPORT_FILES, reports)]
    if expected_kind == "target-execution":
        for provenance in provenances:
            adapter = _require_string(provenance.get("source_adapter"), "report.provenance.source_adapter")
            if FIXTURE_ADAPTER_RE.search(adapter):
                raise ValueError("target-execution archive cannot use fixture, synthetic, test or mock adapters")
    group_ids = {_require_string(provenance.get("execution_group_id"), "report.provenance.execution_group_id") for provenance in provenances}
    if len(group_ids) != 1:
        raise ValueError("all evidence reports must share one execution_group_id")
    execution_ids = [_require_string(provenance.get("execution_id"), "report.provenance.execution_id") for provenance in provenances]
    if len(set(execution_ids)) != len(execution_ids):
        raise ValueError("evidence report execution_id values must be unique")
    resource = reports[0]
    resource_start = _parse_timestamp(resource.get("started_at"), "resource.started_at")
    resource_finished = _parse_timestamp(resource.get("finished_at"), "resource.finished_at")
    for name, report in zip(REPORT_FILES[1:], reports[1:]):
        started = _parse_timestamp(report.get("started_at"), f"{name}.started_at")
        finished = _parse_timestamp(report.get("finished_at"), f"{name}.finished_at")
        if finished < started or finished < resource_start:
            raise ValueError(f"{name} interval is outside the execution group timeline")
    _validate_source_checksums(evidence_directory, reports)
    return {
        "evidence_kind": expected_kind,
        "execution_status": summary["execution_status"],
        "go_no_go_status": summary["go_no_go_status"],
        "profile_sha256": summary["profile_sha256"],
        "execution_group_id": group_ids.pop(),
        "execution_ids": execution_ids,
        "resource_started_at": resource_start.isoformat().replace("+00:00", "Z"),
        "resource_finished_at": resource_finished.isoformat().replace("+00:00", "Z"),
        "profile_schema": profile.get("schema"),
    }


def _build_manifest(evidence_directory: Path, sealed_at: str, candidate_commit: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    files = _validate_main_checksums(evidence_directory)
    metadata = _validate_metadata(evidence_directory)
    source_manifest = evidence_directory / "source-checksums.sha256"
    source_entries = _parse_manifest(source_manifest, {line.split()[-1] for line in source_manifest.read_text(encoding="utf-8-sig").splitlines() if line.strip()})
    source_files = [{"path": name, "sha256": digest} for name, digest in sorted(source_entries.items())]
    files.append({"path": "source-checksums.sha256", "size_bytes": source_manifest.stat().st_size, "sha256": _sha256(source_manifest)})
    sealed = _parse_timestamp(sealed_at, "sealed_at")
    finished = _parse_timestamp(metadata["resource_finished_at"], "resource_finished_at")
    if sealed < finished:
        raise ValueError("sealed_at must not precede the resource observation end")
    if metadata["evidence_kind"] == "target-execution":
        if not candidate_commit or not COMMIT_RE.fullmatch(candidate_commit):
            raise ValueError("target-execution archives require a 40- or 64-character lowercase commit SHA")
        handoff_status = "ready-for-release"
        archive_status = "evidence-sealed"
    else:
        if candidate_commit is not None:
            raise ValueError("contract-fixture archives must not carry a candidate commit")
        handoff_status = "blocked-by-contract-fixture"
        archive_status = "contract-sealed"
    manifest = {
        "schema": ARCHIVE_SCHEMA,
        "status": archive_status,
        "handoff_status": handoff_status,
        "evidence_kind": metadata["evidence_kind"],
        "execution_status": metadata["execution_status"],
        "go_no_go_status": metadata["go_no_go_status"],
        "execution_group_id": metadata["execution_group_id"],
        "execution_ids": metadata["execution_ids"],
        "profile_schema": metadata["profile_schema"],
        "profile_sha256": metadata["profile_sha256"],
        "resource_started_at": metadata["resource_started_at"],
        "resource_finished_at": metadata["resource_finished_at"],
        "sealed_at": sealed.isoformat().replace("+00:00", "Z"),
        "candidate_commit": candidate_commit,
        "source_files": source_files,
        "files": files,
    }
    manifest["evidence_set_sha256"] = _canonical_sha256({key: manifest[key] for key in ("execution_group_id", "profile_sha256", "source_files", "files")})
    return manifest, files


def _write_deterministic_zip(archive_path: Path, evidence_directory: Path, manifest_path: Path, files: list[dict[str, Any]]) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    names = [entry["path"] for entry in files] + [manifest_path.name]
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in names:
            source = manifest_path if name == manifest_path.name else evidence_directory / name
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes())


def verify_archive(archive_path: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = _load_object(manifest_path)
    if manifest.get("schema") != ARCHIVE_SCHEMA:
        raise ValueError("unexpected archive manifest schema")
    expected = {entry["path"]: entry["sha256"] for entry in manifest.get("files", [])}
    expected[manifest_path.name] = _sha256(manifest_path)
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ValueError("archive file set does not match the archive manifest")
        for name, digest in expected.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f"archive checksum mismatch for {name}")
        embedded = json.loads(archive.read(manifest_path.name).decode("utf-8"))
        if embedded != manifest:
            raise ValueError("embedded archive manifest differs from the external manifest")
    return manifest


def seal_archive(evidence_directory: Path, output_directory: Path, sealed_at: str, candidate_commit: str | None) -> dict[str, Any]:
    manifest, files = _build_manifest(evidence_directory, sealed_at, candidate_commit)
    output_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = output_directory / "staging-evidence-archive-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    archive_path = output_directory / "staging-evidence-archive.zip"
    _write_deterministic_zip(archive_path, evidence_directory, manifest_path, files)
    (output_directory / "staging-evidence-archive-manifest.sha256").write_text(
        f"{_sha256(manifest_path)}  {manifest_path.name}\n", encoding="utf-8"
    )
    (output_directory / "staging-evidence-archive.zip.sha256").write_text(
        f"{_sha256(archive_path)}  {archive_path.name}\n", encoding="utf-8"
    )
    verify_archive(archive_path, manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Seal and verify a WP4 staging evidence archive.")
    parser.add_argument("--evidence-directory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--sealed-at", required=True)
    parser.add_argument("--candidate-commit")
    args = parser.parse_args()
    try:
        manifest = seal_archive(args.evidence_directory, args.output_directory, args.sealed_at, args.candidate_commit)
    except (OSError, TypeError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
