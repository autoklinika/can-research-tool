from __future__ import annotations

import pytest

from app.search_engine import (
    SearchDocument,
    SearchEngine,
    SearchMode,
    SearchQuery,
    SearchQueryError,
)


def test_contains_search_matches_selected_fields() -> None:
    engine = SearchEngine()
    documents = [
        SearchDocument(0, {"can_id": "18DA00F9", "payload": "27 07"}),
        SearchDocument(1, {"can_id": "18DAF900", "payload": "67 07 12 34 56 78"}),
    ]

    hits = engine.search(
        documents,
        SearchQuery("18DAF900", fields=frozenset({"can_id"})),
    )

    assert [hit.row for hit in hits] == [1]
    assert hits[0].matched_fields == ("can_id",)


def test_hex_query_matches_compact_prefixed_and_spaced_forms() -> None:
    engine = SearchEngine()
    documents = [
        SearchDocument(0, {"payload": "7F 27 35"}),
        SearchDocument(1, {"payload": "0x7f2735"}),
        SearchDocument(2, {"payload": "7f2735"}),
    ]

    hits = engine.search(documents, SearchQuery("7F 27 35"))

    assert [hit.row for hit in hits] == [0, 1, 2]


def test_exact_prefix_suffix_wildcard_and_regex_modes() -> None:
    engine = SearchEngine()
    documents = [SearchDocument(0, {"text": "18DAF900 | 7F 27 35"})]

    assert engine.search(documents, SearchQuery("18DAF900 | 7F 27 35", SearchMode.EXACT))
    assert engine.search(documents, SearchQuery("18DA", SearchMode.PREFIX))
    assert engine.search(documents, SearchQuery("27 35", SearchMode.SUFFIX))
    assert engine.search(documents, SearchQuery("18DA*35", SearchMode.WILDCARD))
    assert engine.search(documents, SearchQuery(r"18DAF9\d{2}", SearchMode.REGEX))


def test_invalid_regex_is_rejected() -> None:
    with pytest.raises(SearchQueryError):
        SearchEngine().compile(SearchQuery("[", SearchMode.REGEX))


def test_result_limit_stops_scan_output() -> None:
    documents = [SearchDocument(index, {"text": "match"}) for index in range(20)]

    hits = SearchEngine().search(documents, SearchQuery("match"), result_limit=3)

    assert [hit.row for hit in hits] == [0, 1, 2]
