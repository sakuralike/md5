from __future__ import annotations

from starlette.requests import Request

from password_detective.core.client_ip import masked_ip_prefix, resolve_client_ip
from password_detective.db.models.system_setting import SystemSetting


def _request(*, peer: str, forwarded_for: str = "") -> Request:
    headers = []
    if forwarded_for:
        headers.append((b"x-forwarded-for", forwarded_for.encode("ascii")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/site/home-discovery",
            "raw_path": b"/api/v1/site/home-discovery",
            "query_string": b"",
            "headers": headers,
            "client": (peer, 50000),
            "server": ("testserver", 80),
        }
    )


def test_client_ip_only_trusts_forwarded_chain_from_configured_proxy():
    spoofed = _request(peer="198.51.100.20", forwarded_for="192.0.2.10")
    assert str(resolve_client_ip(spoofed, trusted_proxy_cidrs="127.0.0.1/32")) == "198.51.100.20"

    proxied = _request(
        peer="127.0.0.1",
        forwarded_for="192.0.2.10, 10.0.0.8",
    )
    resolved = resolve_client_ip(
        proxied,
        trusted_proxy_cidrs="127.0.0.1/32,10.0.0.0/8",
    )
    assert str(resolved) == "192.0.2.10"
    assert masked_ip_prefix(resolved) == "192.0.2.0/24"


def test_maintenance_mode_blocks_business_but_keeps_operations_and_public_projection(client):
    with client.app.state.database.session_factory() as db:
        db.add_all(
            [
                SystemSetting(key="maintenance_enabled", value_json={"value": True}),
                SystemSetting(
                    key="maintenance_message",
                    value_json={"value": "合成维护窗口"},
                ),
                SystemSetting(
                    key="maintenance_allowed_ip_cidrs",
                    value_json={"value": []},
                ),
            ]
        )
        db.commit()

    public_config = client.get("/api/v1/site/config")
    assert public_config.status_code == 200
    assert public_config.json()["maintenance"] == {
        "active": True,
        "message": "合成维护窗口",
    }
    assert "maintenance_allowed_ip_cidrs" not in public_config.text

    blocked = client.get("/api/v1/site/home-discovery")
    assert blocked.status_code == 503
    assert blocked.headers["retry-after"] == "300"
    assert blocked.json()["code"] == "maintenance.active"
    assert blocked.json()["message"] == "合成维护窗口"
    assert client.get("/api/v1/health/live").status_code == 200

    client.app.state.settings.maintenance_force_disabled = True
    emergency_config = client.get("/api/v1/site/config")
    assert emergency_config.status_code == 200
    assert emergency_config.json()["maintenance"]["active"] is False
    assert client.get("/api/v1/site/home-discovery").status_code == 200
