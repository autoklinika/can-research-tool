from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping, Sequence


class SearchMode(StrEnum):
    CONTAINS = "contains"
    EXACT = "exact"
    PREFIX = "prefix"
    SUFFIX = "suffix"
    WILDCARD = "wildcard"
    REGEX = "regex"


class SearchQueryError(ValueError):
    """Raised when a search query cannot be compiled."""


@dataclass(frozen=True, slots=True)
class SearchDocument:
    row: int
    fields: Mapping[str, str]

    @classmethod
    def from_columns(cls, row: int, columns: Sequence[object]) -> "SearchDocument":
        return cls(
            row=row,
            fields={f"column_{index}": str(value or "") for index, value in enumerate(columns)},
        )


@dataclass(frozen=True, slots=True)
class SearchQuery:
    text: str
    mode: SearchMode = SearchMode.CONTAINS
    fields: frozenset[str] = frozenset()
    case_sensitive: bool = False


@dataclass(frozen=True, slots=True)
class SearchHit:
    row: int
    preview: str
    matched_fields: tuple[str, ...]


class CompiledSearchQuery:
    def __init__(self, query: SearchQuery) -> None:
        text = query.text.strip()
        if not text:
            raise SearchQueryError("Zapytanie wyszukiwania nie może być puste.")
        self.query = query
        self._needle = text if query.case_sensitive else text.casefold()
        self._alternatives = self._build_alternatives(text)
        self._regex: re.Pattern[str] | None = None
        if query.mode == SearchMode.REGEX:
            flags = 0 if query.case_sensitive else re.IGNORECASE
            try:
                self._regex = re.compile(text, flags)
            except re.error as exc:
                raise SearchQueryError(f"Nieprawidłowe wyrażenie regularne: {exc}") from exc
        elif query.mode == SearchMode.WILDCARD:
            flags = 0 if query.case_sensitive else re.IGNORECASE
            self._regex = re.compile(fnmatch.translate(text), flags)

    def matches(self, value: str) -> bool:
        if self._regex is not None:
            return self._regex.search(value) is not None
        candidate = value if self.query.case_sensitive else value.casefold()
        if self.query.mode == SearchMode.EXACT:
            return any(candidate == item for item in self._alternatives)
        if self.query.mode == SearchMode.PREFIX:
            return any(candidate.startswith(item) for item in self._alternatives)
        if self.query.mode == SearchMode.SUFFIX:
            return any(candidate.endswith(item) for item in self._alternatives)
        return any(item in candidate for item in self._alternatives)

    def _build_alternatives(self, text: str) -> tuple[str, ...]:
        values = [text]
        compact = _compact_hex(text)
        if compact is not None:
            values.extend(
                (
                    compact,
                    " ".join(compact[index : index + 2] for index in range(0, len(compact), 2)),
                    f"0x{compact}",
                )
            )
        normalized = values if self.query.case_sensitive else [value.casefold() for value in values]
        return tuple(dict.fromkeys(normalized))


class SearchEngine:
    """Qt-independent search engine for live and stored CRT records."""

    def compile(self, query: SearchQuery) -> CompiledSearchQuery:
        return CompiledSearchQuery(query)

    def search(
        self,
        documents: Iterable[SearchDocument],
        query: SearchQuery | CompiledSearchQuery,
        *,
        preview_limit: int = 240,
        result_limit: int | None = None,
    ) -> list[SearchHit]:
        compiled = query if isinstance(query, CompiledSearchQuery) else self.compile(query)
        hits: list[SearchHit] = []
        selected_fields = compiled.query.fields
        for document in documents:
            fields = (
                document.fields.items()
                if not selected_fields
                else ((name, value) for name, value in document.fields.items() if name in selected_fields)
            )
            matched: list[str] = []
            preview_parts: list[str] = []
            for name, raw_value in fields:
                value = str(raw_value or "")
                preview_parts.append(value)
                if compiled.matches(value):
                    matched.append(name)
            if matched:
                hits.append(
                    SearchHit(
                        row=document.row,
                        preview=" | ".join(preview_parts)[:preview_limit],
                        matched_fields=tuple(matched),
                    )
                )
                if result_limit is not None and len(hits) >= result_limit:
                    break
        return hits


def _compact_hex(text: str) -> str | None:
    normalized = text.strip().lower()
    if normalized.startswith("0x"):
        normalized = normalized[2:]
    normalized = re.sub(r"[\s:_-]+", "", normalized)
    if not normalized or not re.fullmatch(r"[0-9a-f]+", normalized):
        return None
    if len(normalized) % 2:
        return None
    return normalized
