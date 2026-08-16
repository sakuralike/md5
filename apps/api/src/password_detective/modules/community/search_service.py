from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.db.models.community import (
    CommunityPost,
    CommunitySearchDocument,
    CommunitySearchSource,
)
from password_detective.modules.community.schemas import (
    CommunitySearchProviderState as CommunitySearchProviderStateResponse,
)
from password_detective.modules.community.schemas import (
    CommunitySearchResponse,
    CommunitySearchResultItem,
)
from password_detective.modules.community.search_provider import (
    CommunitySearchProvider,
    CommunitySearchProviderState,
    provider_for_session,
)

_MIN_QUERY_LENGTH = 2
_MAX_QUERY_LENGTH = 64


@dataclass(frozen=True)
class CommunitySearchQuery:
    value: str
    source_types: tuple[CommunitySearchSource, ...] = ()


class CommunitySearchService:
    def __init__(self, db: Session, *, provider: CommunitySearchProvider | None = None) -> None:
        self.db = db
        self.provider = provider or provider_for_session(db)

    def provider_state(self) -> CommunitySearchProviderState:
        return self.provider.preflight(self.db)

    def find_documents(
        self,
        search: CommunitySearchQuery,
        *,
        candidate_limit: int,
    ) -> list[CommunitySearchDocument]:
        return self.provider.search_documents(
            self.db,
            query=search.value,
            source_types=search.source_types,
            candidate_limit=candidate_limit,
        )


def normalize_search_query(value: str) -> str:
    if "\x00" in value:
        raise _invalid_query_error()

    without_non_whitespace_controls = "".join(
        character
        for character in value
        if not (unicodedata.category(character).startswith("C") and not character.isspace())
    )
    normalized = " ".join(without_non_whitespace_controls.split())
    if not _MIN_QUERY_LENGTH <= len(normalized) <= _MAX_QUERY_LENGTH:
        raise _invalid_query_error()
    return normalized


def create_search_query(
    value: str,
    *,
    source_types: tuple[CommunitySearchSource, ...] = (),
) -> CommunitySearchQuery:
    return CommunitySearchQuery(value=normalize_search_query(value), source_types=source_types)


def _invalid_query_error() -> AppError:
    return AppError(
        "community.search_invalid_query",
        "搜索关键词须为 2 至 64 个字符，且不能包含空字节",
        status_code=422,
    )


def search_community(
    db: Session,
    *,
    query: str,
    source_types: tuple[CommunitySearchSource, ...],
    page: int,
    page_size: int,
    principal: object | None,
) -> CommunitySearchResponse:
    from password_detective.modules.community.service import _hidden_author_ids

    viewer_id = getattr(getattr(principal, "user", None), "id", None)
    search = create_search_query(query, source_types=source_types)
    service = CommunitySearchService(db)
    provider = service.provider_state()
    hidden_author_ids = _hidden_author_ids(db, viewer_id)
    candidates = service.find_documents(search, candidate_limit=200)
    authorized = [
        item
        for item in candidates
        if _document_is_visible_to_viewer(
            db,
            document=item,
            viewer_id=viewer_id,
            hidden_author_ids=hidden_author_ids,
        )
    ]
    start = (page - 1) * page_size
    return CommunitySearchResponse(
        query=search.value,
        items=[_result_item(document) for document in authorized[start : start + page_size]],
        page=page,
        page_size=page_size,
        total=len(authorized),
        provider=CommunitySearchProviderStateResponse(
            mode=provider.mode,
            degraded=provider.degraded,
        ),
    )


def _document_is_visible_to_viewer(
    db: Session,
    *,
    document: CommunitySearchDocument,
    viewer_id: str | None,
    hidden_author_ids: set[str],
) -> bool:
    from password_detective.db.models.community import (
        CommunityBoard,
        CommunityBoardStatus,
        CommunityContentStatus,
        CommunityGroup,
        CommunityGroupStatus,
        CommunityGroupVisibility,
    )
    from password_detective.db.models.user import User, UserStatus
    from password_detective.modules.community.group_service import post_visibility_condition

    if document.author_id is not None and document.author_id in hidden_author_ids:
        return False
    if document.source_type is CommunitySearchSource.POST:
        post = db.scalar(
            select(CommunityPost).where(
                CommunityPost.id == document.source_id,
                CommunityPost.status == CommunityContentStatus.PUBLISHED,
                CommunityPost.deleted_by_author_at.is_(None),
                post_visibility_condition(viewer_id),
            )
        )
        if post is None:
            return False
        author = db.get(User, post.author_id)
        board = db.get(CommunityBoard, post.board_id)
        return (
            author is not None
            and author.status is UserStatus.ACTIVE
            and board is not None
            and board.status is CommunityBoardStatus.ACTIVE
        )
    if document.source_type is CommunitySearchSource.USER:
        user = db.get(User, document.source_id)
        return user is not None and user.status is UserStatus.ACTIVE
    if document.source_type is CommunitySearchSource.BOARD:
        board = db.get(CommunityBoard, document.source_id)
        return board is not None and board.status is CommunityBoardStatus.ACTIVE
    group = db.get(CommunityGroup, document.source_id)
    return (
        group is not None
        and group.status is CommunityGroupStatus.ACTIVE
        and group.visibility is CommunityGroupVisibility.PUBLIC
    )


def _result_item(document: CommunitySearchDocument) -> CommunitySearchResultItem:
    preview = " ".join(document.body.split())
    if document.source_type is CommunitySearchSource.USER:
        preview = f"@{document.username}" if document.username else ""
    if len(preview) > 180:
        preview = f"{preview[:177]}..."
    return CommunitySearchResultItem(
        type=document.source_type.value,
        source_id=document.source_id,
        title=document.title,
        preview=preview,
        username=document.username,
        board_code=document.board_code,
        group_slug=document.group_slug,
        updated_at=document.source_updated_at,
    )
