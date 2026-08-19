from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class AdminHeatmapDay(BaseModel):
    day: date
    weekday: int = Field(ge=0, le=6)
    activity_count_band: str
    active_boards_count_band: str


class AdminHeatmapBoard(BaseModel):
    board_code: str
    board_name: str
    activity_count_band: str


class AdminCommunityHeatmapResponse(BaseModel):
    window_days: int = Field(ge=7, le=90)
    days: list[AdminHeatmapDay]
    boards: list[AdminHeatmapBoard]
    generated_at: datetime
