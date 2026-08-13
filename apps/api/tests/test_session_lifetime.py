from __future__ import annotations

from password_detective.core.config import Settings


def test_default_browser_session_lifetimes_support_long_running_sessions(monkeypatch):
    monkeypatch.delenv("ACCESS_TOKEN_TTL_MINUTES", raising=False)
    monkeypatch.delenv("REFRESH_TOKEN_TTL_DAYS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.access_token_ttl_minutes == 120
    assert settings.refresh_token_ttl_days == 90


def test_browser_session_lifetimes_remain_operator_configurable():
    settings = Settings(
        _env_file=None,
        access_token_ttl_minutes=720,
        refresh_token_ttl_days=180,
    )

    assert settings.access_token_ttl_minutes == 720
    assert settings.refresh_token_ttl_days == 180

def test_login_rate_limits_keep_secure_defaults_and_allow_controlled_overrides(monkeypatch):
    monkeypatch.delenv("WEB_LOGIN_RATE_LIMIT", raising=False)
    monkeypatch.delenv("ADMIN_LOGIN_RATE_LIMIT", raising=False)

    defaults = Settings(_env_file=None)
    overridden = Settings(
        _env_file=None,
        web_login_rate_limit=100,
        admin_login_rate_limit=80,
    )

    assert defaults.web_login_rate_limit == 10
    assert defaults.admin_login_rate_limit == 10
    assert overridden.web_login_rate_limit == 100
    assert overridden.admin_login_rate_limit == 80
