from __future__ import annotations

from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.community import CommunityBoard, CommunityGroup
from password_detective.db.models.user import User


def register_and_login(client, username: str) -> dict:
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


def headers(tokens: dict, key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Idempotency-Key": key,
    }


def create_group(client, tokens: dict, *, slug: str, visibility: str) -> dict:
    response = client.post(
        "/api/v1/community/groups",
        json={
            "slug": slug,
            "name": "合成恢复研究组",
            "description": "仅使用合成数据讨论授权恢复流程。",
            "visibility": visibility,
        },
        headers=headers(tokens, f"group-create-{slug}"),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_board_catalog_is_seeded_and_configurable(client):
    response = client.get("/api/v1/community/boards")
    assert response.status_code == 200
    assert response.json()["items"][0]["minimum_role"] == "user"
    with client.app.state.database.session_factory() as db:
        board = db.scalar(select(CommunityBoard).where(CommunityBoard.code == "general"))
        assert board is not None
        assert board.sort_order == 10


def test_public_group_join_is_idempotent_and_member_can_post(client):
    owner = register_and_login(client, "group_owner")
    member = register_and_login(client, "group_member")
    create_group(client, owner, slug="public-lab", visibility="public")

    joined = client.post(
        "/api/v1/community/groups/public-lab/join",
        headers=headers(member, "group-join-public-1"),
    )
    assert joined.status_code == 200
    assert joined.json()["group"]["viewer_membership_status"] == "active"
    replay = client.post(
        "/api/v1/community/groups/public-lab/join",
        headers=headers(member, "group-join-public-2"),
    )
    assert replay.status_code == 200
    assert replay.json()["group"]["member_count"] == 2

    activity = client.get(
        "/api/v1/community/activity?feed=groups",
        headers={"Authorization": f"Bearer {member['access_token']}"},
    )
    assert activity.status_code == 200
    joined_events = [
        item for item in activity.json()["items"] if item["kind"] == "group_joined"
    ]
    assert len(joined_events) == 1
    assert joined_events[0]["group_slug"] == "public-lab"

    post = client.post(
        "/api/v1/community/posts",
        json={
            "board_code": "general",
            "group_slug": "public-lab",
            "title": "合成群组主题的完整验证记录",
            "content": "这里记录合成数据环境下的授权验证步骤、完整性检查和回滚方案。",
            "rules_accepted": True,
        },
        headers=headers(member, "group-post-public-1"),
    )
    assert post.status_code == 201, post.text
    assert post.json()["group_slug"] == "public-lab"
    detail = client.get(f"/api/v1/community/posts/{post.json()['id']}")
    assert detail.status_code == 200


def test_approval_group_requires_owner_decision(client):
    owner = register_and_login(client, "approval_owner")
    member = register_and_login(client, "approval_member")
    create_group(client, owner, slug="approval-lab", visibility="approval")
    requested = client.post(
        "/api/v1/community/groups/approval-lab/join",
        headers=headers(member, "group-approval-join"),
    )
    assert requested.status_code == 200
    assert requested.json()["group"]["viewer_membership_status"] == "pending"

    applications = client.get(
        "/api/v1/community/notifications?kind=group_application",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert applications.status_code == 200
    assert len(applications.json()["items"]) == 1
    assert applications.json()["items"][0]["source_type"] == "group"
    assert applications.json()["items"][0]["actor"]["username"] == "approval_member"

    rejected_post = client.post(
        "/api/v1/community/posts",
        json={
            "board_code": "general",
            "group_slug": "approval-lab",
            "title": "未批准成员不能发布主题",
            "content": "这是一段满足长度要求的合成测试内容，用于验证群组成员权限边界。",
            "rules_accepted": True,
        },
        headers=headers(member, "group-approval-post-before"),
    )
    assert rejected_post.status_code == 403
    assert rejected_post.json()["code"] == "community.group_membership_required"

    approved = client.post(
        "/api/v1/community/groups/approval-lab/members/approval_member/decision",
        json={"decision": "approve", "role": "member"},
        headers=headers(owner, "group-approval-decision"),
    )
    assert approved.status_code == 200
    decisions = client.get(
        "/api/v1/community/notifications?kind=group_decision",
        headers={"Authorization": f"Bearer {member['access_token']}"},
    )
    assert decisions.status_code == 200
    assert len(decisions.json()["items"]) == 1
    assert "已通过" in decisions.json()["items"][0]["preview"]

    role_changed = client.patch(
        "/api/v1/community/groups/approval-lab/members/approval_member/role?role=moderator",
        headers=headers(owner, "group-approval-role"),
    )
    assert role_changed.status_code == 200
    role_notifications = client.get(
        "/api/v1/community/notifications?kind=group_role_change",
        headers={"Authorization": f"Bearer {member['access_token']}"},
    )
    assert role_notifications.status_code == 200
    assert len(role_notifications.json()["items"]) == 1
    assert "版主" in role_notifications.json()["items"][0]["preview"]

    detail = client.get(
        "/api/v1/community/groups/approval-lab",
        headers={"Authorization": f"Bearer {member['access_token']}"},
    )
    assert detail.status_code == 200
    assert any(item["username"] == "approval_member" for item in detail.json()["members"])

    activity = client.get(
        "/api/v1/community/activity?feed=groups",
        headers={"Authorization": f"Bearer {member['access_token']}"},
    )
    assert activity.status_code == 200
    assert any(
        item["kind"] == "group_joined" and item["group_slug"] == "approval-lab"
        for item in activity.json()["items"]
    )


def test_private_group_never_leaks_to_non_members(client):
    owner = register_and_login(client, "private_owner")
    outsider = register_and_login(client, "private_outsider")
    create_group(client, owner, slug="private-lab", visibility="private")
    post = client.post(
        "/api/v1/community/posts",
        json={
            "board_code": "security",
            "group_slug": "private-lab",
            "title": "私密群组合成安全讨论",
            "content": "这里仅包含合成数据和授权环境中的安全边界验证，不包含任何真实秘密。",
            "rules_accepted": True,
        },
        headers=headers(owner, "group-private-post"),
    )
    assert post.status_code == 201

    public_groups = client.get("/api/v1/community/groups")
    assert all(item["slug"] != "private-lab" for item in public_groups.json()["items"])
    outsider_groups = client.get(
        "/api/v1/community/groups",
        headers={"Authorization": f"Bearer {outsider['access_token']}"},
    )
    assert all(item["slug"] != "private-lab" for item in outsider_groups.json()["items"])
    assert client.get("/api/v1/community/groups/private-lab").status_code == 404
    assert client.get(f"/api/v1/community/posts/{post.json()['id']}").status_code == 404
    listing = client.get("/api/v1/community/posts")
    assert all(item["id"] != post.json()["id"] for item in listing.json()["items"])


def test_owner_transfer_is_required_before_leave(client):
    owner = register_and_login(client, "transfer_owner")
    member = register_and_login(client, "transfer_member")
    create_group(client, owner, slug="transfer-lab", visibility="public")
    client.post(
        "/api/v1/community/groups/transfer-lab/join",
        headers=headers(member, "transfer-member-join"),
    )
    blocked = client.delete(
        "/api/v1/community/groups/transfer-lab/membership",
        headers=headers(owner, "transfer-owner-leave-before"),
    )
    assert blocked.status_code == 409
    transferred = client.patch(
        "/api/v1/community/groups/transfer-lab/members/transfer_member/role?role=owner",
        headers=headers(owner, "transfer-owner-role"),
    )
    assert transferred.status_code == 200
    left = client.delete(
        "/api/v1/community/groups/transfer-lab/membership",
        headers=headers(owner, "transfer-owner-leave-after"),
    )
    assert left.status_code == 200
    with client.app.state.database.session_factory() as db:
        group = db.scalar(select(CommunityGroup).where(CommunityGroup.slug == "transfer-lab"))
        new_owner = db.scalar(select(User).where(User.username == "transfer_member"))
        assert group is not None and new_owner is not None
        assert group.owner_id == new_owner.id


def test_private_group_filters_profiles_notifications_and_global_moderators(client):
    owner = register_and_login(client, "sealed_owner")
    outsider = register_and_login(client, "sealed_outsider")
    create_group(client, owner, slug="sealed-lab", visibility="private")
    post = client.post(
        "/api/v1/community/posts",
        json={
            "board_code": "security",
            "group_slug": "sealed-lab",
            "title": "私密群组提及与主页隔离验证",
            "content": "仅用于合成数据边界验证，@sealed_outsider 不应收到不可访问内容的通知。",
            "rules_accepted": True,
        },
        headers=headers(owner, "group-private-isolation-post"),
    )
    assert post.status_code == 201, post.text

    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}
    filtered = client.get(
        "/api/v1/community/posts",
        params={"group_slug": "sealed-lab"},
        headers=outsider_headers,
    )
    assert filtered.status_code == 404
    notifications = client.get("/api/v1/community/notifications", headers=outsider_headers)
    assert notifications.status_code == 200
    assert notifications.json()["items"] == []
    profile = client.get(
        "/api/v1/community/users/sealed_owner",
        headers=outsider_headers,
    )
    assert profile.status_code == 200
    assert all(item["id"] != post.json()["id"] for item in profile.json()["recent_posts"])

    with client.app.state.database.session_factory() as db:
        outsider_user = db.scalar(select(User).where(User.username == "sealed_outsider"))
        assert outsider_user is not None
        outsider_user.role = "moderator"
        db.commit()
    relogin = client.post(
        "/api/v1/auth/login",
        json={"login": "sealed_outsider", "password": "SyntheticPass123!"},
    )
    moderator_headers = {"Authorization": f"Bearer {relogin.json()['access_token']}"}
    assert (
        client.get("/api/v1/community/groups/sealed-lab", headers=moderator_headers).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/community/posts/{post.json()['id']}", headers=moderator_headers
        ).status_code
        == 404
    )
    governed = client.patch(
        "/api/v1/community/groups/sealed-lab",
        json={
            "name": "合成私密治理实验组",
            "description": "仅验证全站治理写入与普通读取边界。",
            "visibility": "private",
            "status": "active",
        },
        headers={**moderator_headers, "Idempotency-Key": "sealed-global-governance-update"},
    )
    assert governed.status_code == 200, governed.text
    assert governed.json()["members"] == []
    assert (
        client.get("/api/v1/community/groups/sealed-lab", headers=moderator_headers).status_code
        == 404
    )


def test_private_group_owner_can_invite_member(client):
    owner = register_and_login(client, "invite_owner")
    invited = register_and_login(client, "invite_member")
    create_group(client, owner, slug="invite-only-lab", visibility="private")
    response = client.post(
        "/api/v1/community/groups/invite-only-lab/members/invite_member/decision",
        json={"decision": "invite", "role": "member"},
        headers=headers(owner, "group-private-invite-member"),
    )
    assert response.status_code == 200, response.text
    invitation = client.get(
        "/api/v1/community/notifications?kind=group_decision",
        headers={"Authorization": f"Bearer {invited['access_token']}"},
    )
    assert invitation.status_code == 200
    assert len(invitation.json()["items"]) == 1
    assert "邀请加入" in invitation.json()["items"][0]["preview"]

    detail = client.get(
        "/api/v1/community/groups/invite-only-lab",
        headers={"Authorization": f"Bearer {invited['access_token']}"},
    )
    assert detail.status_code == 200
    assert detail.json()["viewer_membership_status"] == "active"
