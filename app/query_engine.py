from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .search_engine import (
    CompiledSearchQuery,
    SearchDocument,
    SearchEngine,
    SearchHit,
    SearchQuery,
)


@runtime_checkable
class QueryDocumentSource(Protocol):
    """Read-only source accepted by the shared CRT query backend."""

    def snapshot(self) -> tuple[SearchDocument, ...]: ...


@dataclass(frozen=True, slots=True)
class QueryExecutionResult:
    hits: tuple[SearchHit, ...]
    scanned_documents: int


class QueryEngine:
    """Shared execution facade for Search, filters and future conditions.

    The first implementation delegates text matching to SearchEngine while
    establishing one stable backend boundary for every CRT query consumer.
    """

    def __init__(self, search_engine: SearchEngine | None = None) -> None:
        self._search_engine = search_engine or SearchEngine()

    def compile_search(self, query: SearchQuery) -> CompiledSearchQuery:
        return self._search_engine.compile(query)

    def search(
        self,
        source: QueryDocumentSource | Iterable[SearchDocument],
        query: SearchQuery | CompiledSearchQuery,
        *,
        preview_limit: int = 240,
        result_limit: int | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> QueryExecutionResult:
        documents = source.snapshot() if isinstance(source, QueryDocumentSource) else tuple(source)
        hits = self._search_engine.search(
            documents,
            query,
            preview_limit=preview_limit,
            result_limit=result_limit,
            should_cancel=should_cancel,
        )
        return QueryExecutionResult(hits=tuple(hits), scanned_documents=len(documents))
