from __future__ import annotations

from urllib.parse import quote, urlsplit

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
        title=_safe_text(post.seo_title) or post.title,
        description=_safe_text(post.seo_description) or _compact_description(post.content),
        keywords=_safe_keywords(post.seo_keywords),
        canonical_path=_safe_canonical(post.seo_canonical_path)
        or f"/community/posts/{quote(post.id, safe='-')}",
        og_image_url=_safe_og_image(post.og_image_url),
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
    *,
    title: str,
    description: str,
    canonical_path: str,
    keywords: list[str] | None = None,
    og_image_url: str | None = None,
) -> CommunitySeoProjection:
    return CommunitySeoProjection(
        eligible=True,
        indexable=_DYNAMIC_CONTENT_INDEXING_ENABLED,
        title=title,
        description=description,
        keywords=keywords or [],
        canonical_path=canonical_path,
        og_image_url=og_image_url,
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

def _safe_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if not normalized or any(ord(char) < 32 for char in normalized):
        return None
    if any(token in normalized for token in ("<", ">", "{{", "}}")):
        return None
    return normalized


def _safe_keywords(value: list[str] | None) -> list[str]:
    if not value:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _safe_text(item)
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result[:20]


def _safe_canonical(value: str | None) -> str | None:
    if value is None or not value.startswith("/") or value.startswith("//"):
        return None
    if any(char in value for char in ("?", "#", "\\", "\x00")):
        return None
    if any(ord(char) < 32 for char in value):
        return None
    return value


def _safe_og_image(value: str | None) -> str | None:
    if value is None or any(char in value for char in ("\x00", "\r", "\n")):
        return None
    if value.startswith("/") and not value.startswith("//"):
        return value
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return None
    return value
