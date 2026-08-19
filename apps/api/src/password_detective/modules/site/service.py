from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from password_detective.core.maintenance import load_maintenance_runtime_config
from password_detective.core.time import utc_now
from password_detective.db.models.archive_fingerprint import (
    ArchiveFingerprint,
    FingerprintAlgorithm,
)
from password_detective.db.models.community import (
    CommunityBoard,
    CommunityComment,
    CommunityContentStatus,
    CommunityPost,
)
from password_detective.db.models.hash_detail import (
    HashComment,
    HashLike,
    HashVote,
    HashVoteOutcome,
)
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.submission import Submission
from password_detective.db.models.system_setting import SystemSetting
from password_detective.db.models.user import User, UserStatus
from password_detective.modules.admin.seo_settings import default_seo_settings
from password_detective.modules.admin.setting_schemas import (
    SeoSettings,
    SiteNavigationItem,
    default_site_navigation,
)
from password_detective.modules.registration.service import get_registration_policy
from password_detective.modules.site.schemas import (
    AlgorithmDistributionItem,
    AlgorithmDistributionResponse,
    CommunityActivityTrendBoard,
    CommunityActivityTrendBucket,
    CommunityActivityTrendResponse,
    HomeDiscoveryResponse,
    HotHashSummary,
    PublicLegalConfig,
    PublicMaintenanceConfig,
    PublicRegistrationConfig,
    PublicSeoConfig,
    PublicSiteConfigResponse,
    UserRankingSummary,
)


def _setting_value(db: Session, key: str, default: object) -> object:
    record = db.get(SystemSetting, key)
    if record is None:
        return default
    return record.value_json.get("value", default)


def _public_plain_text(db: Session, key: str) -> str:
    raw_value = _setting_value(db, key, "")
    if not isinstance(raw_value, str):
        return ""
    normalized = raw_value.strip()
    if "<" in normalized or ">" in normalized:
        return ""
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        return ""
    return normalized


def _public_seo_config(db: Session) -> PublicSeoConfig:
    defaults = default_seo_settings()
    raw_settings = _setting_value(
        db,
        "seo_settings",
        defaults.model_dump(mode="json"),
    )
    try:
        settings = SeoSettings.model_validate(raw_settings)
    except (TypeError, ValueError):
        settings = defaults

    if not settings.enabled:
        settings = SeoSettings(
            enabled=False,
            indexing_enabled=False,
            title_separator=settings.title_separator,
            open_graph_enabled=False,
            sitemap_enabled=settings.sitemap_enabled,
        )

    return PublicSeoConfig.model_validate(
        settings.model_dump(mode="json", exclude={"sitemap_enabled"})
    )


def get_public_site_config(
    db: Session,
    *,
    maintenance_force_disabled: bool = False,
) -> PublicSiteConfigResponse:
    raw_name = _setting_value(db, "site_name", "密码侦探社")
    raw_logo = _setting_value(db, "site_logo_url", "")
    raw_navigation = _setting_value(
        db, "site_navigation", [item.model_dump(mode="json") for item in default_site_navigation()]
    )
    try:
        navigation = [SiteNavigationItem.model_validate(item) for item in raw_navigation]
    except (TypeError, ValueError):
        navigation = default_site_navigation()
    maintenance = load_maintenance_runtime_config(db)
    return PublicSiteConfigResponse(
        site_name=raw_name if isinstance(raw_name, str) and raw_name.strip() else "密码侦探社",
        site_logo_url=raw_logo if isinstance(raw_logo, str) else "",
        navigation=[item for item in navigation if item.enabled],
        seo=_public_seo_config(db),
        legal=PublicLegalConfig(
            icp_record=_public_plain_text(db, "icp_record"),
            public_security_record=_public_plain_text(db, "public_security_record"),
            copyright_text=_public_plain_text(db, "copyright_text"),
            public_contact_email=_public_plain_text(db, "public_contact_email"),
        ),
        maintenance=PublicMaintenanceConfig(
            active=maintenance.enabled and not maintenance_force_disabled,
            message=maintenance.message,
        ),
        registration=PublicRegistrationConfig(mode=get_registration_policy(db).mode),
    )


