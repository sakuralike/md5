from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

IMAGE_REPORTS = {
    "image:api": "trivy-api-image.json",
    "image:web": "trivy-web-image.json",
    "image:admin": "trivy-admin-image.json",
}
SECRET_SCOPE = "repo:secrets"
SECRET_REPORT = "trivy-repository-secrets.json"
ALLOWED_SCOPES = frozenset((*IMAGE_REPORTS, SECRET_SCOPE))
BLOCKING_SEVERITIES = frozenset({"HIGH", "CRITICAL"})
ACCEPTANCE_ID_PATTERN = re.compile(r"^RA-\d{4}-\d{3,}$")


class ReleaseSecurityValidationError(ValueError):
    """Raised when release security evidence or policy is invalid."""


@dataclass(frozen=True)
class Finding:
    scope: str
    finding_id: str
    severity: str
    target: str
    title: str

    @property
    def key(self) -> tuple[str, str]:
        return self.scope, self.finding_id

    def as_dict(self) -> dict[str, str]:
        return {
            "scope": self.scope,
            "finding_id": self.finding_id,
            "severity": self.severity,
            "target": self.target,
            "title": self.title,
        }


@dataclass(frozen=True)
class Acceptance:
    acceptance_id: str
    scope: str
    finding_id: str
    severity: str
    owner: str
    approved_by: str
    reason: str
    ticket: str
    expires_on: date

    @property
    def key(self) -> tuple[str, str]:
        return self.scope, self.finding_id

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.acceptance_id,
            "scope": self.scope,
            "finding_id": self.finding_id,
            "severity": self.severity,
            "owner": self.owner,
            "approved_by": self.approved_by,
            "reason": self.reason,
            "ticket": self.ticket,
            "expires_on": self.expires_on.isoformat(),
        }


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise ReleaseSecurityValidationError(f"Missing release security artifact: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseSecurityValidationError(f"Invalid JSON artifact {path}: {exc}") from exc


def _required_text(record: dict[str, Any], field: str, acceptance_id: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ReleaseSecurityValidationError(
            f"Risk acceptance {acceptance_id} requires a non-empty {field}"
        )
    return value.strip()


def load_acceptances(path: Path, today: date) -> dict[tuple[str, str], Acceptance]:
    policy = _load_json(path)
    if not isinstance(policy, dict) or policy.get("schema_version") != 1:
        raise ReleaseSecurityValidationError("Risk acceptance schema_version must be 1")
    records = policy.get("acceptances")
    if not isinstance(records, list):
        raise ReleaseSecurityValidationError("Risk acceptances must be a JSON array")

    acceptances: dict[tuple[str, str], Acceptance] = {}
    acceptance_ids: set[str] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ReleaseSecurityValidationError(
                f"Risk acceptance at index {index} must be an object"
            )
        acceptance_id = _required_text(record, "id", f"index-{index}")
        if not ACCEPTANCE_ID_PATTERN.fullmatch(acceptance_id):
            raise ReleaseSecurityValidationError(
                f"Risk acceptance id must match RA-YYYY-NNN: {acceptance_id}"
            )
        if acceptance_id in acceptance_ids:
            raise ReleaseSecurityValidationError(
                f"Duplicate risk acceptance id: {acceptance_id}"
            )
        acceptance_ids.add(acceptance_id)

        scope = _required_text(record, "scope", acceptance_id)
        if scope not in ALLOWED_SCOPES:
            raise ReleaseSecurityValidationError(
                f"Risk acceptance {acceptance_id} has unsupported scope: {scope}"
            )
        finding_id = _required_text(record, "finding_id", acceptance_id)
        severity = _required_text(record, "severity", acceptance_id).upper()
        if severity not in BLOCKING_SEVERITIES:
            raise ReleaseSecurityValidationError(
                f"Risk acceptance {acceptance_id} severity must be HIGH or CRITICAL"
            )
        owner = _required_text(record, "owner", acceptance_id)
        approved_by = _required_text(record, "approved_by", acceptance_id)
        if owner.casefold() == approved_by.casefold():
            raise ReleaseSecurityValidationError(
                f"Risk acceptance {acceptance_id} requires independent approval"
            )
        reason = _required_text(record, "reason", acceptance_id)
        ticket = _required_text(record, "ticket", acceptance_id)
        expires_text = _required_text(record, "expires_on", acceptance_id)
        try:
            expires_on = date.fromisoformat(expires_text)
        except ValueError as exc:
            raise ReleaseSecurityValidationError(
                f"Risk acceptance {acceptance_id} expires_on must use YYYY-MM-DD"
            ) from exc
        if expires_on <= today:
            raise ReleaseSecurityValidationError(
                f"Risk acceptance {acceptance_id} expired on {expires_on.isoformat()}"
            )

        acceptance = Acceptance(
            acceptance_id=acceptance_id,
            scope=scope,
            finding_id=finding_id,
            severity=severity,
            owner=owner,
            approved_by=approved_by,
            reason=reason,
            ticket=ticket,
            expires_on=expires_on,
        )
        if acceptance.key in acceptances:
            raise ReleaseSecurityValidationError(
                f"Duplicate risk acceptance target: {scope}/{finding_id}"
            )
        acceptances[acceptance.key] = acceptance
    return acceptances


def _validate_trivy_report(path: Path) -> dict[str, Any]:
    report = _load_json(path)
    if not isinstance(report, dict) or report.get("SchemaVersion") != 2:
        raise ReleaseSecurityValidationError(f"Artifact is not a Trivy JSON report: {path}")
    results = report.get("Results")
    if results is not None and not isinstance(results, list):
        raise ReleaseSecurityValidationError(f"Trivy Results must be an array: {path}")
    return report


def _image_findings(scope: str, path: Path) -> list[Finding]:
    report = _validate_trivy_report(path)
    findings: list[Finding] = []
    for result in report.get("Results") or []:
        if not isinstance(result, dict):
            continue
        target = str(result.get("Target") or report.get("ArtifactName") or "unknown")
        for vulnerability in result.get("Vulnerabilities") or []:
            if not isinstance(vulnerability, dict):
                continue
            severity = str(vulnerability.get("Severity") or "UNKNOWN").upper()
            if severity not in BLOCKING_SEVERITIES:
                continue
            finding_id = str(vulnerability.get("VulnerabilityID") or "").strip()
            if not finding_id:
                raise ReleaseSecurityValidationError(
                    f"Trivy vulnerability is missing VulnerabilityID: {path}"
                )
            findings.append(
                Finding(
                    scope=scope,
                    finding_id=finding_id,
                    severity=severity,
                    target=target,
                    title=str(vulnerability.get("Title") or finding_id),
                )
            )
    return findings


def _secret_findings(path: Path) -> list[Finding]:
    report = _validate_trivy_report(path)
    findings: list[Finding] = []
    for result in report.get("Results") or []:
        if not isinstance(result, dict):
            continue
        target = str(result.get("Target") or "unknown")
        for secret in result.get("Secrets") or []:
            if not isinstance(secret, dict):
                continue
            severity = str(secret.get("Severity") or "CRITICAL").upper()
            if severity not in BLOCKING_SEVERITIES:
                continue
            rule_id = str(secret.get("RuleID") or "unknown-secret").strip()
            start_line = secret.get("StartLine")
            location = f"{target}:{start_line}" if start_line is not None else target
            findings.append(
                Finding(
                    scope=SECRET_SCOPE,
                    finding_id=f"{rule_id}@{location}",
                    severity=severity,
                    target=target,
                    title=str(secret.get("Title") or rule_id),
                )
            )
    return findings


def verify_release_security(
    directory: Path,
    risk_acceptances_path: Path,
    today: date,
    policy_only: bool = False,
) -> tuple[dict[str, Any], list[Path]]:
    directory = directory.resolve()
    acceptance_path = risk_acceptances_path.resolve()
    acceptances = load_acceptances(acceptance_path, today)
    evidence_paths = [acceptance_path]
    findings: list[Finding] = []

    if not policy_only:
        for scope, filename in IMAGE_REPORTS.items():
            report_path = directory / filename
            findings.extend(_image_findings(scope, report_path))
            evidence_paths.append(report_path)
        secret_path = directory / SECRET_REPORT
        findings.extend(_secret_findings(secret_path))
        evidence_paths.append(secret_path)

    accepted: list[dict[str, Any]] = []
    blocking: list[dict[str, str]] = []
    used_acceptances: set[tuple[str, str]] = set()
    for finding in findings:
        acceptance = acceptances.get(finding.key)
        if acceptance is None or acceptance.severity != finding.severity:
            blocking.append(finding.as_dict())
            continue
        used_acceptances.add(acceptance.key)
        accepted.append(
            {"finding": finding.as_dict(), "acceptance": acceptance.as_dict()}
        )

    unused = [
        acceptance.as_dict()
        for key, acceptance in sorted(acceptances.items())
        if key not in used_acceptances
    ]
    summary = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "policy_only": policy_only,
        "risk_acceptance_count": len(acceptances),
        "finding_count": len(findings),
        "accepted_count": len(accepted),
        "blocking_count": len(blocking),
        "accepted_findings": accepted,
        "blocking_findings": blocking,
        "unused_acceptances": unused,
    }
    if blocking:
        rendered = ", ".join(
            f"{item['scope']}/{item['finding_id']}({item['severity']})"
            for item in blocking
        )
        raise ReleaseSecurityValidationError(
            "Unaccepted release security findings: " + rendered
        )
    return summary, evidence_paths


def write_summary(directory: Path, summary: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "release-security-summary.json"
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def write_checksums(directory: Path, paths: list[Path]) -> Path:
    manifest = directory.resolve() / "RELEASE_SHA256SUMS"
    unique_paths = {path.resolve() for path in paths}
    lines = []
    for path in sorted(unique_paths, key=lambda item: item.name):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate WP4 image, secret, and risk acceptance evidence."
    )
    parser.add_argument("--directory", type=Path, default=Path(".local/security-release"))
    parser.add_argument(
        "--risk-acceptances",
        type=Path,
        default=Path("security/risk-acceptances.json"),
    )
    parser.add_argument("--today", type=date.fromisoformat, default=datetime.now(UTC).date())
    parser.add_argument("--policy-only", action="store_true")
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    try:
        summary, evidence_paths = verify_release_security(
            args.directory,
            args.risk_acceptances,
            args.today,
            args.policy_only,
        )
        summary_path = write_summary(args.directory, summary)
        evidence_paths.append(summary_path)
        if args.write_checksums:
            write_checksums(args.directory, evidence_paths)
    except ReleaseSecurityValidationError as exc:
        print(f"Release security validation failed: {exc}")
        return 1
    print(
        "Release security gate passed: "
        f"findings={summary['finding_count']}, accepted={summary['accepted_count']}, "
        f"evidence={args.directory.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
