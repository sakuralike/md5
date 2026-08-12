from __future__ import annotations

import pyotp
from sqlalchemy import select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.community import CommunityBoard
from password_detective.db.models.user import User, UserRole

PASSWORD = "SyntheticCommunityAdmin123!"


def _admin_session(client, suffix: str, role: UserRole = UserRole.ADMIN) -> dict[str, str]:
    registration = {
        "username": f"board_admin_{suffix}",
        "email": f"board-admin-{suffix}@synthetic.example.com",
        "password": PASSWORD,
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": PASSWORD},
    )
    assert login.status_code == 200
    initial_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = role
        db.commit()
    setup = client.post("/api/v1/admin/totp/setup", headers=initial_headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    confirm = client.post(
        "/api/v1/admin/totp/confirm",
        headers=initial_headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert confirm.status_code == 200
    authenticated = client.post(
        "/api/v1/auth/login",
        json={
            "login": registration["username"],
            "password": PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert authenticated.status_code == 200
    return {"Authorization": f"Bearer {authenticated.json()['access_token']}"}


def test_board_configuration_requires_admin_mfa_and_seeds_catalog(client):
    moderator_headers = _admin_session(client, "moderator", UserRole.MODERATOR)
    forbidden = client.get("/api/v1/admin/community/boards", headers=moderator_headers)
    assert forbidden.status_code == 403

    admin_headers = _admin_session(client, "owner")
    listed = client.get("/api/v1/admin/community/boards", headers=admin_headers)
    assert listed.status_code == 200
    assert [item["code"] for item in listed.json()["items"]][:4] == [
        "general",
        "recovery_guides",
        "verification",
        "security",
    ]


def test_admin_can_create_and_logically_deactivate_board_idempotently(client):
    admin_headers = _admin_session(client, "configuration")
    create_headers = {**admin_headers, "Idempotency-Key": "board-create-synthetic-0001"}
    payload = {
        "code": "synthetic_lab",
        "name": "合成研究",
        "description": "仅使用合成数据验证社区板块配置。",
        "sort_order": 25,
        "minimum_role": "trusted_contributor",
        "is_read_only": False,
        "status": "active",
    }
    created = client.post(
        "/api/v1/admin/community/boards",
        headers=create_headers,
        json=payload,
    )
    assert created.status_code == 201, created.text
    replay = client.post(
        "/api/v1/admin/community/boards",
        headers=create_headers,
        json=payload,
    )
    assert replay.status_code == 201
    assert replay.json() == created.json()

    updated_payload = {
        "name": "合成研究归档",
        "description": "历史主题保持可追溯，但不再接受新主题。",
        "sort_order": 25,
        "minimum_role": "admin",
        "is_read_only": True,
        "status": "inactive",
    }
    updated = client.patch(
        "/api/v1/admin/community/boards/synthetic_lab",
        headers={**admin_headers, "Idempotency-Key": "board-update-synthetic-0001"},
        json=updated_payload,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["board"]["is_read_only"] is True
    assert updated.json()["board"]["status"] == "inactive"

    public_catalog = client.get("/api/v1/community/boards")
    assert public_catalog.status_code == 200
    assert all(item["code"] != "synthetic_lab" for item in public_catalog.json()["items"])

    with client.app.state.database.session_factory() as db:
        board = db.scalar(select(CommunityBoard).where(CommunityBoard.code == "synthetic_lab"))
        actions = set(
            db.scalars(
                select(AuditLog.action).where(
                    AuditLog.action.in_(["community.board.create", "community.board.update"])
                )
            ).all()
        )
        assert board is not None and board.status.value == "inactive"
        assert actions == {"community.board.create", "community.board.update"}
