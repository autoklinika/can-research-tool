from __future__ import annotations

import pytest

from app.search_engine import (
    SearchDocument,
    SearchEngine,
    SearchLogic,
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


def test_comma_search_with_or_matches_any_term() -> None:
    documents = [
        SearchDocument(0, {"service": "SecurityAccess request seed"}),
        SearchDocument(1, {"service": "SecurityAccess send key"}),
        SearchDocument(2, {"service": "ReadDataByIdentifier"}),
    ]

    hits = SearchEngine().search(
        documents,
        SearchQuery("seed, key", logic=SearchLogic.ANY),
    )

    assert [hit.row for hit in hits] == [0, 1]
    assert hits[0].matched_terms == ("seed",)
    assert hits[1].matched_terms == ("key",)


def test_comma_search_with_and_requires_all_terms_across_fields() -> None:
    documents = [
        SearchDocument(0, {"service": "SecurityAccess seed", "payload": "27 07"}),
        SearchDocument(1, {"service": "SecurityAccess key", "payload": "27 08"}),
        SearchDocument(2, {"service": "seed response", "comment": "key calculated"}),
    ]

    hits = SearchEngine().search(
        documents,
        SearchQuery("seed, key", logic=SearchLogic.ALL),
    )

    assert [hit.row for hit in hits] == [2]
    assert hits[0].matched_terms == ("seed", "key")
    assert hits[0].matched_fields == ("service", "comment")


def test_multi_term_hex_keeps_intelligent_normalization() -> None:
    documents = [
        SearchDocument(0, {"payload": "27 07"}),
        SearchDocument(1, {"payload": "67 08 A1 E4 10 55"}),
    ]

    hits = SearchEngine().search(
        documents,
        SearchQuery("2707, 0x6708", logic=SearchLogic.ANY),
    )

    assert [hit.row for hit in hits] == [0, 1]


def test_invalid_regex_is_rejected() -> None:
    with pytest.raises(SearchQueryError):
        SearchEngine().compile(SearchQuery("[", SearchMode.REGEX))


def test_result_limit_stops_scan_output() -> None:
    documents = [SearchDocument(index, {"text": "match"}) for index in range(20)]

    hits = SearchEngine().search(documents, SearchQuery("match"), result_limit=3)

    assert [hit.row for hit in hits] == [0, 1, 2]


def test_cancelled_scan_returns_no_partial_results() -> None:
    documents = [SearchDocument(index, {"text": "match"}) for index in range(1_000)]
    checks = 0

    def should_cancel() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 2

    hits = SearchEngine().search(
        documents,
        SearchQuery("match"),
        should_cancel=should_cancel,
    )

    assert hits == []
    assert checks == 2
