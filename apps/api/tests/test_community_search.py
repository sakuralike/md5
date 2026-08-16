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
    Path(__file__).parents[1] / "alembic" / "versions" / "20260816_0042_community_search.py"
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


def test_post_write_creates_deduplicated_search_outbox_event(client):
    from password_detective.db.models.community import (
        CommunitySearchOutbox,
        CommunitySearchOutboxStatus,
    )

    author = register_and_login(
        client,
        username="search_writer",
        email="search-writer@synthetic.example.com",
    )
    post = client.post(
        "/api/v1/community/posts",
        json={
            "board_code": "general",
            "title": "recover archive safely",
            "content": "Synthetic search indexing body.",
            "rules_accepted": True,
        },
        headers=request_headers(author, "search-outbox-post"),
    )
    assert post.status_code == 201, post.text
    post_id = post.json()["id"]

    with client.app.state.database.session_factory() as db:
        events = db.scalars(
            select(CommunitySearchOutbox).where(CommunitySearchOutbox.source_id == post_id)
        ).all()

    assert len(events) == 1
    assert events[0].status is CommunitySearchOutboxStatus.PENDING
    assert events[0].dedupe_key.endswith(":upsert")


def test_replay_and_rebuild_converge_on_the_same_document_set(client):
    from password_detective.db.models.community import (
        CommunitySearchDocument,
        CommunitySearchSource,
    )
    from password_detective.modules.community.search_index import (
        dispatch_pending_search_events,
        rebuild_search_index,
    )

    author = register_and_login(
        client,
        username="search_replayer",
        email="search-replayer@synthetic.example.com",
    )
    post = client.post(
        "/api/v1/community/posts",
        json={
            "board_code": "general",
            "title": "rebuild recovery guide",
            "content": "Synthetic content for deterministic reindex verification.",
            "rules_accepted": True,
        },
        headers=request_headers(author, "search-replay-post"),
    )
    assert post.status_code == 201, post.text

    with client.app.state.database.session_factory() as db:
        incremental = dispatch_pending_search_events(db)
        document = db.scalar(
            select(CommunitySearchDocument).where(
                CommunitySearchDocument.source_type == CommunitySearchSource.POST,
                CommunitySearchDocument.source_id == post.json()["id"],
            )
        )
        rebuilt = rebuild_search_index(db, apply=True)

    assert incremental.delivered >= 1
    assert document is not None
    assert rebuilt.mismatch_count == 0


def test_rebuild_dry_run_reports_projection_drift_and_persists_aggregate_run(client):
    from password_detective.db.models.community import (
        CommunitySearchRebuildRun,
        CommunitySearchRebuildStatus,
    )
    from password_detective.modules.community.search_index import rebuild_search_index

    author = register_and_login(
        client,
        username="search_drift_author",
        email="search-drift-author@synthetic.example.com",
    )
    created = client.post(
        "/api/v1/community/posts",
        json={
            "board_code": "general",
            "title": "drift recovery guide",
            "content": "Synthetic public content used to verify rebuild drift reporting.",
            "rules_accepted": True,
        },
        headers=request_headers(author, "search-drift-post"),
    )
    assert created.status_code == 201, created.text

    with client.app.state.database.session_factory() as db:
        dry_run = rebuild_search_index(db, apply=False, batch_size=1)
        run = db.get(CommunitySearchRebuildRun, dry_run.run_id)

    assert dry_run.operation == "dry-run"
    assert dry_run.mismatch_count >= 1
    assert run is not None
    assert run.status is CommunitySearchRebuildStatus.COMPLETED
    assert run.missing_count >= 1


def test_rebuild_apply_can_resume_a_bounded_running_run(client):
    from password_detective.db.models.community import (
        CommunitySearchRebuildRun,
        CommunitySearchRebuildStatus,
    )
    from password_detective.modules.community.search_index import rebuild_search_index

    author = register_and_login(
        client,
        username="search_resume_author",
        email="search-resume-author@synthetic.example.com",
    )
    for ordinal in range(2):
        created = client.post(
            "/api/v1/community/posts",
            json={
                "board_code": "general",
                "title": f"resume recovery guide {ordinal}",
                "content": "Synthetic public content used to verify bounded rebuild resume.",
                "rules_accepted": True,
            },
            headers=request_headers(author, f"search-resume-post-{ordinal}"),
        )
        assert created.status_code == 201, created.text

    with client.app.state.database.session_factory() as db:
        partial = rebuild_search_index(
            db,
            apply=True,
            batch_size=1,
            max_batches=1,
        )
        run = db.get(CommunitySearchRebuildRun, partial.run_id)
        assert partial.resume_cursor is not None
        assert run is not None
        assert run.status is CommunitySearchRebuildStatus.RUNNING

        completed = rebuild_search_index(
            db,
            apply=True,
            batch_size=1,
            resume_run_id=partial.run_id,
        )
        db.refresh(run)

    assert completed.resume_cursor is None
    assert completed.mismatch_count == 0
    assert run.status is CommunitySearchRebuildStatus.COMPLETED


def test_public_search_returns_dispatched_public_post_projection(client):
    from password_detective.modules.community.search_index import dispatch_pending_search_events

    author = register_and_login(
        client,
        username="search_public_author",
        email="search-public-author@synthetic.example.com",
    )
    created = client.post(
        "/api/v1/community/posts",
        json={
            "board_code": "general",
            "title": "public projection recovery guide",
            "content": "Synthetic public search document content.",
            "rules_accepted": True,
        },
        headers=request_headers(author, "search-public-projection-post"),
    )
    assert created.status_code == 201, created.text
    with client.app.state.database.session_factory() as db:
        assert dispatch_pending_search_events(db).delivered >= 1

    response = client.get(
        "/api/v1/community/search",
        params={"q": "projection", "types": "post"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["source_id"] == created.json()["id"]
