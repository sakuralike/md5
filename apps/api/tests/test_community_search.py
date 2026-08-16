from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.user import User


def register_and_login(
    client,
    *,
    username: str,
    email: str,
) -> dict[str, str]:
    password = "SyntheticSearchPass123!"
    registration = {
        "username": username,
        "email": email,
        "password": password,
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        user.email_verified_at = utc_now()
        db.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"login": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def request_headers(tokens: Mapping[str, str], idempotency_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Idempotency-Key": idempotency_key,
    }


def create_private_group_post(
    client,
    owner_tokens: Mapping[str, str],
    *,
    title: str,
) -> dict[str, str]:
    group = client.post(
        "/api/v1/community/groups",
        json={
            "slug": "search-private-lab",
            "name": "合成私密搜索边界组",
            "description": "仅用于验证公开搜索不会披露私密群组内容。",
            "visibility": "private",
        },
        headers=request_headers(owner_tokens, "search-private-group-create"),
    )
    assert group.status_code == 201, group.text
    post = client.post(
        "/api/v1/community/posts",
        json={
            "board_code": "general",
            "group_slug": "search-private-lab",
            "title": title,
            "content": "这是一段仅在合成私密群组内可见的恢复流程讨论，不得由公开搜索披露。",
            "rules_accepted": True,
        },
        headers=request_headers(owner_tokens, "search-private-post-create"),
    )
    assert post.status_code == 201, post.text
    return post.json()


def test_public_search_rejects_short_or_control_character_queries(client):
    assert client.get("/api/v1/community/search", params={"q": "a"}).status_code == 422
    assert client.get("/api/v1/community/search", params={"q": "ab\x00cd"}).status_code == 422


def test_public_search_returns_only_requested_public_result_types(client):
    response = client.get(
        "/api/v1/community/search",
        params=[("q", "recovery"), ("types", "post"), ("types", "board")],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["query"] == "recovery"
    assert {item["type"] for item in body["items"]} <= {"post", "board"}
    assert body["provider"]["mode"] in {"ngram", "prefix_fallback", "test"}


def test_private_blocked_or_muted_sources_never_appear_in_search(client):
    owner = register_and_login(
        client,
        username="search_owner",
        email="search-owner@synthetic.example.com",
    )
    outsider = register_and_login(
        client,
        username="search_outsider",
        email="search-outsider@synthetic.example.com",
    )
    private_post = create_private_group_post(
        client,
        owner,
        title="sealed recovery guide",
    )
    blocked = client.put(
        "/api/v1/community/users/search_owner/block",
        headers=request_headers(outsider, "search-block-owner"),
    )
    assert blocked.status_code == 200, blocked.text

    result = client.get(
        "/api/v1/community/search",
        params={"q": "recovery"},
        headers=request_headers(outsider, "search-private-query"),
    )
    assert result.status_code == 200, result.text
    serialized = str(result.json())
    assert private_post["id"] not in serialized
    assert "sealed recovery guide" not in serialized

MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "20260816_0042_community_search.py"
)


def test_search_migration_round_trip_declares_required_tables(monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("migration_20260816_0042", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    created_tables: list[str] = []
    dropped_tables: list[str] = []
    connection = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(
        migration.op,
        "create_table",
        lambda table_name, *columns: created_tables.append(table_name),
    )
    monkeypatch.setattr(migration.op, "create_index", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        migration.op,
        "drop_table",
        lambda table_name: dropped_tables.append(table_name),
    )

    assert migration.revision == "20260816_0042"
    assert migration.down_revision == "20260815_0041"
    migration.upgrade()
    assert set(created_tables) == {
        "community_search_documents",
        "community_search_outbox",
        "community_search_rebuild_runs",
    }
    migration.downgrade()
    assert set(dropped_tables) == set(created_tables)


def test_normalize_search_query_folds_whitespace_and_rejects_invalid_input():
    import pytest

    from password_detective.core.errors import AppError
    from password_detective.modules.community.search_service import normalize_search_query

    assert normalize_search_query("  recover\n\tguide  ") == "recover guide"

    with pytest.raises(AppError) as error:
        normalize_search_query("x")
    assert error.value.code == "community.search_invalid_query"

    with pytest.raises(AppError) as error:
        normalize_search_query("recovery\x00guide")
    assert error.value.code == "community.search_invalid_query"


def test_sqlite_search_provider_reports_test_mode(client):
    from password_detective.modules.community.search_provider import SQLiteCommunitySearchProvider

    with client.app.state.database.session_factory() as db:
        state = SQLiteCommunitySearchProvider(max_prefix_candidates=50).preflight(db)

    assert state.mode == "test"
    assert state.degraded is False
