from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


class _ComposeLoaderMixin:
    @staticmethod
    def reset_constructor(loader: Any, node: Any) -> Any:
        if getattr(node, "value", None) == []:
            return []
        return loader.construct_object(node)


def _load_yaml(path: Path, *, compose: bool = False) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment setup failure
        raise RuntimeError("PyYAML is required for Staging API HA validation") from exc

    loader = yaml.SafeLoader
    if compose:
        class ComposeLoader(yaml.SafeLoader):
            pass

        ComposeLoader.add_constructor("!reset", _ComposeLoaderMixin.reset_constructor)
        loader = ComposeLoader
    value = yaml.load(path.read_text(encoding="utf-8-sig"), Loader=loader)
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a YAML object")
    return value


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_staging_api_ha(repo_root: Path) -> dict[str, Any]:
    compose_path = repo_root / "infra/staging/docker-compose.staging.api-ha.yml"
    nginx_path = repo_root / "infra/staging/nginx.api-ha.conf"
    prometheus_path = repo_root / "infra/staging/prometheus.staging.yml"
    monitoring_smoke_path = repo_root / "scripts/staging-monitoring-smoke.ps1"
    smoke_path = repo_root / "scripts/staging-api-ha-smoke.ps1"
    paths = [
        compose_path,
        nginx_path,
        prometheus_path,
        monitoring_smoke_path,
        smoke_path,
    ]
    _assert(all(path.is_file() for path in paths), "all Staging API HA files must exist")

    compose_text = compose_path.read_text(encoding="utf-8-sig")
    compose = _load_yaml(compose_path, compose=True)
    services = compose.get("services")
    _assert(isinstance(services, dict), "Staging API HA overlay must define services")
    api = services.get("api", {})
    worker = services.get("worker", {})
    scheduler = services.get("scheduler", {})
    proxy = services.get("api-proxy", {})
    _assert(
        re.search(r"(?m)^\s{4}ports:\s*!reset\s*\[\]\s*$", compose_text) is not None,
        "Staging API replicas must reset the root host port publication",
    )
    _assert(api.get("ports") == [], "Staging API replicas must not publish host ports")
    _assert(api.get("expose") == ["8000"], "Staging API replicas must expose only container port 8000")
    shared_runtime_image = "${STAGING_API_IMAGE:-password-detective-api:staging}"
    _assert(
        api.get("image") == shared_runtime_image
        and worker.get("image") == shared_runtime_image
        and scheduler.get("image") == shared_runtime_image,
        "Staging API, Worker and Scheduler must use one candidate runtime image",
    )
    _assert(
        api.get("command")
        == [
            "uvicorn",
            "password_detective.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
        "Staging API replicas must start without concurrent Alembic migration commands",
    )

    _assert(
        proxy.get("image") == "nginx:1.30.4-alpine3.24",
        "Staging API proxy image must be pinned",
    )
    _assert(
        proxy.get("ports") == ["127.0.0.1:${API_PORT:-8000}:8080"],
        "Staging API proxy must bind the single ingress port to loopback",
    )
    _assert(
        proxy.get("volumes")
        == ["./infra/staging/nginx.api-ha.conf:/etc/nginx/conf.d/default.conf:ro"],
        "Staging API proxy must mount the reviewed read-only configuration",
    )
    proxy_dependency = proxy.get("depends_on", {}).get("api", {})
    _assert(
        proxy_dependency.get("condition") == "service_healthy",
        "Staging API proxy must wait for healthy API replicas",
    )
    healthcheck = proxy.get("healthcheck", {}).get("test", [])
    _assert(
        "http://127.0.0.1:8080/api/v1/health/ready" in healthcheck,
        "Staging API proxy healthcheck must traverse the load-balanced readiness path",
    )

    nginx = nginx_path.read_text(encoding="utf-8-sig")
    required_nginx = (
        "resolver 127.0.0.11 ipv6=off valid=5s;",
        "zone password_detective_api 64k;",
        "server api:8000 resolve;",
        "listen 8080;",
        "proxy_pass http://password_detective_api;",
        "proxy_request_buffering off;",
        "access_log off;",
    )
    for marker in required_nginx:
        _assert(marker in nginx, f"Staging API proxy config is missing: {marker}")
    _assert(
        "$upstream_addr" not in nginx,
        "Staging API proxy must not disclose internal replica addresses",
    )

    prometheus = _load_yaml(prometheus_path)
    scrape_configs = prometheus.get("scrape_configs")
    _assert(
        isinstance(scrape_configs, list) and len(scrape_configs) == 1,
        "Staging Prometheus must define exactly one API discovery job",
    )
    scrape = scrape_configs[0]
    _assert(
        scrape.get("job_name") == "password-detective-api"
        and scrape.get("metrics_path") == "/api/v1/metrics",
        "Staging API metrics job drifted",
    )
    _assert(
        scrape.get("dns_sd_configs") == [{"names": ["api"], "type": "A", "port": 8000}],
        "Staging Prometheus must discover every API replica through Compose DNS",
    )
    relabels = scrape.get("relabel_configs", [])
    _assert(
        {"target_label": "service", "replacement": "api"} in relabels
        and {"target_label": "environment", "replacement": "staging"} in relabels,
        "Staging API targets must carry service and environment labels",
    )

    monitoring_smoke = monitoring_smoke_path.read_text(encoding="utf-8-sig")
    _assert(
        "$ExpectedApiTargetCount" in monitoring_smoke,
        "Staging monitoring smoke must verify the expected API target count",
    )
    smoke = smoke_path.read_text(encoding="utf-8-sig")
    for marker in (
        "ExpectedApiReplicas = 2",
        "staging-topology-preflight.ps1",
        "staging-monitoring-smoke.ps1",
        "api_proxy_ready",
    ):
        _assert(marker in smoke, f"Staging API HA smoke is missing: {marker}")

    return {
        "schema": "staging-api-ha-overlay-v1",
        "status": "passed",
        "api_replica_target": 2,
        "ingress_binding": "loopback-only",
        "metrics_discovery": "compose-dns-a-records",
        "files": [str(path.relative_to(repo_root)).replace("\\", "/") for path in paths],
    }


def write_report(repo_root: Path, report_path: Path, write_checksums: bool) -> dict[str, Any]:
    report = validate_staging_api_ha(repo_root)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if write_checksums:
        lines = [
            f"{hashlib.sha256((repo_root / relative).read_bytes()).hexdigest()}  {relative}"
            for relative in report["files"]
        ]
        (report_path.parent / "checksums.sha256").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the WP4 Staging API HA overlay.")
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(".local/staging-api-ha-wp4-iteration-23/contract-report.json"),
    )
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    try:
        repo_root = args.repo_root.resolve()
        report_path = args.report if args.report.is_absolute() else repo_root / args.report
        report = write_report(repo_root, report_path.resolve(), args.write_checksums)
    except (OSError, TypeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Staging API HA validation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
