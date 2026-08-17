from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESOLVER = ROOT / "scripts" / "lib" / "Resolve-ApiVenvPython.ps1"


def invoke_resolver(api_path: Path) -> subprocess.CompletedProcess[str]:
    command = (
        f". '{RESOLVER}'; "
        f"$resolved = Resolve-ApiVenvPython -ApiPath '{api_path}'; "
        "if ($null -eq $resolved) { exit 4 }; "
        "Write-Output $resolved"
    )
    return subprocess.run(
        ["pwsh", "-NoProfile", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
    )


def test_resolver_prefers_windows_venv_python(tmp_path: Path) -> None:
    api_path = tmp_path / "api"
    windows_python = api_path / ".venv" / "Scripts" / "python.exe"
    posix_python = api_path / ".venv" / "bin" / "python.exe"
    windows_python.parent.mkdir(parents=True)
    posix_python.parent.mkdir(parents=True)
    windows_python.touch()
    posix_python.touch()

    result = invoke_resolver(api_path)

    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == windows_python


def test_resolver_accepts_msys_style_venv_python(tmp_path: Path) -> None:
    api_path = tmp_path / "api"
    posix_python = api_path / ".venv" / "bin" / "python.exe"
    posix_python.parent.mkdir(parents=True)
    posix_python.touch()

    result = invoke_resolver(api_path)

    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == posix_python