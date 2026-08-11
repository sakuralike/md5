from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from verify_staging_api_ha import validate_staging_api_ha


def _copy_contract(tmp_path: Path) -> Path:
    report = validate_staging_api_ha(ROOT)
    for relative in report["files"]:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return tmp_path


def test_staging_api_ha_contract_passes() -> None:
    report = validate_staging_api_ha(ROOT)

    assert report["schema"] == "staging-api-ha-overlay-v1"
    assert report["api_replica_target"] == 2
    assert report["ingress_binding"] == "loopback-only"
    assert report["metrics_discovery"] == "compose-dns-a-records"


def test_rejects_api_host_port_publication(tmp_path: Path) -> None:
    repo = _copy_contract(tmp_path)
    compose = repo / "infra/staging/docker-compose.staging.api-ha.yml"
    text = compose.read_text(encoding="utf-8")
    compose.write_text(text.replace("ports: !reset []", 'ports: ["8000:8000"]'), encoding="utf-8")

    with pytest.raises(ValueError, match="reset the root host port"):
        validate_staging_api_ha(repo)


def test_rejects_public_proxy_binding(tmp_path: Path) -> None:
    repo = _copy_contract(tmp_path)
    compose = repo / "infra/staging/docker-compose.staging.api-ha.yml"
    text = compose.read_text(encoding="utf-8")
    compose.write_text(
        text.replace(
            '"127.0.0.1:${API_PORT:-8000}:8080"',
            '"${API_PORT:-8000}:8080"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="bind the single ingress port to loopback"):
        validate_staging_api_ha(repo)


def test_rejects_proxy_without_dynamic_replica_resolution(tmp_path: Path) -> None:
    repo = _copy_contract(tmp_path)
    nginx = repo / "infra/staging/nginx.api-ha.conf"
    text = nginx.read_text(encoding="utf-8")
    nginx.write_text(text.replace("server api:8000 resolve;", "server api:8000;"), encoding="utf-8")

    with pytest.raises(ValueError, match="server api:8000 resolve"):
        validate_staging_api_ha(repo)


def test_rejects_single_target_prometheus_config(tmp_path: Path) -> None:
    repo = _copy_contract(tmp_path)
    prometheus = repo / "infra/staging/prometheus.staging.yml"
    text = prometheus.read_text(encoding="utf-8")
    text = text.replace(
        "    dns_sd_configs:\n      - names:\n          - api\n        type: A\n        port: 8000\n",
        "    static_configs:\n      - targets:\n          - api:8000\n",
    )
    prometheus.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="discover every API replica"):
        validate_staging_api_ha(repo)
