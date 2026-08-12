from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from password_detective.db.models.community import (
    CommunityComment,
    CommunityContentStatus,
    CommunityPost,
)


@dataclass(frozen=True)
class ReplyCountProjectionChange:
    post_id: str
    stored_count: int
    expected_count: int

    def as_dict(self) -> dict[str, int | str]:
        return {
            "post_id": self.post_id,
            "stored_count": self.stored_count,
            "expected_count": self.expected_count,
        }


@dataclass(frozen=True)
class ReplyCountProjectionSummary:
    scanned_posts: int
    inconsistent_posts: int
    updated_posts: int
    changes: tuple[ReplyCountProjectionChange, ...]

    def as_dict(self) -> dict[str, int | list[dict[str, int | str]]]:
        return {
            "scanned_posts": self.scanned_posts,
            "inconsistent_posts": self.inconsistent_posts,
            "updated_posts": self.updated_posts,
            "changes": [change.as_dict() for change in self.changes],
        }


def rebuild_reply_count_projection(
    db: Session,
    *,
    apply: bool,
) -> ReplyCountProjectionSummary:
    public_reply_count = func.count(CommunityComment.id)
    rows = db.execute(
        select(
            CommunityPost.id,
            CommunityPost.reply_count,
            public_reply_count.label("expected_count"),
        )
        .outerjoin(
            CommunityComment,
            and_(
                CommunityComment.post_id == CommunityPost.id,
                CommunityComment.status == CommunityContentStatus.PUBLISHED,
                CommunityComment.deleted_by_author_at.is_(None),
            ),
        )
        .group_by(CommunityPost.id, CommunityPost.reply_count)
        .order_by(CommunityPost.id.asc())
    ).all()
    changes = tuple(
        ReplyCountProjectionChange(
            post_id=post_id,
            stored_count=stored_count,
            expected_count=expected_count,
        )
        for post_id, stored_count, expected_count in rows
        if stored_count != expected_count
    )
    if apply:
        for change in changes:
            db.execute(
                update(CommunityPost)
                .where(CommunityPost.id == change.post_id)
                .values(reply_count=change.expected_count)
            )
    return ReplyCountProjectionSummary(
        scanned_posts=len(rows),
        inconsistent_posts=len(changes),
        updated_posts=len(changes) if apply else 0,
        changes=changes,
    )
