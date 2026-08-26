from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
PLUGIN_PATH = "/var/lib/password-detective/desktop-plugins"
PLUGIN_VOLUME = f"desktop-plugin-data:{PLUGIN_PATH}"


def test_plugin_storage_is_shared_by_runtime_services() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    for service_name in ("api", "worker", "scheduler"):
        service = compose["services"][service_name]
        assert service["environment"]["DESKTOP_PLUGIN_STORAGE_PATH"] == PLUGIN_PATH
    assert PLUGIN_VOLUME in compose["services"]["api"]["volumes"]
    assert PLUGIN_VOLUME in compose["services"]["worker"]["volumes"]
    assert "desktop-plugin-data" in compose["volumes"]


def test_plugin_storage_volume_is_writable_after_container_start() -> None:
    dockerfile = (ROOT / "infra/docker/api.Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "infra/docker/api-entrypoint.sh").read_text(encoding="utf-8")
    staging = (ROOT / "infra/staging/docker-compose.staging.api-ha.yml").read_text(
        encoding="utf-8"
    )

    assert PLUGIN_PATH in dockerfile
    assert PLUGIN_PATH in entrypoint
    assert "prepare_runtime_data_directories" in entrypoint
    assert "chown app:app" in entrypoint
    assert staging.count(PLUGIN_VOLUME) == 3


def test_staging_plugin_storage_uses_private_minio_backend() -> None:
    staging = (ROOT / "infra/staging/docker-compose.staging.api-ha.yml").read_text(
        encoding="utf-8"
    )

    assert "DESKTOP_PLUGIN_STORAGE_BACKEND: s3" in staging
    assert "http://plugin-object-storage:9000" in staging
    assert "plugin-object-storage:" in staging
    assert "desktop-plugin-object-data" in staging
    assert "minio/health/live" in staging
    assert 'ports: !reset []' in staging
