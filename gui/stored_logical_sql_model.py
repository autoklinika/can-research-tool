from __future__ import annotations

import sqlite3
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QRunnable, Qt, Signal, Slot

from app.logical_cache import open_logical_cache_readonly, record_from_cache_row
from app.logical_records import LogicalMessageRecord

from .stored_logical_message_panel import (
    MESSAGE_ROLE,
    StoredLogicalCriteria,
    decoded_values_text,
    format_logical_time,
    format_message_id,
    protocol_label,
    sender_text,
)

PAGE_SIZE = 256
MAX_CACHED_PAGES = 10
FILTER_YIELD_EVERY = 2_048


class StoredLogicalSqlModel(QAbstractTableModel):
    """Virtual eight-column model backed by the versioned logical SQLite cache."""

    HEADERS = (
        "Czas [s]",
        "ID",
        "Nazwa",
        "Nadawca",
        "Protokół",
        "DLC",
        "Dane",
        "Wartości (zdekodowane)",
    )

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache_path: Path | None = None
        self._connection: sqlite3.Connection | None = None
        self._total = 0
        self._visible_ids: tuple[int, ...] | None = None
        self._pages: OrderedDict[int, tuple[LogicalMessageRecord, ...]] = OrderedDict()

    @property
    def cache_path(self) -> Path | None:
        return self._cache_path

    @property
    def total_messages(self) -> int:
        return self._total

    @property
    def visible_messages(self) -> int:
        return self.rowCount()

    def set_cache(self, path: str | Path) -> None:
        self.close_cache()
        cache_path = Path(path).resolve()
        connection = open_logical_cache_readonly(cache_path)
        total = int(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
        self.beginResetModel()
        self._cache_path = cache_path
        self._connection = connection
        self._total = total
        self._visible_ids = None
        self._pages.clear()
        self.endResetModel()

    def close_cache(self) -> None:
        connection = self._connection
        if connection is None and self._cache_path is None:
            return
        self.beginResetModel()
        self._connection = None
        self._cache_path = None
        self._total = 0
        self._visible_ids = None
        self._pages.clear()
        self.endResetModel()
        if connection is not None:
            connection.close()

    def set_visible_ids(self, identifiers: tuple[int, ...] | None) -> None:
        self.beginResetModel()
        self._visible_ids = identifiers
        self._pages.clear()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return self._total if self._visible_ids is None else len(self._visible_ids)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return section + 1

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        message = self.message_at(index.row())
        if message is None:
            return None
        if role == MESSAGE_ROLE:
            return message
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() in (0, 1, 5):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        values = (
            format_logical_time(message.first_timestamp_ns),
            format_message_id(message),
            message.name or "—",
            sender_text(message),
            protocol_label(message.protocol),
            len(message.payload),
            message.payload_hex or "—",
            decoded_values_text(message),
        )
        return values[index.column()]

    def message_at(self, row: int) -> LogicalMessageRecord | None:
        if row < 0 or row >= self.rowCount() or self._connection is None:
            return None
        page_number = row // PAGE_SIZE
        page = self._pages.get(page_number)
        if page is None:
            page = self._load_page(page_number)
            self._pages[page_number] = page
            self._pages.move_to_end(page_number)
            while len(self._pages) > MAX_CACHED_PAGES:
                self._pages.popitem(last=False)
        local = row - page_number * PAGE_SIZE
        return page[local] if 0 <= local < len(page) else None

    def filter_choices(self) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
        connection = self._connection
        if connection is None:
            return (), ()
        protocols = tuple(
            (protocol_label(str(row[0])), str(row[0]))
            for row in connection.execute(
                "SELECT DISTINCT protocol FROM messages ORDER BY protocol COLLATE NOCASE"
            )
        )
        senders = tuple(
            str(row[0])
            for row in connection.execute(
                "SELECT DISTINCT sender FROM messages WHERE sender <> '—' "
                "ORDER BY sender COLLATE NOCASE"
            )
        )
        return protocols, senders

    def _load_page(self, page_number: int) -> tuple[LogicalMessageRecord, ...]:
        connection = self._connection
        if connection is None:
            return ()
        start = page_number * PAGE_SIZE
        if self._visible_ids is None:
            first_id = start + 1
            last_id = min(self._total, start + PAGE_SIZE)
            rows = connection.execute(
                "SELECT * FROM messages WHERE id BETWEEN ? AND ? ORDER BY id",
                (first_id, last_id),
            ).fetchall()
            return tuple(record_from_cache_row(row) for row in rows)

        identifiers = self._visible_ids[start : start + PAGE_SIZE]
        if not identifiers:
            return ()
        placeholders = ",".join("?" for _ in identifiers)
        rows = connection.execute(
            f"SELECT * FROM messages WHERE id IN ({placeholders})",
            identifiers,
        ).fetchall()
        by_id = {int(row["id"]): record_from_cache_row(row) for row in rows}
        return tuple(by_id[identifier] for identifier in identifiers if identifier in by_id)


class StoredLogicalSqlFilterSignals(QObject):
    completed = Signal(int, object, int)
    failed = Signal(int, str)


class StoredLogicalSqlFilterTask(QRunnable):
    """Evaluate local and project filters without loading the full cache into RAM."""

    def __init__(
        self,
        generation: int,
        cache_path: str | Path,
        criteria: StoredLogicalCriteria,
        project_filter_set: object | None,
    ) -> None:
        super().__init__()
        self.generation = generation
        self.cache_path = Path(cache_path)
        self.criteria = criteria
        self.project_filter_set = project_filter_set
        self.signals = StoredLogicalSqlFilterSignals()

    @Slot()
    def run(self) -> None:
        try:
            with open_logical_cache_readonly(self.cache_path) as connection:
                total = int(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
                sql, parameters = _criteria_query(self.criteria)
                needs_records = bool(
                    self.project_filter_set is not None
                    and getattr(self.project_filter_set, "active_count", 0)
                ) or self.criteria.hide_periodic
                if not needs_records:
                    identifiers = tuple(
                        int(row[0])
                        for row in connection.execute(
                            f"SELECT id FROM messages {sql} ORDER BY id",
                            parameters,
                        )
                    )
                else:
                    identifiers = self._filter_records(connection, sql, parameters)
            self.signals.completed.emit(self.generation, identifiers, total)
        except Exception as exc:
            self.signals.failed.emit(self.generation, str(exc))

    def _filter_records(
        self,
        connection: sqlite3.Connection,
        sql: str,
        parameters: tuple[object, ...],
    ) -> tuple[int, ...]:
        accepted: list[int] = []
        seen_periodic: set[tuple[object, ...]] = set()
        rows = connection.execute(f"SELECT * FROM messages {sql} ORDER BY id", parameters)
        for index, row in enumerate(rows, start=1):
            message = record_from_cache_row(row)
            filter_set = self.project_filter_set
            if filter_set is not None and getattr(filter_set, "active_count", 0):
                decision = filter_set.decide_logical_message(
                    message,
                    relative_time_us=int(message.first_timestamp_ns // 1_000),
                )
                if not decision.visible:
                    continue
            if self.criteria.hide_periodic:
                key = (
                    message.protocol,
                    message.transport,
                    message.arbitration_id,
                    message.pgn,
                    message.source_address,
                    message.destination_address,
                    message.name,
                    message.payload,
                )
                if key in seen_periodic:
                    continue
                seen_periodic.add(key)
            accepted.append(int(row["id"]))
            if index % FILTER_YIELD_EVERY == 0:
                pass
        return tuple(accepted)


def _criteria_query(criteria: StoredLogicalCriteria) -> tuple[str, tuple[object, ...]]:
    clauses: list[str] = []
    parameters: list[object] = []
    if criteria.protocol:
        clauses.append("protocol = ?")
        parameters.append(criteria.protocol)
    if criteria.sender:
        clauses.append("sender = ?")
        parameters.append(criteria.sender)
    if criteria.identity_text:
        clauses.append("identity_text LIKE ?")
        parameters.append(f"%{criteria.identity_text.casefold()}%")
    if criteria.time_from_ns is not None:
        clauses.append("first_timestamp_ns >= ?")
        parameters.append(int(criteria.time_from_ns))
    if criteria.time_to_ns is not None:
        clauses.append("first_timestamp_ns <= ?")
        parameters.append(int(criteria.time_to_ns))
    if criteria.only_errors:
        clauses.append(
            "(complete = 0 OR error <> '' OR instr(fields_json, '\"decode_error\"') > 0)"
        )
    if criteria.data_pattern:
        offset = max(0, int(criteria.data_offset or 0))
        clauses.append("substr(payload, ?, ?) = ?")
        parameters.extend((offset + 1, len(criteria.data_pattern), sqlite3.Binary(criteria.data_pattern)))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, tuple(parameters)
