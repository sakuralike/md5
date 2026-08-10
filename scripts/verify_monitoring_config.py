from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_RULES = {
    "PasswordDetectiveApiTargetDown",
    "PasswordDetectiveDatabaseUnavailable",
    "PasswordDetectiveRedisUnavailable",
    "PasswordDetectiveWorkerHeartbeatMissing",
    "PasswordDetectiveHighErrorRate",
    "PasswordDetectiveHighP95Latency",
    "PasswordDetectiveWorkerQueueBacklog",
}
REQUIRED_METRICS = {
    "password_detective_http_requests_total",
    "password_detective_http_request_duration_seconds_bucket",
    "password_detective_worker_queue_depth",
    "password_detective_dependency_up",
    "password_detective_process_uptime_seconds",
}
FORBIDDEN = re.compile(
    r"(?:request_id|user_id|email|fingerprint|access_token|refresh_token|secret_value)",
    re.IGNORECASE,
)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - exercised by CI setup failure
        raise RuntimeError(
            "PyYAML is required for monitoring configuration validation"
        ) from exc
    value = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a YAML object")
    return value


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_monitoring_files(repo_root: Path) -> dict[str, Any]:
    prometheus_path = repo_root / "infra/monitoring/prometheus/prometheus.yml"
    rules_path = repo_root / "infra/monitoring/prometheus/alerts/password-detective.yml"
    datasource_path = (
        repo_root / "infra/monitoring/grafana/provisioning/datasources/prometheus.yml"
    )
    dashboards_path = (
        repo_root / "infra/monitoring/grafana/provisioning/dashboards/dashboards.yml"
    )
    dashboard_path = (
        repo_root
        / "infra/monitoring/grafana/dashboards/password-detective-overview.json"
    )
    compose_path = repo_root / "infra/monitoring/docker-compose.monitoring.yml"
    alertmanager_path = repo_root / "infra/monitoring/alertmanager/alertmanager.yml"
    receiver_path = repo_root / "scripts/alertmanager_receiver.py"
    paths = [
        prometheus_path,
        rules_path,
        datasource_path,
        dashboards_path,
        dashboard_path,
        compose_path,
        alertmanager_path,
        receiver_path,
    ]
    _assert(
        all(path.is_file() for path in paths),
        "all WP4 iteration 9 monitoring files must exist",
    )

    prometheus = _load_yaml(prometheus_path)
    scrape_configs = prometheus.get("scrape_configs")
    _assert(
        isinstance(scrape_configs, list) and len(scrape_configs) == 1,
        "exactly one API scrape config is required",
    )
    scrape = scrape_configs[0]
    _assert(
        scrape.get("job_name") == "password-detective-api",
        "API scrape job name drifted",
    )
    _assert(
        scrape.get("metrics_path") == "/api/v1/metrics",
        "scrape path must be the metrics endpoint",
    )
    targets = scrape.get("static_configs", [{}])[0].get("targets", [])
    _assert(targets == ["api:8000"], "monitoring must scrape the Compose API service")
    rule_files = prometheus.get("rule_files", [])
    alertmanagers = prometheus.get("alerting", {}).get("alertmanagers", [])
    _assert(
        alertmanagers == [{"static_configs": [{"targets": ["alertmanager:9093"]}]}],
        "Prometheus must forward alerts to the Compose Alertmanager service",
    )
    _assert(
        rule_files == ["/etc/prometheus/alerts/*.yml"],
        "rule file glob must be mounted alert directory",
    )

    rules_document = _load_yaml(rules_path)
    groups = rules_document.get("groups")
    _assert(
        isinstance(groups, list) and groups,
        "alert rules must contain at least one group",
    )
    rules = [
        rule
        for group in groups
        for rule in group.get("rules", [])
        if isinstance(rule, dict)
    ]
    actual_rules = {str(rule.get("alert")) for rule in rules}
    _assert(
        REQUIRED_RULES <= actual_rules,
        f"missing alert rules: {sorted(REQUIRED_RULES - actual_rules)}",
    )
    for rule in rules:
        alert = str(rule.get("alert", ""))
        if alert not in REQUIRED_RULES:
            continue
        expression = str(rule.get("expr", ""))
        _assert(expression, f"{alert} must have an expression")
        _assert(
            not FORBIDDEN.search(expression),
            f"{alert} contains a sensitive/high-cardinality label",
        )
        labels = rule.get("labels")
        annotations = rule.get("annotations")
        _assert(
            isinstance(labels, dict)
            and labels.get("severity") in {"warning", "critical"},
            f"{alert} needs a severity",
        )
        _assert(
            isinstance(annotations, dict)
            and annotations.get("runbook") == "docs/runbooks/wp4-monitoring.md",
            f"{alert} needs the monitoring runbook",
        )
    expressions = "\n".join(str(rule.get("expr", "")) for rule in rules)
    alert_metrics = REQUIRED_METRICS - {"password_detective_process_uptime_seconds"}
    for metric in alert_metrics:
        _assert(metric in expressions, f"alert rules must reference {metric}")

    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8-sig"))
    _assert(
        dashboard.get("uid") == "password-detective-overview", "dashboard UID drifted"
    )
    panels = dashboard.get("panels")
    _assert(
        isinstance(panels, list) and len(panels) >= 5,
        "dashboard needs at least five panels",
    )
    dashboard_text = json.dumps(dashboard, ensure_ascii=False)
    _assert(
        not FORBIDDEN.search(dashboard_text),
        "dashboard contains a sensitive/high-cardinality field",
    )
    for metric in REQUIRED_METRICS:
        _assert(metric in dashboard_text, f"dashboard must reference {metric}")

    datasource = _load_yaml(datasource_path)
    data_sources = datasource.get("datasources")
    _assert(
        isinstance(data_sources, list) and data_sources[0].get("uid") == "prometheus",
        "Prometheus datasource provisioning is required",
    )
    dashboards = _load_yaml(dashboards_path)
    _assert(
        dashboards.get("providers", [{}])[0].get("options", {}).get("path")
        == "/var/lib/grafana/dashboards",
        "Grafana dashboard provisioning path drifted",
    )
    alertmanager = _load_yaml(alertmanager_path)
    route = alertmanager.get("route", {})
    _assert(
        route.get("receiver") == "password-detective-notification-gateway",
        "Alertmanager must route to the notification gateway",
    )
    _assert(
        route.get("group_by") == ["alertname", "service", "severity", "environment"],
        "Alertmanager group_by must stay low-cardinality",
    )
    _assert(route.get("group_wait") == "2s", "Alertmanager drill group_wait must be two seconds")
    _assert(route.get("group_interval") == "5s", "Alertmanager drill group_interval must be five seconds")
    receivers = alertmanager.get("receivers", [])
    _assert(
        any(
            receiver.get("name") == "password-detective-notification-gateway"
            and receiver.get("webhook_configs", [{}])[0].get("send_resolved") is True
            and receiver.get("webhook_configs", [{}])[0].get("url") == "http://alert-receiver:18081/alerts"
            for receiver in receivers
        ),
        "Alertmanager must expose a resolved-capable internal webhook receiver",
    )
    alertmanager_text = alertmanager_path.read_text(encoding="utf-8-sig")
    _assert(not FORBIDDEN.search(alertmanager_text), "Alertmanager config contains a sensitive/high-cardinality field")
    receiver_text = receiver_path.read_text(encoding="utf-8-sig")
    for marker in ("normalize_alertmanager_payload", "FORBIDDEN_KEY", "REDACTED", "/events"):
        _assert(marker in receiver_text, f"notification gateway is missing {marker}")
    compose_text = compose_path.read_text(encoding="utf-8-sig")
    for service in ("prometheus:", "grafana:", "alertmanager:", "alert-receiver:", 'profiles: ["monitoring"]'):
        _assert(
            service in compose_text, f"monitoring Compose overlay missing {service}"
        )

    return {
        "schema": "monitoring-config-v2",
        "status": "passed",
        "rule_count": len(REQUIRED_RULES),
        "dashboard_panel_count": len(panels),
        "required_metrics": sorted(REQUIRED_METRICS),
        "files": [
            str(path.relative_to(repo_root)).replace("\\", "/") for path in paths
        ],
    }


def write_report(
    repo_root: Path, report_path: Path, write_checksums: bool
) -> dict[str, Any]:
    report = validate_monitoring_files(repo_root)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if write_checksums:
        lines = []
        for relative in report["files"]:
            path = repo_root / relative
            lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative}")
        (report_path.parent / "checksums.sha256").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate WP4 Prometheus and Grafana artifacts."
    )
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(".local/monitoring-wp4-iteration-9/monitoring-report.json"),
    )
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    try:
        report_path = (
            args.report if args.report.is_absolute() else args.repo_root / args.report
        )
        report = write_report(
            args.repo_root.resolve(), report_path.resolve(), args.write_checksums
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"monitoring validation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
