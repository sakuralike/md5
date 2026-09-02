from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import sys
import zipfile
from pathlib import Path

MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
REQUIRED_FILES = {"manifest.json", "signature.ed25519", "provenance.json", "sbom.cdx.json"}


def lint(package: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not package.is_file():
        return [{"rule_id": "PD-PKG-001", "severity": "error", "message": "package does not exist"}]
    if package.stat().st_size > MAX_PACKAGE_BYTES:
        findings.append({"rule_id": "PD-PKG-002", "severity": "error", "message": "package exceeds 512 MiB"})
    try:
        with zipfile.ZipFile(package) as archive:
            names = archive.namelist()
            normalized: set[str] = set()
            for name in names:
                clean = name.replace("\\", "/")
                if clean.startswith("/") or ".." in posixpath.normpath(clean).split("/"):
                    findings.append({"rule_id": "PD-PKG-003", "severity": "error", "message": f"path traversal: {name}"})
                key = clean.casefold()
                if key in normalized:
                    findings.append({"rule_id": "PD-PKG-004", "severity": "error", "message": f"duplicate path: {name}"})
                normalized.add(key)
            missing = sorted(REQUIRED_FILES.difference(names))
            for name in missing:
                findings.append({"rule_id": "PD-PKG-005", "severity": "error", "message": f"missing required file: {name}"})
            if "manifest.json" in names:
                raw = archive.read("manifest.json")
                if len(raw) > MAX_MANIFEST_BYTES:
                    findings.append({"rule_id": "PD-MAN-001", "severity": "error", "message": "manifest exceeds 128 KiB"})
                else:
                    try:
                        manifest = json.loads(raw)
                    except json.JSONDecodeError:
                        findings.append({"rule_id": "PD-MAN-002", "severity": "error", "message": "manifest is not valid JSON"})
                    else:
                        for field in ("schema", "plugin_id", "version", "runtime", "commands", "capabilities", "limits"):
                            if field not in manifest:
                                findings.append({"rule_id": "PD-MAN-003", "severity": "error", "message": f"manifest missing {field}"})
                        if manifest.get("schema") != "pd.plugin/v1":
                            findings.append({"rule_id": "PD-MAN-004", "severity": "error", "message": "unsupported manifest schema"})
            if "provenance.json" in names:
                try:
                    provenance = json.loads(archive.read("provenance.json"))
                    if provenance.get("schema") != "pd.plugin.provenance/v1":
                        findings.append({"rule_id": "PD-PROV-001", "severity": "error", "message": "unsupported provenance schema"})
                except json.JSONDecodeError:
                    findings.append({"rule_id": "PD-PROV-002", "severity": "error", "message": "provenance is not valid JSON"})
    except (zipfile.BadZipFile, OSError) as exc:
        findings.append({"rule_id": "PD-PKG-006", "severity": "error", "message": f"invalid package: {exc}"})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Password Detective .pdpkg package.")
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    findings = lint(args.package)
    output = {
        "tool": "pdpp-lint",
        "version": "1",
        "package_sha256": hashlib.sha256(args.package.read_bytes()).hexdigest() if args.package.is_file() else None,
        "findings": findings,
        "status": "failed" if findings else "passed",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
