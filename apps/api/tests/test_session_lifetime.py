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
