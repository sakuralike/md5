from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from verify_release_security import (
    ReleaseSecurityValidationError,
    verify_release_security,
    write_checksums,
    write_summary,
)


class ReleaseSecurityVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        self.policy = self.root / "risk-acceptances.json"
        self.today = date(2026, 8, 9)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_json(self, path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")

    def write_empty_policy(self) -> None:
        self.write_json(self.policy, {"schema_version": 1, "acceptances": []})

    def write_reports(
        self,
        *,
        vulnerabilities: list[dict[str, object]] | None = None,
        secrets: list[dict[str, object]] | None = None,
    ) -> None:
        image_results = []
        if vulnerabilities is not None:
            image_results = [
                {"Target": "python:3.12-slim", "Vulnerabilities": vulnerabilities}
            ]
        for filename, artifact in (
            ("trivy-api-image.json", "password-detective-api:test"),
            ("trivy-web-image.json", "password-detective-web:test"),
            ("trivy-admin-image.json", "password-detective-admin:test"),
        ):
            self.write_json(
                self.evidence / filename,
                {
                    "SchemaVersion": 2,
                    "ArtifactName": artifact,
                    "ArtifactType": "container_image",
                    "Results": image_results if filename == "trivy-api-image.json" else [],
                },
            )
        secret_results = []
        if secrets is not None:
            secret_results = [{"Target": "config/example.txt", "Secrets": secrets}]
        self.write_json(
            self.evidence / "trivy-repository-secrets.json",
            {
                "SchemaVersion": 2,
                "ArtifactName": ".",
                "ArtifactType": "filesystem",
                "Results": secret_results,
            },
        )

    def test_clean_reports_pass_and_write_deterministic_manifest(self) -> None:
        self.write_empty_policy()
        self.write_reports()

        summary, paths = verify_release_security(
            self.evidence, self.policy, self.today
        )
        summary_path = write_summary(self.evidence, summary)
        manifest = write_checksums(self.evidence, [*paths, summary_path])

        self.assertEqual(summary["blocking_count"], 0)
        self.assertEqual(summary["finding_count"], 0)
        manifest_names = [line.split("  ", 1)[1] for line in manifest.read_text().splitlines()]
        self.assertEqual(manifest_names, sorted(manifest_names))

    def test_unaccepted_high_vulnerability_is_blocking(self) -> None:
        self.write_empty_policy()
        self.write_reports(
            vulnerabilities=[
                {
                    "VulnerabilityID": "CVE-2099-0001",
                    "Severity": "HIGH",
                    "Title": "Synthetic vulnerable package",
                }
            ]
        )

        with self.assertRaisesRegex(
            ReleaseSecurityValidationError, "CVE-2099-0001"
        ):
            verify_release_security(self.evidence, self.policy, self.today)

    def test_valid_dual_control_acceptance_allows_exact_finding(self) -> None:
        self.write_json(
            self.policy,
            {
                "schema_version": 1,
                "acceptances": [
                    {
                        "id": "RA-2026-001",
                        "scope": "image:api",
                        "finding_id": "CVE-2099-0001",
                        "severity": "HIGH",
                        "owner": "security-owner@example.invalid",
                        "approved_by": "release-approver@example.invalid",
                        "reason": "Synthetic fixture awaiting upstream rebuild.",
                        "ticket": "SEC-TEST-001",
                        "expires_on": "2026-08-31",
                    }
                ],
            },
        )
        self.write_reports(
            vulnerabilities=[
                {
                    "VulnerabilityID": "CVE-2099-0001",
                    "Severity": "HIGH",
                    "Title": "Synthetic vulnerable package",
                }
            ]
        )

        summary, _ = verify_release_security(self.evidence, self.policy, self.today)

        self.assertEqual(summary["accepted_count"], 1)
        self.assertEqual(summary["blocking_count"], 0)

    def test_expired_acceptance_fails_even_without_reports(self) -> None:
        self.write_json(
            self.policy,
            {
                "schema_version": 1,
                "acceptances": [
                    {
                        "id": "RA-2026-002",
                        "scope": "repo:secrets",
                        "finding_id": "synthetic-secret@config/example.txt:1",
                        "severity": "CRITICAL",
                        "owner": "security-owner@example.invalid",
                        "approved_by": "release-approver@example.invalid",
                        "reason": "Synthetic expired acceptance.",
                        "ticket": "SEC-TEST-002",
                        "expires_on": "2026-08-09",
                    }
                ],
            },
        )

        with self.assertRaisesRegex(ReleaseSecurityValidationError, "expired"):
            verify_release_security(
                self.evidence, self.policy, self.today, policy_only=True
            )

    def test_acceptance_requires_independent_approver(self) -> None:
        self.write_json(
            self.policy,
            {
                "schema_version": 1,
                "acceptances": [
                    {
                        "id": "RA-2026-003",
                        "scope": "image:web",
                        "finding_id": "CVE-2099-0002",
                        "severity": "CRITICAL",
                        "owner": "same-owner@example.invalid",
                        "approved_by": "same-owner@example.invalid",
                        "reason": "Synthetic invalid approval.",
                        "ticket": "SEC-TEST-003",
                        "expires_on": "2026-08-31",
                    }
                ],
            },
        )

        with self.assertRaisesRegex(
            ReleaseSecurityValidationError, "independent approval"
        ):
            verify_release_security(
                self.evidence, self.policy, self.today, policy_only=True
            )


if __name__ == "__main__":
    unittest.main()
