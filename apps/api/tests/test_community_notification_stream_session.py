from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.time import utc_now
from password_detective.db.models.user import User
from password_detective.modules.community import router as community_router


def _register_and_login(client) -> dict[str, object]:
    payload = {
        "username": "stream_session_user",
        "email": "stream-session-user@example.com",
        "password": "SyntheticPass123!",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == payload["username"]))
        assert user is not None
        user.email_verified_at = utc_now()
        db.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"login": payload["username"], "password": payload["password"]},
    )
    assert response.status_code == 200
    return response.json()


def test_notification_stream_releases_auth_session_before_streaming(client, monkeypatch) -> None:
    tokens = _register_and_login(client)
    database = client.app.state.database
    original_session = database.session
    state = {"active_request_sessions": 0}

    def tracked_session() -> Iterator[Session]:
        state["active_request_sessions"] += 1
        try:
            yield from original_session()
        finally:
            state["active_request_sessions"] -= 1

    async def finite_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
        del args, kwargs
        yield f"data: active={state['active_request_sessions']}\n\n"

    monkeypatch.setattr(database, "session", tracked_session)
    monkeypatch.setattr(community_router, "_notification_event_stream", finite_stream)

    response = client.get(
        "/api/v1/community/notifications/stream",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200
    assert "data: active=0" in response.text
    assert state["active_request_sessions"] == 0
