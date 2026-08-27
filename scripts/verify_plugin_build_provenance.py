from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


def _read_package(path: Path) -> tuple[dict, dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(
            not name or name.startswith("/") or ".." in Path(name).parts for name in names
        ):
            raise ValueError(f"invalid package paths: {path}")
        provenance = json.loads(archive.read("provenance.json"))
        files = {
            name: hashlib.sha256(archive.read(name)).hexdigest()
            for name in names
            if name != "signature.ed25519"
        }
    return provenance, files


def _git_head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip().lower()


def _tool_version(command: list[str]) -> str:
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()


def _recorded_files(provenance: dict, files: dict[str, str]) -> dict[str, str]:
    records = []
    records.extend(provenance.get("source_files", []))
    records.append(provenance.get("sbom", {}))
    records.extend(provenance.get("binaries", []))
    recorded = {
        record["path"]: record["sha256"]
        for record in records
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    }
    return {path: files[path] for path in recorded if path in files} | {
        path: digest for path, digest in recorded.items() if path not in files
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--rebuild", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    head = _git_head(args.repository_root)
    first_provenance, first_files = _read_package(args.package)
    second_provenance, second_files = _read_package(args.rebuild)
    for label, provenance, files in (
        ("package", first_provenance, first_files),
        ("rebuild", second_provenance, second_files),
    ):
        if provenance.get("schema") != "pd.plugin.provenance/v1":
            raise ValueError(f"{label} provenance schema is invalid")
        if provenance.get("source_commit") != head:
            raise ValueError(
                f"{label} provenance source_commit does not match Git HEAD: "
                f"{provenance.get('source_commit')} != {head}"
            )
        if not provenance.get("source_files"):
            raise ValueError(f"{label} provenance has no source files")
        expected_files = {
            path: digest
            for path, digest in files.items()
            if path.startswith(("source/", "bin/"))
            or path == "sbom.cdx.json"
        }
        if _recorded_files(provenance, expected_files) != expected_files:
            raise ValueError(f"{label} provenance file records do not match archive contents")

    if first_provenance != second_provenance or first_files != second_files:
        raise ValueError("rebuild provenance or content digests differ")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "pd.plugin.build-proof/v1",
        "git_commit": head,
        "package_sha256": hashlib.sha256(args.package.read_bytes()).hexdigest(),
        "rebuild_sha256": hashlib.sha256(args.rebuild.read_bytes()).hexdigest(),
        "content_reproducible": True,
        "provenance": first_provenance,
        "toolchain": {
            "dotnet": _tool_version(["dotnet", "--version"]),
            "python": _tool_version(["python", "--version"]),
        },
    }
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    checksum = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_name("SHA256SUMS").write_text(
        f"{checksum}  {args.output.name}\n"
        f"{evidence['package_sha256']}  {args.package.name}\n"
        f"{evidence['rebuild_sha256']}  {args.rebuild.name}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
