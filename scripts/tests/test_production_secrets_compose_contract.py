from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
OVERRIDE = (ROOT / "docker-compose.production-secrets.yml").read_text(encoding="utf-8")


def test_base_compose_exposes_file_setting_hooks_for_all_app_processes() -> None:
    lines = BASE.splitlines()
    assert sum(line.strip().startswith("APP_SECRET_KEY_FILE:") for line in lines) == 3
    assert sum(line.strip().startswith("DATABASE_URL_FILE:") for line in lines) == 3
    assert sum(line.strip().startswith("REDIS_URL_FILE:") for line in lines) == 3
    assert sum(line.strip().startswith("CANDIDATE_SECRET_KEYRING_FILE:") for line in lines) == 3
    assert sum(line.strip().startswith("CANDIDATE_SECRET_DEDUP_KEY_FILE:") for line in lines) == 3


def test_production_override_clears_direct_secrets_and_mounts_file_secrets() -> None:
    for direct_name in (
        "APP_SECRET_KEY",
        "DATABASE_URL",
        "REDIS_URL",
        "CANDIDATE_SECRET_KEY_VERSION",
        "CANDIDATE_SECRET_KEYRING",
        "CANDIDATE_SECRET_DEDUP_KEY",
        "NOTIFICATION_WEBHOOK_SECRET",
        "NOTIFICATION_SMTP_PASSWORD",
    ):
        assert f'{direct_name}: ""' in OVERRIDE
        assert f"{direct_name}_FILE: /run/secrets/{direct_name.lower()}" in OVERRIDE
    assert "MYSQL_PASSWORD_FILE: /run/secrets/mysql_password" in OVERRIDE
    assert "MYSQL_ROOT_PASSWORD_FILE: /run/secrets/mysql_root_password" in OVERRIDE
    assert "PASSWORD_DETECTIVE_SECRET_DIR" in OVERRIDE


def test_redis_password_is_materialized_to_private_runtime_config() -> None:
    assert "umask 077" in OVERRIDE
    assert "/run/secrets/redis_password" in OVERRIDE
    assert "requirepass %s" in OVERRIDE
    assert "REDISCLI_AUTH=" in OVERRIDE


def test_api_image_copies_root_only_secret_mounts_then_drops_privileges() -> None:
    dockerfile = (ROOT / "infra/docker/api.Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "infra/docker/api-entrypoint.sh").read_text(encoding="utf-8")
    assert "su-exec" in dockerfile
    assert 'ENTRYPOINT ["password-detective-api-entrypoint"]' in dockerfile
    assert "sed -i 's/\\r$//' /usr/local/bin/password-detective-api-entrypoint" in dockerfile
    assert "RUNTIME_SECRET_DIR=/run/password-detective-secrets" in entrypoint
    assert 'chmod 0400 "$destination"' in entrypoint
    assert 'exec su-exec app "$@"' in entrypoint
    assert "/run/password-detective-secrets:mode=0700" in OVERRIDE
