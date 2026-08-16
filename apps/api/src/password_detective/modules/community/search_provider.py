from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from password_detective.db.models.community import CommunitySearchDocument, CommunitySearchSource

SearchMode = Literal["ngram", "prefix_fallback", "test"]


@dataclass(frozen=True)
class CommunitySearchProviderState:
    mode: SearchMode
    degraded: bool


class CommunitySearchProvider(Protocol):
    def preflight(self, db: Session) -> CommunitySearchProviderState: ...

    def search_documents(
        self,
        db: Session,
        *,
        query: str,
        source_types: tuple[CommunitySearchSource, ...],
        candidate_limit: int,
    ) -> list[CommunitySearchDocument]: ...


def _apply_source_type_filter(statement, source_types: tuple[CommunitySearchSource, ...]):
    if source_types:
        return statement.where(CommunitySearchDocument.source_type.in_(source_types))
    return statement


class SQLiteCommunitySearchProvider:
    """Deterministic SQLite double used in tests; it is not a production full-text provider."""

    def __init__(self, *, max_prefix_candidates: int = 200) -> None:
        self.max_prefix_candidates = max_prefix_candidates

    def preflight(self, db: Session) -> CommunitySearchProviderState:
        if db.get_bind().dialect.name != "sqlite":
            raise ValueError("SQLiteCommunitySearchProvider requires a SQLite session")
        return CommunitySearchProviderState(mode="test", degraded=False)

    def search_documents(
        self,
        db: Session,
        *,
        query: str,
        source_types: tuple[CommunitySearchSource, ...],
        candidate_limit: int,
    ) -> list[CommunitySearchDocument]:
        bounded_limit = min(candidate_limit, self.max_prefix_candidates)
        pattern = f"%{query.lower()}%"
        statement = select(CommunitySearchDocument).where(
            CommunitySearchDocument.is_public.is_(True),
            or_(
                func.lower(CommunitySearchDocument.title).like(pattern),
                func.lower(CommunitySearchDocument.body).like(pattern),
                func.lower(CommunitySearchDocument.username).like(pattern),
            ),
        )
        statement = _apply_source_type_filter(statement, source_types)
        statement = statement.order_by(CommunitySearchDocument.source_updated_at.desc()).limit(
            bounded_limit
        )
        return list(db.scalars(statement))


class MySQLNgramCommunitySearchProvider:
    """Production MySQL FULLTEXT ngram provider."""

    def preflight(self, db: Session) -> CommunitySearchProviderState:
        if db.get_bind().dialect.name != "mysql":
            raise ValueError("MySQLNgramCommunitySearchProvider requires a MySQL session")
        return CommunitySearchProviderState(mode="ngram", degraded=False)

    def search_documents(
        self,
        db: Session,
        *,
        query: str,
        source_types: tuple[CommunitySearchSource, ...],
        candidate_limit: int,
    ) -> list[CommunitySearchDocument]:
        match_expression = text(
            "MATCH(title, body) AGAINST (:query IN BOOLEAN MODE)"
        )
        statement = select(CommunitySearchDocument).where(
            CommunitySearchDocument.is_public.is_(True),
            match_expression,
        )
        statement = _apply_source_type_filter(statement, source_types)
        statement = statement.order_by(
            text("MATCH(title, body) AGAINST (:query IN BOOLEAN MODE) DESC"),
            CommunitySearchDocument.source_updated_at.desc(),
        ).limit(candidate_limit)
        return list(db.scalars(statement, {"query": query}))


class PrefixFallbackCommunitySearchProvider:
    """Bounded degradation path for non-SQLite, non-ngram deployments."""

    def __init__(self, *, max_prefix_candidates: int = 200) -> None:
        self.max_prefix_candidates = max_prefix_candidates

    def preflight(self, db: Session) -> CommunitySearchProviderState:
        return CommunitySearchProviderState(mode="prefix_fallback", degraded=True)

    def search_documents(
        self,
        db: Session,
        *,
        query: str,
        source_types: tuple[CommunitySearchSource, ...],
        candidate_limit: int,
    ) -> list[CommunitySearchDocument]:
        bounded_limit = min(candidate_limit, self.max_prefix_candidates)
        pattern = f"{query.lower()}%"
        statement = select(CommunitySearchDocument).where(
            CommunitySearchDocument.is_public.is_(True),
            or_(
                func.lower(CommunitySearchDocument.title).like(pattern),
                func.lower(CommunitySearchDocument.username).like(pattern),
            ),
        )
        statement = _apply_source_type_filter(statement, source_types)
        statement = statement.order_by(CommunitySearchDocument.source_updated_at.desc()).limit(
            bounded_limit
        )
        return list(db.scalars(statement))


def provider_for_session(db: Session) -> CommunitySearchProvider:
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "mysql":
        return MySQLNgramCommunitySearchProvider()
    if dialect_name == "sqlite":
        return SQLiteCommunitySearchProvider()
    return PrefixFallbackCommunitySearchProvider()
