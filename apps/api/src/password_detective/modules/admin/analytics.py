from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityBoard,
    CommunityBoardStatus,
    CommunityComment,
    CommunityContentStatus,
    CommunityPost,
)
from password_detective.modules.admin.analytics_schemas import (
    AdminCommunityHeatmapResponse,
    AdminHeatmapBoard,
    AdminHeatmapDay,
)


def _count_band(count: int) -> str:
    if count == 0:
        return "0"
    if count < 10:
        return "少于 10"
    if count < 50:
        return "10-49"
    if count < 100:
        return "50-99"
    if count < 500:
        return "100-499"
    if count < 1_000:
        return "500-999"
    return f"{count // 1_000}k+"


def get_community_heatmap(
    db: Session,
    *,
    window_days: int = 30,
) -> AdminCommunityHeatmapResponse:
    end_day = utc_now().date()
    start_day = end_day - timedelta(days=window_days - 1)
    cutoff = start_day
    daily_activity: dict[date, int] = defaultdict(int)
    daily_boards: dict[date, set[str]] = defaultdict(set)
    board_activity: dict[str, int] = defaultdict(int)

    post_rows = db.execute(
        select(CommunityPost.created_at, CommunityPost.board_code)
        .join(CommunityBoard, CommunityBoard.id == CommunityPost.board_id)
        .where(
            CommunityPost.status == CommunityContentStatus.PUBLISHED,
            CommunityPost.deleted_by_author_at.is_(None),
            CommunityBoard.status == CommunityBoardStatus.ACTIVE,
            CommunityPost.created_at >= cutoff,
        )
    ).all()
    comment_rows = db.execute(
        select(CommunityComment.created_at, CommunityPost.board_code)
        .join(CommunityPost, CommunityPost.id == CommunityComment.post_id)
        .join(CommunityBoard, CommunityBoard.id == CommunityPost.board_id)
        .where(
            CommunityComment.status == CommunityContentStatus.PUBLISHED,
            CommunityComment.deleted_by_author_at.is_(None),
            CommunityPost.status == CommunityContentStatus.PUBLISHED,
            CommunityPost.deleted_by_author_at.is_(None),
            CommunityBoard.status == CommunityBoardStatus.ACTIVE,
            CommunityComment.created_at >= cutoff,
        )
    ).all()

    for created_at, board_code in [*post_rows, *comment_rows]:
        day = created_at.date()
        daily_activity[day] += 1
        daily_boards[day].add(board_code)
        board_activity[board_code] += 1

    days = [
        AdminHeatmapDay(
            day=day,
            weekday=day.weekday(),
            activity_count_band=_count_band(daily_activity[day]),
            active_boards_count_band=_count_band(len(daily_boards[day])),
        )
        for offset in range(window_days)
        for day in [start_day + timedelta(days=offset)]
    ]
    board_rows = db.execute(
        select(CommunityBoard.code, CommunityBoard.name)
        .where(CommunityBoard.status == CommunityBoardStatus.ACTIVE)
        .order_by(CommunityBoard.sort_order, CommunityBoard.code)
    ).all()
    boards = [
        AdminHeatmapBoard(
            board_code=code,
            board_name=name,
            activity_count_band=_count_band(board_activity[code]),
        )
        for code, name in board_rows
    ]
    return AdminCommunityHeatmapResponse(
        window_days=window_days,
        days=days,
        boards=boards,
        generated_at=utc_now(),
    )
