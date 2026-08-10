from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

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


def parse_set_cookie(set_cookie: str) -> tuple[str, dict[str, str | bool]]:
    cookie = SimpleCookie()
    cookie.load(set_cookie)
    if not cookie:
        return "", {}
    morsel = next(iter(cookie.values()))
    attributes: dict[str, str | bool] = {"name": morsel.key}
    for key in ("httponly", "secure"):
        attributes[key] = bool(morsel[key])
    for key in ("path", "samesite"):
        if morsel[key]:
            attributes[key] = morsel[key]
    return morsel.value, attributes


def _promote_dast_user_to_admin(username: str) -> None:
    """Promote a synthetic DAST fixture without exposing an admin bootstrap API."""
    from password_detective.core.config import Settings
    from password_detective.db.database import Database
    from password_detective.db.models.user import User, UserRole
    from sqlalchemy import select

    database = Database(Settings())
    try:
        with database.session_factory() as db:
            user = db.scalar(select(User).where(User.username == username))
            if user is None:
                raise RuntimeError("DAST admin fixture registration was not persisted")
            user.role = UserRole.ADMIN
            db.commit()
    finally:
        database.dispose()


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
        name
        for name, expected in SECURITY_HEADERS.items()
        if live.headers.get(name) != expected
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
        if (
            result.status != 401
            or payload.get("code") != "auth.authentication_required"
        ):
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
            and allowed.headers.get("access-control-allow-origin")
            == "http://localhost:5173"
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
            oversized.status == 413
            and oversized_payload.get("code") == "request.body_too_large",
            oversized.status,
            "oversized JSON body rejected before endpoint handling",
        )
    )

    suffix = uuid4().hex[:12]
    user_a = {
        "username": f"dast_owner_{suffix}",
        "email": f"dast-owner-{suffix}@example.com",
        "password": "SyntheticDastPass123!",
    }
    user_b = {
        "username": f"dast_other_{suffix}",
        "email": f"dast-other-{suffix}@example.com",
        "password": "SyntheticDastPass123!",
    }
    registration_failures: list[str] = []
    for label, payload in (("owner", user_a), ("other", user_b)):
        registered = request(
            base_url,
            "POST",
            "/api/v1/auth/register",
            headers={"Content-Type": "application/json"},
            body=json.dumps(payload).encode(),
        )
        if registered.status != 201:
            registration_failures.append(f"{label} registration -> {registered.status}")
    tokens: dict[str, str] = {}
    for label, payload in (("owner", user_a), ("other", user_b)):
        logged_in = request(
            base_url,
            "POST",
            "/api/v1/auth/login",
            headers={"Content-Type": "application/json"},
            body=json.dumps(
                {"login": payload["username"], "password": payload["password"]}
            ).encode(),
        )
        logged_payload = _parse_json(logged_in.body)
        if logged_in.status != 200 or not logged_payload.get("access_token"):
            registration_failures.append(f"{label} login -> {logged_in.status}")
        else:
            tokens[label] = str(logged_payload["access_token"])

    object_failures = list(registration_failures)
    if len(tokens) == 2:
        owner_headers = {"Authorization": f"Bearer {tokens['owner']}"}
        other_headers = {"Authorization": f"Bearer {tokens['other']}"}
        export = request(
            base_url,
            "POST",
            "/api/v1/me/privacy/exports",
            headers={**owner_headers, "Idempotency-Key": f"dast-export-{suffix}"},
            body=b"{}",
        )
        export_payload = _parse_json(export.body)
        export_id = export_payload.get("id")
        if export.status not in (200, 202) or not export_id:
            object_failures.append(f"owner export -> {export.status}")
        else:
            other_export = request(
                base_url,
                "GET",
                f"/api/v1/me/privacy/exports/{export_id}",
                headers=other_headers,
            )
            if (
                other_export.status != 404
                or _parse_json(other_export.body).get("code")
                != "privacy.export_not_found"
            ):
                object_failures.append(
                    f"cross-user export read -> {other_export.status}"
                )

        owner_sessions = request(
            base_url,
            "GET",
            "/api/v1/me/security/sessions",
            headers=owner_headers,
        )
        sessions_payload = _parse_json_list(owner_sessions.body)
        sessions = sessions_payload
        family_id = sessions[0].get("id") if sessions else None
        if not family_id:
            object_failures.append(f"owner sessions -> {owner_sessions.status}")
        else:
            cross_revoke = request(
                base_url,
                "DELETE",
                f"/api/v1/me/security/sessions/{family_id}",
                headers=other_headers,
            )
            if (
                cross_revoke.status != 404
                or _parse_json(cross_revoke.body).get("code")
                != "auth.session_not_found"
            ):
                object_failures.append(
                    f"cross-user session revoke -> {cross_revoke.status}"
                )
    checks.append(
        CheckResult(
            "authenticated_object_boundaries",
            not object_failures,
            None,
            "cross-user export read and session revoke denied"
            if not object_failures
            else "; ".join(object_failures),
        )
    )

    browser_login = request(
        base_url,
        "POST",
        "/api/v1/web/auth/login",
        headers={"Origin": "http://localhost:5173", "Content-Type": "application/json"},
        body=json.dumps(
            {"login": user_a["username"], "password": user_a["password"]}
        ).encode(),
    )
    set_cookie = browser_login.headers.get("set-cookie", "")
    cookie_value, cookie_attributes = parse_set_cookie(set_cookie)
    browser_csrf = request(
        base_url,
        "POST",
        "/api/v1/web/auth/refresh",
        headers={
            "Origin": "https://untrusted.example",
            "Cookie": f"pd_web_refresh={cookie_value}",
        },
    )
    browser_refresh = request(
        base_url,
        "POST",
        "/api/v1/web/auth/refresh",
        headers={
            "Origin": "http://localhost:5173",
            "Cookie": f"pd_web_refresh={cookie_value}",
        },
    )
    cookie_ok = (
        browser_login.status == 200
        and cookie_attributes.get("name") == "pd_web_refresh"
        and cookie_attributes.get("httponly") is True
        and cookie_attributes.get("path") == "/api/v1/web/auth"
        and str(cookie_attributes.get("samesite", "")).lower() == "lax"
        and browser_csrf.status == 403
        and _parse_json(browser_csrf.body).get("code") == "request.invalid_origin"
        and browser_refresh.status == 200
    )
    checks.append(
        CheckResult(
            "browser_cookie_csrf_samesite",
            cookie_ok,
            browser_csrf.status if browser_csrf.status != 200 else browser_login.status,
            "refresh cookie is HttpOnly/Lax/path-scoped and cross-site refresh is denied"
            if cookie_ok
            else f"login={browser_login.status}, csrf={browser_csrf.status}, refresh={browser_refresh.status}",
        )
    )

    admin_password = "SyntheticDastAdminPass123!"
    admin_username = f"dast_admin_{uuid4().hex[:12]}"
    admin_email = f"{admin_username}@example.com"
    admin_registration = request(
        base_url,
        "POST",
        "/api/v1/auth/register",
        headers={"Content-Type": "application/json"},
        body=json.dumps(
            {
                "username": admin_username,
                "email": admin_email,
                "password": admin_password,
            }
        ).encode(),
    )
    admin_registered = admin_registration.status == 201
    if admin_registered:
        _promote_dast_user_to_admin(admin_username)

    initial_admin_login = request(
        base_url,
        "POST",
        "/api/v1/auth/login",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"login": admin_username, "password": admin_password}).encode(),
    )
    initial_admin_token = _parse_json(initial_admin_login.body).get("access_token", "")
    initial_admin_headers = {"Authorization": f"Bearer {initial_admin_token}"}
    setup = request(
        base_url,
        "POST",
        "/api/v1/admin/totp/setup",
        headers={**initial_admin_headers, "Content-Type": "application/json"},
        body=b"{}",
    )
    setup_payload = _parse_json(setup.body)
    admin_secret = setup_payload.get("secret", "")

    import pyotp

    confirm = request(
        base_url,
        "POST",
        "/api/v1/admin/totp/confirm",
        headers={**initial_admin_headers, "Content-Type": "application/json"},
        body=json.dumps({"code": pyotp.TOTP(admin_secret).now()}).encode(),
    )
    mfa_required = request(
        base_url, "GET", "/api/v1/admin/access-check", headers=initial_admin_headers
    )
    admin_login = request(
        base_url,
        "POST",
        "/api/v1/admin/auth/login",
        headers={"Origin": "http://localhost:5173", "Content-Type": "application/json"},
        body=json.dumps(
            {
                "login": admin_username,
                "password": admin_password,
                "totp_code": pyotp.TOTP(admin_secret).now(),
            }
        ).encode(),
    )
    admin_login_payload = _parse_json(admin_login.body)
    admin_token = admin_login_payload.get("access_token", "")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    access_check = request(
        base_url, "GET", "/api/v1/admin/access-check", headers=admin_headers
    )

    wrong_reauth = request(
        base_url,
        "POST",
        "/api/v1/admin/auth/reauthenticate",
        headers={**admin_headers, "Content-Type": "application/json"},
        body=json.dumps(
            {
                "current_password": "SyntheticWrongPass123!",
                "totp_code": pyotp.TOTP(admin_secret).now(),
            }
        ).encode(),
    )
    reauth = request(
        base_url,
        "POST",
        "/api/v1/admin/auth/reauthenticate",
        headers={**admin_headers, "Content-Type": "application/json"},
        body=json.dumps(
            {
                "current_password": admin_password,
                "totp_code": pyotp.TOTP(admin_secret).now(),
            }
        ).encode(),
    )
    reauth_payload = _parse_json(reauth.body)
    reauth_token = reauth_payload.get("reauth_token", "")
    admin_security_ok = (
        admin_registered
        and initial_admin_login.status == 200
        and setup.status == 200
        and bool(admin_secret)
        and confirm.status == 200
        and mfa_required.status == 403
        and _parse_json(mfa_required.body).get("code") == "auth.totp_required"
        and admin_login.status == 200
        and access_check.status == 200
        and access_check.headers.get("cache-control") == "no-store"
        and wrong_reauth.status == 400
        and _parse_json(wrong_reauth.body).get("code")
        == "auth.invalid_current_password"
        and reauth.status == 200
        and bool(reauth_token)
        and reauth.headers.get("cache-control") == "no-store"
    )
    checks.append(
        CheckResult(
            "admin_mfa_reauthentication",
            admin_security_ok,
            reauth.status,
            "admin MFA setup, MFA-gated access, wrong-credential rejection, and no-store reauthentication passed"
            if admin_security_ok
            else f"register={admin_registration.status}, setup={setup.status}, mfa={mfa_required.status}, login={admin_login.status}, reauth={reauth.status}",
        )
    )

    target_username = f"dast_target_{uuid4().hex[:12]}"
    target_password = "SyntheticDastTargetPass123!"
    target_registration = request(
        base_url,
        "POST",
        "/api/v1/auth/register",
        headers={"Content-Type": "application/json"},
        body=json.dumps(
            {
                "username": target_username,
                "email": f"{target_username}@example.com",
                "password": target_password,
            }
        ).encode(),
    )
    target_login = request(
        base_url,
        "POST",
        "/api/v1/auth/login",
        headers={"Content-Type": "application/json"},
        body=json.dumps(
            {"login": target_username, "password": target_password}
        ).encode(),
    )
    target_login_payload = _parse_json(target_login.body)
    target_token = target_login_payload.get("access_token", "")
    target_user_id = ""
    if target_token:
        profile = request(
            base_url,
            "GET",
            "/api/v1/me/profile",
            headers={"Authorization": f"Bearer {target_token}"},
        )
        target_user_id = _parse_json(profile.body).get("id", "")

    replay_target_username = f"dast_replay_target_{uuid4().hex[:12]}"
    replay_target_password = "SyntheticDastReplayTargetPass123!"
    replay_registration = request(
        base_url,
        "POST",
        "/api/v1/auth/register",
        headers={"Content-Type": "application/json"},
        body=json.dumps(
            {
                "username": replay_target_username,
                "email": f"{replay_target_username}@example.com",
                "password": replay_target_password,
            }
        ).encode(),
    )
    replay_login = request(
        base_url,
        "POST",
        "/api/v1/auth/login",
        headers={"Content-Type": "application/json"},
        body=json.dumps(
            {"login": replay_target_username, "password": replay_target_password}
        ).encode(),
    )
    replay_target_id = ""
    replay_token = _parse_json(replay_login.body).get("access_token", "")
    if replay_token:
        replay_profile = request(
            base_url,
            "GET",
            "/api/v1/me/profile",
            headers={"Authorization": f"Bearer {replay_token}"},
        )
        replay_target_id = _parse_json(replay_profile.body).get("id", "")

    action_key = f"wp4-dast-status-{uuid4().hex}"
    action_payload = {
        "expected_status": "active",
        "status": "disabled",
        "reason_code": "security_risk",
        "reauth_token": reauth_token,
    }
    action = request(
        base_url,
        "PATCH",
        f"/api/v1/admin/users/{target_user_id}/status",
        headers={
            **admin_headers,
            "Content-Type": "application/json",
            "Idempotency-Key": action_key,
        },
        body=json.dumps(action_payload).encode(),
    )
    replay = request(
        base_url,
        "PATCH",
        f"/api/v1/admin/users/{target_user_id}/status",
        headers={
            **admin_headers,
            "Content-Type": "application/json",
            "Idempotency-Key": action_key,
        },
        body=json.dumps(action_payload).encode(),
    )
    conflict_payload = {**action_payload, "reason_code": "manual_review"}
    conflict = request(
        base_url,
        "PATCH",
        f"/api/v1/admin/users/{target_user_id}/status",
        headers={
            **admin_headers,
            "Content-Type": "application/json",
            "Idempotency-Key": action_key,
        },
        body=json.dumps(conflict_payload).encode(),
    )
    consumed = request(
        base_url,
        "PATCH",
        f"/api/v1/admin/users/{replay_target_id}/status",
        headers={
            **admin_headers,
            "Content-Type": "application/json",
            "Idempotency-Key": f"{action_key}-consumed",
        },
        body=json.dumps(action_payload).encode(),
    )
    action_body = _parse_json(action.body)
    replay_body = _parse_json(replay.body)
    idempotency_ok = (
        target_registration.status == 201
        and target_login.status == 200
        and replay_registration.status == 201
        and replay_login.status == 200
        and bool(target_user_id)
        and bool(replay_target_id)
        and action.status == 200
        and action_body.get("current_status") == "disabled"
        and replay.status == 200
        and replay_body == action_body
        and conflict.status == 409
        and _parse_json(conflict.body).get("code") == "request.idempotency_conflict"
        and consumed.status == 401
        and _parse_json(consumed.body).get("code")
        == "auth.invalid_reauthentication_token"
    )
    checks.append(
        CheckResult(
            "idempotency_replay_conflict",
            idempotency_ok,
            conflict.status,
            "admin status mutation replayed safely, rejected payload conflict, and consumed reauth grant once"
            if idempotency_ok
            else f"action={action.status}, replay={replay.status}, conflict={conflict.status}, consumed={consumed.status}",
        )
    )

    limit_results: list[HttpResult] = []
    for _ in range(12):
        limit_results.append(
            request(
                base_url,
                "POST",
                "/api/v1/admin/auth/reauthenticate",
                headers={**admin_headers, "Content-Type": "application/json"},
                body=json.dumps(
                    {
                        "current_password": "SyntheticWrongPass123!",
                        "totp_code": pyotp.TOTP(admin_secret).now(),
                    }
                ).encode(),
            )
        )
    first_limited = next(
        (result for result in limit_results if result.status == 429), None
    )
    rate_limit_ok = (
        first_limited is not None
        and _parse_json(first_limited.body).get("code") == "rate_limit.exceeded"
        and bool(first_limited.headers.get("retry-after"))
    )
    checks.append(
        CheckResult(
            "admin_reauthentication_rate_limit",
            rate_limit_ok,
            first_limited.status if first_limited else limit_results[-1].status,
            "repeated privileged reauthentication attempts reached a 429 gate with Retry-After"
            if rate_limit_ok
            else f"statuses={[result.status for result in limit_results]}",
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
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _parse_json(body: str) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_json_list(body: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic API dynamic security probes."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    parser.add_argument(
        "--output", type=Path, default=Path(".local/security-dast/dast-report.json")
    )
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
