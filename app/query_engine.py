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
    """Read-only snapshot source accepted by the shared CRT query backend."""

    def snapshot(self): ...


@runtime_checkable
class ExecutableQuerySource(Protocol):
    """Source able to execute a query without materializing all documents in RAM."""

    def execute_search(
        self,
        search_engine: SearchEngine,
        query: SearchQuery | CompiledSearchQuery,
        *,
        preview_limit: int,
        result_limit: int | None,
        should_cancel: Callable[[], bool] | None,
    ) -> tuple[tuple[SearchHit, ...], int]: ...


@dataclass(frozen=True, slots=True)
class QueryExecutionResult:
    hits: tuple[SearchHit, ...]
    scanned_documents: int


class QueryEngine:
    """Shared execution facade for Search, filters and future conditions.

    In-memory tables continue to use SearchEngine directly. Persistent project
    indexes may execute against SQLite and return only matching records, without
    reconstructing the complete document set in application memory.
    """

    def __init__(self, search_engine: SearchEngine | None = None) -> None:
        self._search_engine = search_engine or SearchEngine()

    def compile_search(self, query: SearchQuery) -> CompiledSearchQuery:
        return self._search_engine.compile(query)

    def search(
        self,
        source: QueryDocumentSource | ExecutableQuerySource | Iterable[SearchDocument],
        query: SearchQuery | CompiledSearchQuery,
        *,
        preview_limit: int = 240,
        result_limit: int | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> QueryExecutionResult:
        if isinstance(source, ExecutableQuerySource):
            hits, scanned = source.execute_search(
                self._search_engine,
                query,
                preview_limit=preview_limit,
                result_limit=result_limit,
                should_cancel=should_cancel,
            )
            return QueryExecutionResult(hits=tuple(hits), scanned_documents=int(scanned))

        documents = source.snapshot() if isinstance(source, QueryDocumentSource) else tuple(source)
        if isinstance(documents, ExecutableQuerySource):
            hits, scanned = documents.execute_search(
                self._search_engine,
                query,
                preview_limit=preview_limit,
                result_limit=result_limit,
                should_cancel=should_cancel,
            )
            return QueryExecutionResult(hits=tuple(hits), scanned_documents=int(scanned))

        materialized = tuple(documents)
        hits = self._search_engine.search(
            materialized,
            query,
            preview_limit=preview_limit,
            result_limit=result_limit,
            should_cancel=should_cancel,
        )
        return QueryExecutionResult(hits=tuple(hits), scanned_documents=len(materialized))
