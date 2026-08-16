from __future__ import annotations

from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.community import (
    CommunityPost,
    CommunityPublicProfile,
    CommunitySearchOutbox,
    CommunitySearchSource,
    CommunityUserBlock,
    CommunityUserFollow,
    CommunityUserMute,
)
from password_detective.db.models.user import User, UserStatus


def _register_login(client, username: str) -> dict:
    payload = {
        "username": username,
        "email": f"{username}@example.com",
        "password": "SyntheticPass123!",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        user.email_verified_at = utc_now()
        db.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"login": username, "password": payload["password"]},
    )
    assert response.status_code == 200
    return response.json()


def _headers(tokens: dict, key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Idempotency-Key": f"{key}-synthetic-key",
    }


def test_public_profile_update_privacy_and_safe_projection(client):
    tokens = _register_login(client, "profile_owner")
    own = client.get("/api/v1/community/me/profile", headers=_headers(tokens, "unused"))
    assert own.status_code == 200
    assert own.json()["display_name"] == "profile_owner"

    updated = client.patch(
        "/api/v1/community/me/profile",
        json={
            "display_name": "合成展示名",
            "bio": "只展示公开的合成社区简介。",
            "regenerate_avatar": True,
        },
        headers=_headers(tokens, "community-profile-update-001"),
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "合成展示名"

    invalid_name = client.patch(
        "/api/v1/community/me/profile",
        json={"display_name": "   ", "bio": "", "regenerate_avatar": False},
        headers=_headers(tokens, "community-profile-invalid-name-001"),
    )
    assert invalid_name.status_code == 422

    privacy = client.patch(
        "/api/v1/community/me/privacy",
        json={
            "follower_visibility": "private",
            "following_visibility": "public",
            "message_policy": "following",
            "mention_policy": "nobody",
        },
        headers=_headers(tokens, "community-privacy-update-001"),
    )
    assert privacy.status_code == 200
    assert privacy.json()["mention_policy"] == "nobody"

    public = client.get("/api/v1/community/users/profile_owner")
    assert public.status_code == 200
    body = public.json()
    assert body["display_name"] == "合成展示名"
    assert body["registered_month"] == utc_now().strftime("%Y-%m")
    forbidden = {
        "email",
        "created_at",
        "updated_at",
        "last_activity_at",
        "ip_prefix",
        "device",
        "reputation_score",
        "growth_points",
        "message_policy",
        "mention_policy",
    }
    assert forbidden.isdisjoint(body)

    with client.app.state.database.session_factory() as db:
        profile = db.scalar(
            select(CommunityPublicProfile).where(
                CommunityPublicProfile.display_name == "合成展示名"
            )
        )
        assert profile is not None
        search_events = db.scalars(
            select(CommunitySearchOutbox).where(
                CommunitySearchOutbox.source_type == CommunitySearchSource.USER,
                CommunitySearchOutbox.source_id == profile.user_id,
            )
        ).all()
        assert any(event.document_version > 2_147_483_647 for event in search_events)
        actions = db.scalars(
            select(AuditLog).where(
                AuditLog.action.in_(["community.profile.updated", "community.privacy.updated"])
            )
        ).all()
        assert len(actions) == 2


def test_follow_is_unique_self_safe_and_private_lists_are_enforced(client):
    alice = _register_login(client, "follow_alice")
    bob = _register_login(client, "follow_bob")

    followed = client.put(
        "/api/v1/community/users/follow_bob/follow",
        headers=_headers(alice, "follow-bob-001"),
    )
    assert followed.status_code == 200, followed.text
    assert followed.json()["relationship"]["viewer_is_following"] is True
    replay = client.put(
        "/api/v1/community/users/follow_bob/follow",
        headers=_headers(alice, "follow-bob-001"),
    )
    assert replay.json() == followed.json()

    self_follow = client.put(
        "/api/v1/community/users/follow_alice/follow",
        headers=_headers(alice, "follow-self-001"),
    )
    assert self_follow.status_code == 422
    assert self_follow.json()["code"] == "community.self_relation_not_allowed"

    bob_profile = client.get(
        "/api/v1/community/users/follow_bob",
        headers={"Authorization": f"Bearer {alice['access_token']}"},
    )
    assert bob_profile.json()["stats"]["follower_count"] == 1
    assert bob_profile.json()["relationship"]["viewer_is_following"] is True

    client.patch(
        "/api/v1/community/me/privacy",
        json={
            "follower_visibility": "private",
            "following_visibility": "public",
            "message_policy": "following",
            "mention_policy": "everyone",
        },
        headers=_headers(bob, "bob-private-followers-001"),
    )
    private = client.get(
        "/api/v1/community/users/follow_bob/followers",
        headers={"Authorization": f"Bearer {alice['access_token']}"},
    )
    assert private.status_code == 403
    own = client.get(
        "/api/v1/community/users/follow_bob/followers",
        headers={"Authorization": f"Bearer {bob['access_token']}"},
    )
    assert own.status_code == 200
    assert own.json()["items"][0]["username"] == "follow_alice"

    with client.app.state.database.session_factory() as db:
        assert len(db.scalars(select(CommunityUserFollow)).all()) == 1


def test_block_removes_both_follow_edges_and_prevents_new_follow(client):
    alice = _register_login(client, "block_alice")
    bob = _register_login(client, "block_bob")
    client.put(
        "/api/v1/community/users/block_bob/follow",
        headers=_headers(alice, "block-follow-1"),
    )
    client.put(
        "/api/v1/community/users/block_alice/follow",
        headers=_headers(bob, "block-follow-2"),
    )
    blocked = client.put(
        "/api/v1/community/users/block_bob/block",
        headers=_headers(alice, "block-bob-001"),
    )
    assert blocked.status_code == 200
    state = blocked.json()["relationship"]
    assert state["viewer_is_blocking"] is True
    assert state["viewer_is_following"] is False
    assert state["follows_viewer"] is False

    denied = client.put(
        "/api/v1/community/users/block_alice/follow",
        headers=_headers(bob, "block-follow-denied"),
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "community.interaction_blocked"

    with client.app.state.database.session_factory() as db:
        assert db.scalars(select(CommunityUserFollow)).all() == []
        assert len(db.scalars(select(CommunityUserBlock)).all()) == 1


def test_mute_is_local_and_does_not_remove_follow_or_notify_target(client):
    alice = _register_login(client, "mute_alice")
    _register_login(client, "mute_bob")
    client.put(
        "/api/v1/community/users/mute_bob/follow",
        headers=_headers(alice, "mute-follow-001"),
    )
    muted = client.put(
        "/api/v1/community/users/mute_bob/mute",
        json={"expires_at": None},
        headers=_headers(alice, "mute-bob-001"),
    )
    assert muted.status_code == 200
    assert muted.json()["relationship"]["viewer_is_muting"] is True
    assert muted.json()["relationship"]["viewer_is_following"] is True

    with client.app.state.database.session_factory() as db:
        assert len(db.scalars(select(CommunityUserMute)).all()) == 1
        assert len(db.scalars(select(CommunityUserFollow)).all()) == 1


def test_disabled_users_are_not_public_or_followable(client):
    tokens = _register_login(client, "disabled_target")
    viewer = _register_login(client, "active_viewer")
    with client.app.state.database.session_factory() as db:
        target = db.scalar(select(User).where(User.username == "disabled_target"))
        assert target is not None
        target.status = UserStatus.DISABLED
        db.commit()
    assert client.get("/api/v1/community/users/disabled_target").status_code == 404
    denied = client.put(
        "/api/v1/community/users/disabled_target/follow",
        headers=_headers(viewer, "disabled-follow-001"),
    )
    assert denied.status_code == 404
    del tokens


def test_block_and_mute_filter_existing_community_content(client):
    author = _register_login(client, "filter_author")
    viewer = _register_login(client, "filter_viewer")
    created = client.post(
        "/api/v1/community/posts",
        json={
            "board_code": "general",
            "title": "合成关系过滤主题",
            "content": "这是仅用于验证拉黑和静音视图过滤的合成主题内容。",
            "rules_accepted": True,
        },
        headers=_headers(author, "filter-post-create-001"),
    )
    assert created.status_code == 201
    post_id = created.json()["id"]

    muted = client.put(
        "/api/v1/community/users/filter_author/mute",
        json={"expires_at": None},
        headers=_headers(viewer, "filter-mute-001"),
    )
    assert muted.status_code == 200
    visible_to_viewer = client.get(
        "/api/v1/community/posts",
        headers={"Authorization": f"Bearer {viewer['access_token']}"},
    )
    assert visible_to_viewer.status_code == 200
    assert visible_to_viewer.json()["items"] == []
    hidden_detail = client.get(
        f"/api/v1/community/posts/{post_id}",
        headers={"Authorization": f"Bearer {viewer['access_token']}"},
    )
    assert hidden_detail.status_code == 404

    unmuted = client.delete(
        "/api/v1/community/users/filter_author/mute",
        headers=_headers(viewer, "filter-unmute-001"),
    )
    assert unmuted.status_code == 200
    blocked = client.put(
        "/api/v1/community/users/filter_author/block",
        headers=_headers(viewer, "filter-block-001"),
    )
    assert blocked.status_code == 200
    blocked_listing = client.get(
        "/api/v1/community/posts",
        headers={"Authorization": f"Bearer {viewer['access_token']}"},
    )
    assert blocked_listing.status_code == 200
    assert blocked_listing.json()["items"] == []

    with client.app.state.database.session_factory() as db:
        assert db.get(CommunityPost, post_id) is not None
