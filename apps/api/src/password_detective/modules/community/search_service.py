from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.db.models.community import CommunitySearchDocument, CommunitySearchSource
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
        if not (
            unicodedata.category(character).startswith("C")
            and not character.isspace()
        )
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