def get_home_discovery(db: Session, *, limit: int = 5) -> HomeDiscoveryResponse:
    like_count = func.count(func.distinct(HashLike.id))
    comment_count = func.count(func.distinct(HashComment.id))
    useful_vote_count = func.count(
        func.distinct(case((HashVote.outcome == HashVoteOutcome.USEFUL, HashVote.id)))
    )
    hot_rows = db.execute(
        select(
            ArchiveFingerprint.algorithm,
            ArchiveFingerprint.digest,
            like_count.label("like_count"),
            comment_count.label("comment_count"),
            useful_vote_count.label("useful_vote_count"),
        )
        .outerjoin(HashLike, HashLike.fingerprint_id == ArchiveFingerprint.id)
        .outerjoin(HashComment, HashComment.fingerprint_id == ArchiveFingerprint.id)
        .outerjoin(HashVote, HashVote.fingerprint_id == ArchiveFingerprint.id)
        .group_by(ArchiveFingerprint.id, ArchiveFingerprint.algorithm, ArchiveFingerprint.digest)
        .having(like_count + comment_count + useful_vote_count > 0)
        .order_by(
            (like_count * 3 + comment_count * 2 + useful_vote_count * 2).desc(),
            ArchiveFingerprint.created_at.desc(),
        )
        .limit(limit)
    ).all()
    hot_hashes = [
        HotHashSummary(
            algorithm=row.algorithm,
            digest=row.digest,
            like_count=row.like_count,
            comment_count=row.comment_count,
            useful_vote_count=row.useful_vote_count,
            heat_score=row.like_count * 3 + row.comment_count * 2 + row.useful_vote_count * 2,
        )
        for row in hot_rows
    ]

    contribution_count = func.count(Submission.id)
    contribution_rows = db.execute(
        select(User.id, User.username, contribution_count.label("score"))
        .join(Submission, Submission.user_id == User.id)
        .where(User.status == UserStatus.ACTIVE)
        .group_by(User.id, User.username)
        .order_by(contribution_count.desc(), User.created_at.asc(), User.id.asc())
        .limit(limit)
    ).all()

    points_score = func.coalesce(func.sum(PointsLedger.amount), 0)
    points_rows = db.execute(
        select(User.id, User.username, points_score.label("score"))
        .join(PointsLedger, PointsLedger.user_id == User.id)
        .where(User.status == UserStatus.ACTIVE, PointsLedger.status == PointsLedgerStatus.POSTED)
        .group_by(User.id, User.username)
        .having(points_score > 0)
        .order_by(points_score.desc(), User.created_at.asc(), User.id.asc())
        .limit(limit)
    ).all()

    return HomeDiscoveryResponse(
        hot_hashes=hot_hashes,
        contribution_leaders=[
            UserRankingSummary(rank=index, uid=row.id, username=row.username, score=row.score)
            for index, row in enumerate(contribution_rows, start=1)
        ],
        points_leaders=[
            UserRankingSummary(rank=index, uid=row.id, username=row.username, score=row.score)
            for index, row in enumerate(points_rows, start=1)
        ],
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


def get_algorithm_distribution(db: Session) -> AlgorithmDistributionResponse:
    rows = db.execute(
        select(
            ArchiveFingerprint.algorithm,
            func.count(func.distinct(ArchiveFingerprint.id)).label("fingerprint_count"),
        )
        .join(
            PasswordCandidate,
            PasswordCandidate.archive_id == ArchiveFingerprint.archive_id,
        )
        .where(PasswordCandidate.status == CandidateStatus.VERIFIED)
        .group_by(ArchiveFingerprint.algorithm)
    ).all()
    counts = {row.algorithm: int(row.fingerprint_count) for row in rows}
    total = sum(counts.values())
    algorithms = [
        FingerprintAlgorithm.MD5,
        FingerprintAlgorithm.SHA1,
        FingerprintAlgorithm.SHA256,
        FingerprintAlgorithm.SHA512,
    ]

    def privacy_percentage(count: int) -> float:
        if total == 0 or count == 0:
            return 0.0
        return float(min(100, round((count * 100 / total) / 5) * 5))

    return AlgorithmDistributionResponse(
        total_count_band=_count_band(total),
        items=[
            AlgorithmDistributionItem(
                algorithm=algorithm,
                count_band=_count_band(counts.get(algorithm, 0)),
                percentage=privacy_percentage(counts.get(algorithm, 0)),
            )
            for algorithm in algorithms
        ],
        generated_at=utc_now(),
    )


def get_community_activity_trend(
    db: Session,
    *,
    window_days: int = 30,
) -> CommunityActivityTrendResponse:
    end_day = utc_now().date()
    start_day = end_day - timedelta(days=window_days - 1)
    cutoff = start_day

    post_rows = db.execute(
        select(CommunityPost.created_at, CommunityPost.board_code)
        .join(CommunityBoard, CommunityBoard.id == CommunityPost.board_id)
        .where(
            CommunityPost.status == CommunityContentStatus.PUBLISHED,
            CommunityPost.deleted_by_author_at.is_(None),
            CommunityBoard.status == "active",
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
            CommunityBoard.status == "active",
            CommunityComment.created_at >= cutoff,
        )
    ).all()

    daily_posts: dict[date, int] = defaultdict(int)
    daily_comments: dict[date, int] = defaultdict(int)
    daily_boards: dict[date, set[str]] = defaultdict(set)
    board_posts: dict[str, int] = defaultdict(int)
    board_comments: dict[str, int] = defaultdict(int)
    for created_at, board_code in post_rows:
        day = created_at.date()
        daily_posts[day] += 1
        daily_boards[day].add(board_code)
        board_posts[board_code] += 1
    for created_at, board_code in comment_rows:
        day = created_at.date()
        daily_comments[day] += 1
        daily_boards[day].add(board_code)
        board_comments[board_code] += 1

    board_rows = db.execute(
        select(CommunityBoard.code, CommunityBoard.name)
        .where(CommunityBoard.status == "active")
        .order_by(CommunityBoard.sort_order, CommunityBoard.code)
    ).all()
    buckets = [
        CommunityActivityTrendBucket(
            day=start_day + timedelta(days=offset),
            posts_count_band=_count_band(daily_posts[start_day + timedelta(days=offset)]),
            comments_count_band=_count_band(daily_comments[start_day + timedelta(days=offset)]),
            activity_count_band=_count_band(
                daily_posts[start_day + timedelta(days=offset)]
                + daily_comments[start_day + timedelta(days=offset)]
            ),
            active_boards_count_band=_count_band(
                len(daily_boards[start_day + timedelta(days=offset)])
            ),
        )
        for offset in range(window_days)
    ]
    boards = [
        CommunityActivityTrendBoard(
            board_code=code,
            board_name=name,
            posts_count_band=_count_band(board_posts[code]),
            comments_count_band=_count_band(board_comments[code]),
            activity_count_band=_count_band(board_posts[code] + board_comments[code]),
        )
        for code, name in board_rows
    ]
    return CommunityActivityTrendResponse(
        window_days=window_days,
        buckets=buckets,
        boards=boards,
        generated_at=utc_now(),
    )
