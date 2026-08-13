from __future__ import annotations

from sqlalchemy import select

from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.system_setting import SystemSetting
from password_detective.db.models.user import User

PASSWORD = "SyntheticDiscoveryPass123!"


def _register(client, username: str) -> tuple[dict[str, str], str]:
    payload = {
        "username": username,
        "email": f"{username}@synthetic.example.com",
        "password": PASSWORD,
    }
    registered = client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": username, "password": PASSWORD},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, registered.json()["id"]


def _submit(client, headers: dict[str, str], digest: str, sequence: int) -> None:
    response = client.post(
        "/api/v1/archives/submissions",
        headers={**headers, "Idempotency-Key": f"discovery-submission-{sequence:04d}"},
        json={
            "fingerprints": [{"algorithm": "sha256", "digest": digest}],
            "password": f"Synthetic-Archive-{sequence}!",
            "authorization_confirmed": True,
            "authorization_version": "2026-08-13",
            "optional_format": "zip",
        },
    )
    assert response.status_code == 201


def test_public_site_config_uses_safe_defaults_and_published_projection(client):
    defaults = client.get("/api/v1/site/config")
    assert defaults.status_code == 200
    assert defaults.json() == {
        "site_name": "密码侦探社",
        "site_logo_url": "",
        "navigation": [
            {"label": "首页", "path": "/", "enabled": True, "requires_auth": False},
            {"label": "社区", "path": "/community", "enabled": True, "requires_auth": False},
        ],
    }

    with client.app.state.database.session_factory() as db:
        db.add_all(
            [
                SystemSetting(key="site_name", value_json={"value": "合成侦探站"}),
                SystemSetting(key="site_logo_url", value_json={"value": "/brand/logo.svg"}),
                SystemSetting(
                    key="site_navigation",
                    value_json={
                        "value": [
                            {
                                "label": "首页",
                                "path": "/",
                                "enabled": True,
                                "requires_auth": False,
                            },
                            {
                                "label": "用户中心",
                                "path": "/account",
                                "enabled": True,
                                "requires_auth": True,
                            },
                            {
                                "label": "停用入口",
                                "path": "/disabled",
                                "enabled": False,
                                "requires_auth": False,
                            },
                        ]
                    },
                ),
            ]
        )
        db.commit()

    configured = client.get("/api/v1/site/config")
    assert configured.status_code == 200
    assert configured.json()["site_name"] == "合成侦探站"
    assert configured.json()["site_logo_url"] == "/brand/logo.svg"
    assert [item["path"] for item in configured.json()["navigation"]] == ["/", "/account"]


def test_home_discovery_returns_hot_hashes_and_top_five_rankings(client):
    alpha_headers, alpha_id = _register(client, "discovery_alpha")
    beta_headers, beta_id = _register(client, "discovery_beta")
    digests = ["a" * 64, "b" * 64, "c" * 64]

    _submit(client, alpha_headers, digests[0], 1)
    _submit(client, alpha_headers, digests[1], 2)
    _submit(client, beta_headers, digests[2], 3)

    hot_url = f"/api/v1/hashes/sha256/{digests[0]}"
    assert (
        client.put(
            f"{hot_url}/like",
            headers={**alpha_headers, "Idempotency-Key": "discovery-like-alpha"},
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"{hot_url}/like",
            headers={**beta_headers, "Idempotency-Key": "discovery-like-beta"},
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"{hot_url}/vote",
            headers={**beta_headers, "Idempotency-Key": "discovery-vote-beta"},
            json={"outcome": "useful"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{hot_url}/comments",
            headers={**alpha_headers, "Idempotency-Key": "discovery-comment-alpha"},
            json={"content": "Synthetic hot hash note", "rules_accepted": True},
        ).status_code
        == 201
    )

    with client.app.state.database.session_factory() as db:
        users = {
            user.id: user.username
            for user in db.scalars(select(User).where(User.id.in_([alpha_id, beta_id]))).all()
        }
        assert users[alpha_id] == "discovery_alpha"
        ledgers = db.scalars(select(PointsLedger)).all()
        for ledger in ledgers:
            ledger.status = PointsLedgerStatus.POSTED
            ledger.amount = 10 if ledger.user_id == alpha_id else 4
        db.commit()

    response = client.get("/api/v1/site/home-discovery")
    assert response.status_code == 200
    body = response.json()
    assert len(body["hot_hashes"]) <= 5
    assert body["hot_hashes"][0] == {
        "algorithm": "sha256",
        "digest": digests[0],
        "like_count": 2,
        "comment_count": 1,
        "useful_vote_count": 1,
        "heat_score": 10,
    }
    assert body["contribution_leaders"][0]["uid"] == alpha_id
    assert body["contribution_leaders"][0]["score"] == 2
    assert body["points_leaders"][0]["uid"] == alpha_id
    assert body["points_leaders"][0]["score"] == 20
    assert all(len(body[key]) <= 5 for key in ("contribution_leaders", "points_leaders"))
