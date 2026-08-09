from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from verify_security_artifacts import (
    ArtifactValidationError,
    verify_artifacts,
    write_checksums,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


class VerifySecurityArtifactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        write_json(
            self.directory / "api-dependency-audit.json",
            {"dependencies": [{"name": "fastapi", "version": "1.0", "vulns": []}]},
        )
        cyclonedx = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "components": [{"type": "library", "name": "synthetic-component"}],
        }
        write_json(self.directory / "api-sbom.cdx.json", cyclonedx)
        write_json(self.directory / "repository-sbom.cdx.json", cyclonedx)
        write_json(self.directory / "bandit-report.json", {"errors": [], "results": []})
        write_json(
            self.directory / "pnpm-audit.json",
            {"metadata": {"vulnerabilities": {"high": 0, "critical": 0}}},
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_accepts_complete_evidence_and_writes_sorted_checksums(self) -> None:
        paths = verify_artifacts(self.directory, require_repository_sbom=True)
        manifest = write_checksums(self.directory, paths)
        lines = manifest.read_text(encoding="utf-8").splitlines()
        self.assertEqual(5, len(lines))
        self.assertEqual(sorted(line.split("  ", 1)[1] for line in lines), [
            "api-dependency-audit.json",
            "api-sbom.cdx.json",
            "bandit-report.json",
            "pnpm-audit.json",
            "repository-sbom.cdx.json",
        ])

    def test_rejects_vulnerable_api_dependency(self) -> None:
        write_json(
            self.directory / "api-dependency-audit.json",
            {"dependencies": [{"name": "unsafe", "vulns": [{"id": "SYNTH-1"}]}]},
        )
        with self.assertRaises(ArtifactValidationError):
            verify_artifacts(self.directory)

    def test_rejects_high_node_vulnerability(self) -> None:
        write_json(
            self.directory / "pnpm-audit.json",
            {"metadata": {"vulnerabilities": {"high": 1, "critical": 0}}},
        )
        with self.assertRaises(ArtifactValidationError):
            verify_artifacts(self.directory)

    def test_rejects_non_cyclonedx_sbom(self) -> None:
        write_json(self.directory / "api-sbom.cdx.json", {"components": []})
        with self.assertRaises(ArtifactValidationError):
            verify_artifacts(self.directory)


if __name__ == "__main__":
    unittest.main()
