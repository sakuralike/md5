#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REQUEST_ID_PATTERN = re.compile(r"^req_[0-9a-f]{32}$")
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "cache-control": "no-store",
}


@dataclass(frozen=True)
class HttpResult:
    status: int
    headers: dict[str, str]
    body: str


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    status: int | None
    detail: str


def request(
    base_url: str,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 10.0,
) -> HttpResult:
    req = Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers=headers or {},
        method=method,
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            return HttpResult(
                status=response.status,
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read().decode("utf-8", errors="replace"),
            )
    except HTTPError as exc:
        return HttpResult(
            status=exc.code,
            headers={key.lower(): value for key, value in exc.headers.items()},
            body=exc.read().decode("utf-8", errors="replace"),
        )


def run_checks(base_url: str) -> list[CheckResult]:
    checks: list[CheckResult] = []

    ready = request(base_url, "GET", "/api/v1/health/ready")
    ready_payload = _parse_json(ready.body)
    checks.append(
        CheckResult(
            "readiness",
            ready.status == 200 and ready_payload.get("status") == "ready",
            ready.status,
            "ready endpoint returned the expected dependency status",
        )
    )

    live = request(base_url, "GET", "/api/v1/health/live")
    missing_headers = [
        name for name, expected in SECURITY_HEADERS.items() if live.headers.get(name) != expected
    ]
    csp = live.headers.get("content-security-policy", "")
    request_id = live.headers.get("x-request-id", "")
    checks.append(
        CheckResult(
            "security_headers",
            live.status == 200
            and not missing_headers
            and "frame-ancestors 'none'" in csp
            and REQUEST_ID_PATTERN.fullmatch(request_id) is not None,
            live.status,
            (
                "security headers and generated request id present"
                if not missing_headers
                else f"missing or mismatched headers: {','.join(missing_headers)}"
            ),
        )
    )

    protected_failures: list[str] = []
    for method, path in (
        ("GET", "/api/v1/me/profile"),
        ("POST", "/api/v1/me/privacy/exports"),
        ("GET", "/api/v1/admin/users"),
        ("GET", "/api/v1/admin/audit-logs"),
    ):
        result = request(base_url, method, path)
        payload = _parse_json(result.body)
        if result.status != 401 or payload.get("code") != "auth.authentication_required":
            protected_failures.append(f"{method} {path} -> {result.status}")
    checks.append(
        CheckResult(
            "anonymous_authorization_boundaries",
            not protected_failures,
            None,
            "anonymous user/admin boundaries denied"
            if not protected_failures
            else "; ".join(protected_failures),
        )
    )

    preflight = {
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization,X-Request-ID",
    }
    allowed = request(
        base_url,
        "OPTIONS",
        "/api/v1/me/profile",
        headers={"Origin": "http://localhost:5173", **preflight},
    )
    rejected = request(
        base_url,
        "OPTIONS",
        "/api/v1/me/profile",
        headers={"Origin": "https://untrusted.example", **preflight},
    )
    checks.append(
        CheckResult(
            "cors_origin_policy",
            allowed.status == 200
            and allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
            and rejected.status == 400
            and "access-control-allow-origin" not in rejected.headers,
            None,
            f"allowed={allowed.status}, untrusted={rejected.status}",
        )
    )

    unsupported = request(base_url, "POST", "/api/v1/health/live", body=b"")
    checks.append(
        CheckResult(
            "unsupported_method",
            unsupported.status == 405 and "traceback" not in unsupported.body.lower(),
            unsupported.status,
            "unsupported method rejected without traceback",
        )
    )

    xss_canary = "<script>wp4_dast_probe()</script>"
    query = urlencode({"probe": xss_canary})
    reflected = request(base_url, "GET", f"/api/v1/health/live?{query}")
    checks.append(
        CheckResult(
            "xss_non_reflection",
            reflected.status == 200 and xss_canary not in reflected.body,
            reflected.status,
            "query canary was not reflected",
        )
    )

    password_canary = "Synthetic-WP4-DAST-Password!"
    token_canary = "wp4.synthetic.dast.token"
    login_body = json.dumps(
        {"login": f"missing-{token_canary}", "password": password_canary}
    ).encode()
    login = request(
        base_url,
        "POST",
        "/api/v1/auth/login",
        headers={"Content-Type": "application/json"},
        body=login_body,
    )
    checks.append(
        CheckResult(
            "credential_non_reflection",
            login.status == 401
            and password_canary not in login.body
            and token_canary not in login.body,
            login.status,
            "synthetic credential canaries were not reflected",
        )
    )

    oversized_body = b'{"probe":"' + (b"x" * 1_048_576) + b'"}'
    oversized = request(
        base_url,
        "POST",
        "/api/v1/auth/login",
        headers={"Content-Type": "application/json"},
        body=oversized_body,
        timeout=20.0,
    )
    oversized_payload = _parse_json(oversized.body)
    checks.append(
        CheckResult(
            "oversized_json_body",
            oversized.status == 413 and oversized_payload.get("code") == "request.body_too_large",
            oversized.status,
            "oversized JSON body rejected before endpoint handling",
        )
    )

    return checks


def write_report(output: Path, base_url: str, checks: list[CheckResult]) -> None:
    passed = sum(check.passed for check in checks)
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "target": base_url,
        "summary": {
            "total": len(checks),
            "passed": passed,
            "failed": len(checks) - passed,
        },
        "checks": [asdict(check) for check in checks],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_json(body: str) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic API dynamic security probes.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    parser.add_argument("--output", type=Path, default=Path(".local/security-dast/dast-report.json"))
    args = parser.parse_args()

    try:
        checks = run_checks(args.base_url)
    except (URLError, TimeoutError, OSError) as exc:
        print(f"DAST target is unavailable: {exc}", file=sys.stderr)
        return 2

    write_report(args.output, args.base_url, checks)
    for check in checks:
        marker = "PASS" if check.passed else "FAIL"
        print(f"[{marker}] {check.name}: {check.detail}")
    failed = [check.name for check in checks if not check.passed]
    if failed:
        print(f"DAST security gate failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"DAST security gate passed. Evidence: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
