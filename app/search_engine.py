from __future__ import annotations

import fnmatch
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterable, Mapping, Sequence


class SearchMode(StrEnum):
    CONTAINS = "contains"
    EXACT = "exact"
    PREFIX = "prefix"
    SUFFIX = "suffix"
    WILDCARD = "wildcard"
    REGEX = "regex"


class SearchLogic(StrEnum):
    ANY = "any"
    ALL = "all"


class SearchQueryError(ValueError):
    """Raised when a search query cannot be compiled."""


@dataclass(frozen=True, slots=True)
class SearchDocument:
    row: int
    fields: Mapping[str, str]
    normalized_fields: Mapping[str, str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        materialized = {name: str(value or "") for name, value in self.fields.items()}
        object.__setattr__(self, "fields", materialized)
        object.__setattr__(
            self,
            "normalized_fields",
            {name: value.casefold() for name, value in materialized.items()},
        )

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
    logic: SearchLogic = SearchLogic.ANY


@dataclass(frozen=True, slots=True)
class SearchHit:
    row: int
    preview: str
    matched_fields: tuple[str, ...]
    matched_terms: tuple[str, ...] = ()


class _CompiledTerm:
    def __init__(self, text: str, query: SearchQuery) -> None:
        self.text = text
        self.mode = query.mode
        self.case_sensitive = query.case_sensitive
        self._alternatives = self._build_alternatives(text)
        self._regex: re.Pattern[str] | None = None
        if query.mode == SearchMode.REGEX:
            flags = 0 if query.case_sensitive else re.IGNORECASE
            try:
                self._regex = re.compile(text, flags)
            except re.error as exc:
                raise SearchQueryError(
                    f"Nieprawidłowe wyrażenie regularne „{text}”: {exc}"
                ) from exc
        elif query.mode == SearchMode.WILDCARD:
            flags = 0 if query.case_sensitive else re.IGNORECASE
            self._regex = re.compile(fnmatch.translate(text), flags)

    def matches_prepared(self, raw_value: str, normalized_value: str) -> bool:
        if self._regex is not None:
            return self._regex.search(raw_value) is not None
        candidate = raw_value if self.case_sensitive else normalized_value
        if self.mode == SearchMode.EXACT:
            return candidate in self._alternatives
        if self.mode == SearchMode.PREFIX:
            return candidate.startswith(self._alternatives)
        if self.mode == SearchMode.SUFFIX:
            return candidate.endswith(self._alternatives)
        return any(item in candidate for item in self._alternatives)

    def matches(self, value: str) -> bool:
        raw_value = str(value or "")
        return self.matches_prepared(raw_value, raw_value.casefold())

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
        normalized = values if self.case_sensitive else [value.casefold() for value in values]
        return tuple(dict.fromkeys(normalized))


class CompiledSearchQuery:
    def __init__(self, query: SearchQuery) -> None:
        terms = _parse_terms(query.text)
        if not terms:
            raise SearchQueryError("Zapytanie wyszukiwania nie może być puste.")
        self.query = query
        self.logic = query.logic
        self.terms = tuple(_CompiledTerm(term, query) for term in terms)

    def match_document(
        self,
        document: SearchDocument,
    ) -> tuple[bool, tuple[str, ...], tuple[str, ...], tuple[tuple[str, str], ...]]:
        selected_fields = self.query.fields
        if selected_fields:
            fields = tuple(
                (name, value)
                for name, value in document.fields.items()
                if name in selected_fields
            )
        else:
            fields = tuple(document.fields.items())

        normalized = document.normalized_fields
        matched_fields: list[str] = []
        matched_field_set: set[str] = set()
        matched_terms: list[str] = []

        for term in self.terms:
            term_matched = False
            for name, raw_value in fields:
                if term.matches_prepared(raw_value, normalized[name]):
                    term_matched = True
                    if name not in matched_field_set:
                        matched_field_set.add(name)
                        matched_fields.append(name)

            if term_matched:
                matched_terms.append(term.text)
            elif self.logic == SearchLogic.ALL:
                return False, (), (), fields

        matched = (
            len(matched_terms) == len(self.terms)
            if self.logic == SearchLogic.ALL
            else bool(matched_terms)
        )
        return matched, tuple(matched_fields), tuple(matched_terms), fields

    def match_fields(
        self,
        fields: Iterable[tuple[str, str]],
    ) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
        document = SearchDocument(-1, dict(fields))
        matched, matched_fields, matched_terms, _ = self.match_document(document)
        return matched, matched_fields, matched_terms

    def matches(self, value: str) -> bool:
        matched, _, _ = self.match_fields((("value", value),))
        return matched


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
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[SearchHit]:
        compiled = query if isinstance(query, CompiledSearchQuery) else self.compile(query)
        hits: list[SearchHit] = []
        append_hit = hits.append

        for index, document in enumerate(documents):
            if should_cancel is not None and index % 256 == 0 and should_cancel():
                return []

            matched, matched_fields, matched_terms, fields = compiled.match_document(document)
            if not matched:
                continue

            append_hit(
                SearchHit(
                    row=document.row,
                    preview=" | ".join(value for _, value in fields)[:preview_limit],
                    matched_fields=matched_fields,
                    matched_terms=matched_terms,
                )
            )
            if result_limit is not None and len(hits) >= result_limit:
                break
        return hits


def _parse_terms(text: str) -> tuple[str, ...]:
    normalized = text.strip()
    if not normalized:
        return ()
    terms = tuple(part.strip() for part in normalized.split(",") if part.strip())
    if not terms:
        raise SearchQueryError("Podaj co najmniej jeden niepusty element wyszukiwania.")
    return terms


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
