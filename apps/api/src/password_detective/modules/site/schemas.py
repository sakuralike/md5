from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from password_detective.db.models.archive_fingerprint import FingerprintAlgorithm
from password_detective.modules.admin.setting_schemas import SiteNavigationItem


class PublicSeoConfig(BaseModel):
    enabled: bool
    indexing_enabled: bool
    home_title: str
    keywords: list[str]
    description: str
    title_separator: Literal["-", "_", "|", "·"]
    default_image_url: str
    open_graph_enabled: bool


class PublicLegalConfig(BaseModel):
    icp_record: str
    public_security_record: str
    copyright_text: str
    public_contact_email: str


class PublicMaintenanceConfig(BaseModel):
    active: bool
    message: str


class PublicRegistrationConfig(BaseModel):
    mode: Literal["open", "invite_only"]


class PublicSiteConfigResponse(BaseModel):
    site_name: str
    site_logo_url: str
    navigation: list[SiteNavigationItem]
    seo: PublicSeoConfig
    legal: PublicLegalConfig
    maintenance: PublicMaintenanceConfig
    registration: PublicRegistrationConfig


class HotHashSummary(BaseModel):
    algorithm: FingerprintAlgorithm
    digest: str
    like_count: int = 0
    comment_count: int = 0
    useful_vote_count: int = 0
    heat_score: int = 0


class UserRankingSummary(BaseModel):
    rank: int = Field(ge=1, le=5)
    uid: str
    username: str
    score: int


class HomeDiscoveryResponse(BaseModel):
    hot_hashes: list[HotHashSummary]
    contribution_leaders: list[UserRankingSummary]
    points_leaders: list[UserRankingSummary]


class AlgorithmDistributionItem(BaseModel):
    algorithm: FingerprintAlgorithm
    count_band: str
    percentage: float = Field(ge=0, le=100)


class AlgorithmDistributionResponse(BaseModel):
    total_count_band: str
    items: list[AlgorithmDistributionItem]
    generated_at: datetime


class CommunityActivityTrendBucket(BaseModel):
    day: date
    posts_count_band: str
    comments_count_band: str
    activity_count_band: str
    active_boards_count_band: str


class CommunityActivityTrendBoard(BaseModel):
    board_code: str
    board_name: str
    posts_count_band: str
    comments_count_band: str
    activity_count_band: str


class CommunityActivityTrendResponse(BaseModel):
    window_days: int = Field(ge=7, le=90)
    buckets: list[CommunityActivityTrendBucket]
    boards: list[CommunityActivityTrendBoard]
    generated_at: datetime
