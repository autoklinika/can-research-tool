from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Iterator

from PySide6.QtCore import QObject, Signal

from app.logical_cache import open_logical_cache_readonly, record_from_cache_row
from app.search_engine import (
    CompiledSearchQuery,
    SearchDocument,
    SearchEngine,
    SearchHit,
    SearchQuery,
)

from .stored_logical_message_panel import (
    decoded_values_text,
    format_logical_time,
    format_message_id,
    protocol_label,
    sender_text,
)


LOGICAL_SEARCH_HEADERS = (
    "Czas [s]",
    "ID",
    "Nazwa",
    "Nadawca",
    "Protokół",
    "DLC",
    "Dane",
    "Wartości (zdekodowane)",
)


class LogicalSqlQuerySource:
    """Worker-safe query source backed directly by the logical SQLite cache."""

    headers = list(LOGICAL_SEARCH_HEADERS)

    def __init__(
        self,
        cache_path: str | Path,
        visible_ids: tuple[int, ...] | None = None,
    ) -> None:
        self.cache_path = Path(cache_path).resolve()
        self.visible_ids = None if visible_ids is None else tuple(int(value) for value in visible_ids)

    def snapshot(self) -> "LogicalSqlQuerySource":
        return self

    def execute_search(
        self,
        search_engine: SearchEngine,
        query: SearchQuery | CompiledSearchQuery,
        *,
        preview_limit: int,
        result_limit: int | None,
        should_cancel: Callable[[], bool] | None,
    ) -> tuple[tuple[SearchHit, ...], int]:
        compiled = query if isinstance(query, CompiledSearchQuery) else search_engine.compile(query)
        hits: list[SearchHit] = []
        scanned = 0
        connection: sqlite3.Connection | None = None
        try:
            connection = open_logical_cache_readonly(self.cache_path)
            for display_row, row in self._iter_rows(connection):
                if should_cancel is not None and scanned % 256 == 0 and should_cancel():
                    return (), scanned
                document = _document_from_row(display_row, row)
                scanned += 1
                matched, matched_fields, matched_terms, fields = compiled.match_document(document)
                if not matched:
                    continue
                hits.append(
                    SearchHit(
                        row=document.row,
                        preview=" | ".join(value for _, value in fields)[:preview_limit],
                        matched_fields=matched_fields,
                        matched_terms=matched_terms,
                    )
                )
                if result_limit is not None and len(hits) >= result_limit:
                    break
        finally:
            if connection is not None:
                connection.close()
        return tuple(hits), scanned

    def _iter_rows(self, connection: sqlite3.Connection) -> Iterator[tuple[int, sqlite3.Row]]:
        identifiers = self.visible_ids
        if identifiers is None:
            for row in connection.execute("SELECT * FROM messages ORDER BY id"):
                yield max(0, int(row["id"]) - 1), row
            return

        chunk_size = 800
        for start in range(0, len(identifiers), chunk_size):
            chunk = identifiers[start : start + chunk_size]
            if not chunk:
                continue
            placeholders = ",".join("?" for _ in chunk)
            rows = connection.execute(
                f"SELECT * FROM messages WHERE id IN ({placeholders})",
                chunk,
            ).fetchall()
            by_id = {int(row["id"]): row for row in rows}
            for offset, identifier in enumerate(chunk):
                row = by_id.get(identifier)
                if row is not None:
                    yield start + offset, row


class LogicalSqlSearchIndex(QObject):
    """Ready-only adapter exposing an existing logical cache to LogSearchWindow."""

    progress_changed = Signal(int, int)
    ready_changed = Signal(bool)

    def __init__(self, model, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model = model
        self._active = False

    @property
    def model(self):
        return self._model

    @property
    def headers(self) -> list[str]:
        return list(LOGICAL_SEARCH_HEADERS)

    @property
    def is_ready(self) -> bool:
        path = getattr(self._model, "cache_path", None)
        return path is not None and Path(path).is_file()

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def progress(self) -> tuple[int, int]:
        total = int(self._model.rowCount()) if self._model is not None else 0
        return (total, total) if self.is_ready else (0, total)

    def start(self) -> None:
        self._active = True

    def snapshot(self):
        factory = getattr(self._model, "search_snapshot", None)
        if not callable(factory):
            return ()
        return factory()

    def close(self) -> None:
        self._active = False
        self._model = None


def _document_from_row(display_row: int, row: sqlite3.Row) -> SearchDocument:
    message = record_from_cache_row(row)
    fields = {
        "Czas [s]": format_logical_time(message.first_timestamp_ns),
        "ID": format_message_id(message),
        "Nazwa": message.name or "—",
        "Nadawca": _display_sender(message),
        "Protokół": protocol_label(message.protocol),
        "DLC": str(len(message.payload)),
        "Dane": message.payload_hex or "—",
        "Wartości (zdekodowane)": _display_decoded_values(message),
    }
    return SearchDocument(row=int(display_row), fields=fields)


def _display_sender(message) -> str:
    fields = message.fields or {}
    senders = fields.get("senders")
    if isinstance(senders, (list, tuple)) and senders:
        return ", ".join(str(value) for value in senders)
    return sender_text(message)


def _display_decoded_values(message) -> str:
    fields = message.fields or {}
    signals = fields.get("signals")
    if isinstance(signals, dict) and signals:
        units = fields.get("signal_units")
        unit_map = units if isinstance(units, dict) else {}
        parts: list[str] = []
        for name, value in signals.items():
            unit = str(unit_map.get(name) or "").strip()
            text = f"{name}: {_format_scalar(value)}"
            if unit:
                text += f" {unit}"
            parts.append(text)
            if len(parts) >= 8:
                break
        return "    ".join(parts)
    return decoded_values_text(message)


def _format_scalar(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)
