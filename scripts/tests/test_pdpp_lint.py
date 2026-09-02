import json
import subprocess
import sys
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "pdpp-lint.py"


def test_pdpp_lint_rejects_missing_required_files(tmp_path: Path) -> None:
    package = tmp_path / "invalid.pdpkg"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"schema": "pd.plugin/v1"}))

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(package)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert any(item["rule_id"] == "PD-PKG-005" for item in payload["findings"])
