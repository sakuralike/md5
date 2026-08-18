from __future__ import annotations

from urllib.parse import quote

from sqlalchemy.orm import Session

from password_detective.db.models.community import (
    CommunityBoard,
    CommunityBoardStatus,
    CommunityContentStatus,
    CommunityGroup,
    CommunityGroupStatus,
    CommunityGroupVisibility,
    CommunityPost,
    CommunityPublicProfile,
)
from password_detective.db.models.user import User, UserStatus
from password_detective.modules.community.schemas import CommunitySeoProjection

_DYNAMIC_CONTENT_INDEXING_ENABLED = False
_DESCRIPTION_LIMIT = 320


def post_seo_projection(db: Session, post: CommunityPost) -> CommunitySeoProjection:
    board = db.get(CommunityBoard, post.board_id)
    if (
        post.status != CommunityContentStatus.PUBLISHED
        or board is None
        or board.status != CommunityBoardStatus.ACTIVE
        or board.code != post.board_code
    ):
        return _not_eligible()
    if post.group_id is not None:
        group = db.get(CommunityGroup, post.group_id)
        if not _is_public_group(group):
            return _not_eligible()
    return _eligible(
        title=post.title,
        description=_compact_description(post.content),
        canonical_path=f"/community/posts/{quote(post.id, safe='-')}",
    )


def group_seo_projection(group: CommunityGroup) -> CommunitySeoProjection:
    if not _is_public_group(group):
        return _not_eligible()
    return _eligible(
        title=group.name,
        description=_compact_description(group.description),
        canonical_path=f"/community/groups/{quote(group.slug, safe='-')}",
    )


def profile_seo_projection(
    user: User, profile: CommunityPublicProfile
) -> CommunitySeoProjection:
    if user.status != UserStatus.ACTIVE:
        return _not_eligible()
    return _eligible(
        title=profile.display_name,
        description=_compact_description(profile.bio),
        canonical_path=f"/community/users/{quote(user.username, safe='-_')}",
    )


def _is_public_group(group: CommunityGroup | None) -> bool:
    return (
        group is not None
        and group.status == CommunityGroupStatus.ACTIVE
        and group.visibility == CommunityGroupVisibility.PUBLIC
    )


def _eligible(
    *, title: str, description: str, canonical_path: str
) -> CommunitySeoProjection:
    return CommunitySeoProjection(
        eligible=True,
        indexable=_DYNAMIC_CONTENT_INDEXING_ENABLED,
        title=title,
        description=description,
        keywords=[],
        canonical_path=canonical_path,
        og_image_url=None,
    )


def _not_eligible() -> CommunitySeoProjection:
    return CommunitySeoProjection(
        eligible=False,
        indexable=False,
        title=None,
        description=None,
        keywords=[],
        canonical_path=None,
        og_image_url=None,
    )


def _compact_description(value: str) -> str:
    compact = " ".join(value.split())
    return (
        compact
        if len(compact) <= _DESCRIPTION_LIMIT
        else f"{compact[: _DESCRIPTION_LIMIT - 3]}..."
    )