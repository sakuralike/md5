from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REQUIRED_REPORTS = (
    "api-dependency-audit.json",
    "api-sbom.cdx.json",
    "bandit-report.json",
    "pnpm-audit.json",
)


class ArtifactValidationError(ValueError):
    """Raised when a security evidence artifact is missing or invalid."""


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise ArtifactValidationError(f"Missing security artifact: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError(f"Invalid JSON artifact {path}: {exc}") from exc


def _validate_api_audit(path: Path) -> None:
    report = _load_json(path)
    dependencies = report.get("dependencies") if isinstance(report, dict) else None
    if not isinstance(dependencies, list) or not dependencies:
        raise ArtifactValidationError("API dependency audit must contain dependencies")
    vulnerable = [
        dependency.get("name", "unknown")
        for dependency in dependencies
        if isinstance(dependency, dict) and dependency.get("vulns")
    ]
    if vulnerable:
        raise ArtifactValidationError(
            "API dependency audit contains vulnerabilities: " + ", ".join(vulnerable)
        )


def _validate_pnpm_audit(path: Path) -> None:
    report = _load_json(path)
    try:
        vulnerabilities = report["metadata"]["vulnerabilities"]
        high = int(vulnerabilities.get("high", 0))
        critical = int(vulnerabilities.get("critical", 0))
    except (KeyError, TypeError, ValueError) as exc:
        raise ArtifactValidationError("pnpm audit metadata is missing or invalid") from exc
    if high or critical:
        raise ArtifactValidationError(
            f"pnpm audit contains blocking vulnerabilities: high={high}, critical={critical}"
        )


def _validate_bandit(path: Path) -> None:
    report = _load_json(path)
    if not isinstance(report, dict):
        raise ArtifactValidationError("Bandit report must be a JSON object")
    errors = report.get("errors")
    if errors:
        raise ArtifactValidationError(f"Bandit reported scan errors: {errors}")
    results = report.get("results")
    if not isinstance(results, list):
        raise ArtifactValidationError("Bandit report results are missing")
    blocking = [
        result
        for result in results
        if isinstance(result, dict)
        and str(result.get("issue_severity", "")).upper() in {"MEDIUM", "HIGH"}
        and str(result.get("issue_confidence", "")).upper() in {"MEDIUM", "HIGH"}
    ]
    if blocking:
        test_ids = sorted({str(result.get("test_id", "unknown")) for result in blocking})
        raise ArtifactValidationError(
            "Bandit report contains blocking findings: " + ", ".join(test_ids)
        )


def _validate_cyclonedx(path: Path) -> None:
    report = _load_json(path)
    if not isinstance(report, dict) or report.get("bomFormat") != "CycloneDX":
        raise ArtifactValidationError(f"Artifact is not a CycloneDX BOM: {path}")
    if not report.get("specVersion"):
        raise ArtifactValidationError(f"CycloneDX specVersion is missing: {path}")
    components = report.get("components")
    if not isinstance(components, list) or not components:
        raise ArtifactValidationError(f"CycloneDX BOM contains no components: {path}")


def verify_artifacts(directory: Path, require_repository_sbom: bool = False) -> list[Path]:
    directory = directory.resolve()
    paths = [directory / name for name in REQUIRED_REPORTS]
    _validate_api_audit(directory / "api-dependency-audit.json")
    _validate_cyclonedx(directory / "api-sbom.cdx.json")
    _validate_bandit(directory / "bandit-report.json")
    _validate_pnpm_audit(directory / "pnpm-audit.json")
    if require_repository_sbom:
        repository_sbom = directory / "repository-sbom.cdx.json"
        _validate_cyclonedx(repository_sbom)
        paths.append(repository_sbom)
    return paths


def write_checksums(directory: Path, paths: list[Path]) -> Path:
    manifest = directory.resolve() / "SHA256SUMS"
    lines = []
    for path in sorted(paths, key=lambda item: item.name):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate WP4 security evidence artifacts.")
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--require-repository-sbom", action="store_true")
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    try:
        paths = verify_artifacts(args.directory, args.require_repository_sbom)
        if args.write_checksums:
            write_checksums(args.directory, paths)
    except ArtifactValidationError as exc:
        print(f"Security artifact validation failed: {exc}")
        return 1
    print(f"Validated {len(paths)} security artifacts in {args.directory.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
