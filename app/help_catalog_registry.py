from __future__ import annotations

import re
import unicodedata
from html import escape

from .help_catalog import (
    HELP_CATEGORY_ORDER,
    HELP_TOPICS as BASE_HELP_TOPICS,
    HelpSection,
    HelpTopic,
)
from .help_catalog_stage2d2 import STAGE2D2_HELP_TOPICS


HELP_TOPICS: tuple[HelpTopic, ...] = BASE_HELP_TOPICS + STAGE2D2_HELP_TOPICS
_TOPIC_BY_ID = {topic.id: topic for topic in HELP_TOPICS}


def help_topic(topic_id: str) -> HelpTopic:
    try:
        return _TOPIC_BY_ID[str(topic_id)]
    except KeyError as exc:
        raise KeyError(f"unknown help topic: {topic_id}") from exc


def help_topics_by_category() -> tuple[tuple[str, tuple[HelpTopic, ...]], ...]:
    return tuple(
        (
            category,
            tuple(topic for topic in HELP_TOPICS if topic.category == category),
        )
        for category in HELP_CATEGORY_ORDER
        if any(topic.category == category for topic in HELP_TOPICS)
    )


def search_help_topics(query: str) -> tuple[HelpTopic, ...]:
    normalized = _normalize(query)
    if not normalized:
        return HELP_TOPICS
    tokens = tuple(token for token in normalized.split() if token)
    ranked: list[tuple[int, int, HelpTopic]] = []
    for order, topic in enumerate(HELP_TOPICS):
        title = _normalize(topic.title)
        summary = _normalize(topic.summary)
        keywords = _normalize(" ".join(topic.keywords))
        body = _normalize(_topic_plain_text(topic))
        haystack = " ".join((title, summary, keywords, body))
        if not all(token in haystack for token in tokens):
            continue
        score = 0
        for token in tokens:
            if token in title:
                score += 40
            if token in keywords:
                score += 20
            if token in summary:
                score += 10
            if token in body:
                score += 2
        ranked.append((-score, order, topic))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in ranked)


def render_help_home_html() -> str:
    categories: list[str] = []
    for category, topics in help_topics_by_category():
        links = "".join(
            f'<li><a href="help://topic/{escape(topic.id)}">{escape(topic.title)}</a>'
            f'<div class="summary">{escape(topic.summary)}</div></li>'
            for topic in topics
        )
        categories.append(f"<h2>{escape(category)}</h2><ul>{links}</ul>")
    return _page(
        "Pomoc CAN Research Tool",
        '<p class="lead">Przeszukiwalny opis funkcji programu, przepływów pracy, ograniczeń i pojęć technicznych.</p>'
        '<div class="callout"><b>Zasada nadrzędna:</b> surowe sesje są źródłem prawdy, a filtry i analizy są warstwą prezentacji lub trwałymi artefaktami.</div>'
        "<h2>Szybkie przejścia</h2>"
        '<div class="quick">'
        '<a href="help://topic/quick-start">Pierwsze badanie</a>'
        '<a href="help://topic/live-capture">Live Capture</a>'
        '<a href="help://topic/comparison-dashboard">Porównanie logów</a>'
        '<a href="help://topic/uds-transactions">Transakcje UDS</a>'
        '<a href="help://topic/uds-timeline">Oś UDS</a>'
        '<a href="help://topic/troubleshooting-empty">Brak wyników</a>'
        '<a href="help://topic/glossary">Słownik</a>'
        "</div>"
        + "".join(categories),
    )


def render_help_topic_html(topic: HelpTopic) -> str:
    chunks = [f'<p class="lead">{escape(topic.summary)}</p>']
    for section in topic.sections:
        chunks.append(f"<h2>{escape(section.title)}</h2>")
        chunks.extend(f"<p>{_inline(value)}</p>" for value in section.paragraphs)
        if section.bullets:
            chunks.append(
                "<ul>"
                + "".join(f"<li>{_inline(value)}</li>" for value in section.bullets)
                + "</ul>"
            )
        if section.steps:
            chunks.append(
                "<ol>"
                + "".join(f"<li>{_inline(value)}</li>" for value in section.steps)
                + "</ol>"
            )
        if section.note:
            chunks.append(
                f'<div class="note"><b>Uwaga:</b> {_inline(section.note)}</div>'
            )
        if section.warning:
            chunks.append(
                f'<div class="warning"><b>Ważne:</b> {_inline(section.warning)}</div>'
            )
    if topic.related:
        links = []
        for related_id in topic.related:
            related = _TOPIC_BY_ID.get(related_id)
            if related is not None:
                links.append(
                    f'<li><a href="help://topic/{escape(related.id)}">{escape(related.title)}</a></li>'
                )
        if links:
            chunks.append("<h2>Powiązane tematy</h2><ul>" + "".join(links) + "</ul>")
    return _page(topic.title, "".join(chunks))


def _page(title: str, body: str) -> str:
    return f"""
<!doctype html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: sans-serif; line-height: 1.48; margin: 24px 32px 48px; }}
h1 {{ font-size: 26px; margin: 0 0 10px; }}
h2 {{ font-size: 18px; margin-top: 26px; padding-bottom: 5px; border-bottom: 1px solid palette(mid); }}
p, li {{ font-size: 14px; }}
.lead {{ font-size: 16px; }}
.summary {{ opacity: 0.78; margin: 2px 0 8px; }}
.callout, .note, .warning {{ border: 1px solid palette(mid); border-radius: 5px; padding: 10px 12px; margin: 14px 0; }}
.warning {{ border-left: 5px solid #c57b00; }}
.note {{ border-left: 5px solid #3b82c4; }}
.quick {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 20px; }}
.quick a {{ border: 1px solid palette(mid); border-radius: 4px; padding: 7px 10px; text-decoration: none; }}
code {{ font-family: monospace; background: palette(alternate-base); padding: 1px 4px; border-radius: 3px; }}
a {{ text-decoration: none; }}
</style></head><body><h1>{escape(title)}</h1>{body}</body></html>
"""


def _inline(value: str) -> str:
    parts = re.split(r"(`[^`]+`)", str(value))
    rendered: list[str] = []
    for part in parts:
        if len(part) >= 2 and part.startswith("`") and part.endswith("`"):
            rendered.append(f"<code>{escape(part[1:-1])}</code>")
        else:
            rendered.append(escape(part))
    return "".join(rendered)


def _topic_plain_text(topic: HelpTopic) -> str:
    values = [topic.title, topic.summary, " ".join(topic.keywords)]
    for section in topic.sections:
        values.extend((section.title, *section.paragraphs, *section.bullets, *section.steps))
        values.extend((section.note, section.warning))
    return " ".join(value for value in values if value)


def _normalize(value: str) -> str:
    folded = str(value).casefold().translate(str.maketrans({"ł": "l"}))
    decomposed = unicodedata.normalize("NFKD", folded)
    without_marks = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(re.findall(r"[a-z0-9x]+", without_marks))


__all__ = [
    "HELP_CATEGORY_ORDER",
    "HELP_TOPICS",
    "HelpSection",
    "HelpTopic",
    "help_topic",
    "help_topics_by_category",
    "render_help_home_html",
    "render_help_topic_html",
    "search_help_topics",
]
