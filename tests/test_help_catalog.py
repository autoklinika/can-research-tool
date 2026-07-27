from __future__ import annotations

from app.help_catalog import (
    HELP_CATEGORY_ORDER,
    HELP_TOPICS,
    help_topic,
    help_topics_by_category,
    render_help_home_html,
    render_help_topic_html,
    search_help_topics,
)


def test_help_catalog_is_complete_and_consistent() -> None:
    assert len(HELP_TOPICS) >= 25
    ids = [topic.id for topic in HELP_TOPICS]
    assert len(ids) == len(set(ids))
    assert ids[0] == "start"

    known_ids = set(ids)
    categories = {topic.category for topic in HELP_TOPICS}
    assert categories.issubset(set(HELP_CATEGORY_ORDER))
    assert {
        "Pierwsze kroki",
        "Rejestracja i ramki CAN",
        "Porównywanie logów",
        "Rozwiązywanie problemów",
    }.issubset(categories)

    for topic in HELP_TOPICS:
        assert topic.title.strip()
        assert topic.summary.strip()
        assert topic.sections
        assert set(topic.related).issubset(known_ids)


def test_search_is_accent_insensitive_and_searches_content() -> None:
    source_results = search_help_topics("zrodlo prawdy")
    assert source_results
    assert source_results[0].id == "source-of-truth"

    uds_results = search_help_topics("0x78 odpowiedz koncowa")
    assert {topic.id for topic in uds_results} >= {
        "uds-latency",
        "uds-transactions",
    }

    did_results = search_help_topics("Routine F022")
    assert did_results
    assert did_results[0].id in {"uds-transactions", "uds-basics"}

    assert search_help_topics("") == HELP_TOPICS
    assert search_help_topics("fraza-ktorej-na-pewno-nie-ma") == ()


def test_categories_preserve_declared_order() -> None:
    grouped = help_topics_by_category()
    names = [name for name, _topics in grouped]
    expected = [name for name in HELP_CATEGORY_ORDER if name in names]
    assert names == expected
    assert all(topics for _name, topics in grouped)


def test_rendered_help_contains_navigation_and_safety_content() -> None:
    home = render_help_home_html()
    assert "Pomoc CAN Research Tool" in home
    assert "help://topic/quick-start" in home
    assert "surowe sesje" in home

    topic = help_topic("uds-transactions")
    rendered = render_help_topic_html(topic)
    assert "Eksplorator transakcji UDS" in rendered
    assert "comparison_uds_latency" in rendered
    assert "evidence_truncated" in rendered
    assert "help://topic/artifacts" in rendered


def test_required_program_functions_have_topics() -> None:
    required = {
        "projects",
        "live-capture",
        "live-filters",
        "markers",
        "stored-sessions",
        "search",
        "dbc",
        "timeline",
        "timing-jitter",
        "uds-latency",
        "uds-transactions",
        "artifacts",
        "evidence-navigation",
        "bounded-model",
        "troubleshooting-empty",
        "glossary",
        "shortcuts",
    }
    assert required.issubset({topic.id for topic in HELP_TOPICS})
