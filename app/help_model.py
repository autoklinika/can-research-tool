from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HelpSection:
    title: str
    paragraphs: tuple[str, ...] = ()
    bullets: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    note: str = ""
    warning: str = ""


@dataclass(frozen=True, slots=True)
class HelpTopic:
    id: str
    category: str
    title: str
    summary: str
    keywords: tuple[str, ...]
    sections: tuple[HelpSection, ...]
    related: tuple[str, ...] = ()


__all__ = ["HelpSection", "HelpTopic"]
