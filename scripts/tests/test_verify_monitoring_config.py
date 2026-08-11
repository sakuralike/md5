from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from verify_monitoring_config import validate_monitoring_files


def _copy_monitoring_contract(tmp_path: Path) -> Path:
    report = validate_monitoring_files(ROOT)
    for relative in report["files"]:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return tmp_path


def test_monitoring_contract_includes_staging_overlay() -> None:
    report = validate_monitoring_files(ROOT)

    assert report["schema"] == "monitoring-config-v3"
    assert "infra/staging/prometheus.staging.yml" in report["files"]
    assert "infra/staging/docker-compose.staging.monitoring.yml" in report["files"]


def test_monitoring_contract_rejects_public_prometheus_binding(tmp_path: Path) -> None:
    repo = _copy_monitoring_contract(tmp_path)
    compose = repo / "infra/monitoring/docker-compose.monitoring.yml"
    text = compose.read_text(encoding="utf-8")
    text = text.replace(
        '"127.0.0.1:${PROMETHEUS_PORT:-9090}:9090"',
        '"${PROMETHEUS_PORT:-9090}:9090"',
    )
    compose.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="9090 must bind to loopback"):
        validate_monitoring_files(repo)


def test_monitoring_contract_rejects_staging_label_drift(tmp_path: Path) -> None:
    repo = _copy_monitoring_contract(tmp_path)
    prometheus = repo / "infra/staging/prometheus.staging.yml"
    text = prometheus.read_text(encoding="utf-8")
    prometheus.write_text(
        text.replace("environment: staging", "environment: integration"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="staging environment label"):
        validate_monitoring_files(repo)
