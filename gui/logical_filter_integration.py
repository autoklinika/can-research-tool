from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QModelIndex, QObject, QRunnable, QSortFilterProxyModel, Signal, Slot

from app.live_filters import ActiveFilterSet
from app.logical_records import LogicalMessageRecord

from .logical_message_model import LogicalMessageTableModel


@dataclass(frozen=True, slots=True)
class LogicalFilterScanResult:
    accepted_keys: frozenset[tuple[int, int, int | None]]
    evaluated_keys: frozenset[tuple[int, int, int | None]]


class LogicalFilterScanSignals(QObject):
    completed = Signal(int, object)
    failed = Signal(int, str)


class LogicalFilterScanTask(QRunnable):
    """Evaluate an immutable logical-message snapshot outside the GUI thread."""

    def __init__(
        self,
        generation: int,
        messages: tuple[LogicalMessageRecord, ...],
        filter_set: ActiveFilterSet,
    ) -> None:
        super().__init__()
        self.generation = generation
        self.messages = messages
        self.filter_set = filter_set
        self.signals = LogicalFilterScanSignals()

    @Slot()
    def run(self) -> None:
        try:
            accepted: set[tuple[int, int, int | None]] = set()
            evaluated: set[tuple[int, int, int | None]] = set()
            for message in self.messages:
                key = logical_message_key(message)
                evaluated.add(key)
                if self.filter_set.decide_logical_message(
                    message,
                    relative_time_us=int(message.first_timestamp_ns // 1_000),
                ).visible:
                    accepted.add(key)
            self.signals.completed.emit(
                self.generation,
                LogicalFilterScanResult(
                    accepted_keys=frozenset(accepted),
                    evaluated_keys=frozenset(evaluated),
                ),
            )
        except Exception as exc:
            self.signals.failed.emit(self.generation, str(exc))


class LogicalMessageFilterProxy(QSortFilterProxyModel):
    """Presentation-only filter for logical-message tables.

    The source model keeps the full bounded GUI buffer. While a full scan is running,
    the proxy deliberately exposes all source rows. Once the generation-safe result is
    applied, rows beyond the immutable snapshot are evaluated incrementally.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.filter_set = ActiveFilterSet(())
        self.filter_enabled = False
        self.filter_ready = False
        self.filter_scanning = False
        self._signature: tuple[object, ...] = self.filter_set.signature
        self._accepted_keys: set[tuple[int, int, int | None]] = set()
        self._evaluated_keys: set[tuple[int, int, int | None]] = set()
        self.setDynamicSortFilter(True)

    @property
    def signature(self) -> tuple[object, ...]:
        return self._signature

    def set_filter_set(self, filter_set: ActiveFilterSet) -> bool:
        if filter_set.signature == self._signature:
            return False
        self.filter_set = filter_set
        self._signature = filter_set.signature
        return True

    def set_filter_enabled(self, enabled: bool) -> None:
        normalized = bool(enabled and self.filter_set.active_count)
        if normalized == self.filter_enabled:
            return
        self.filter_enabled = normalized
        if not normalized:
            self.filter_ready = False
            self.filter_scanning = False
            self._accepted_keys.clear()
            self._evaluated_keys.clear()
        self.invalidateFilter()

    def begin_background_scan(self) -> None:
        if not self.filter_enabled:
            return
        self.filter_scanning = True
        self.filter_ready = False
        self._accepted_keys.clear()
        self._evaluated_keys.clear()
        self.invalidateFilter()

    def apply_background_result(self, result: LogicalFilterScanResult) -> None:
        if not self.filter_enabled:
            return
        self._accepted_keys = set(result.accepted_keys)
        self._evaluated_keys = set(result.evaluated_keys)
        self.filter_scanning = False
        self.filter_ready = True
        self.invalidateFilter()

    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QModelIndex,
    ) -> bool:  # noqa: N802
        if not self.filter_enabled or not self.filter_ready:
            return True
        message = self._source_message(source_row)
        if message is None:
            return False
        key = logical_message_key(message)
        if key in self._evaluated_keys:
            return key in self._accepted_keys

        visible = self.filter_set.decide_logical_message(
            message,
            relative_time_us=int(message.first_timestamp_ns // 1_000),
        ).visible
        self._evaluated_keys.add(key)
        if visible:
            self._accepted_keys.add(key)
        return visible

    def message_at(self, proxy_row: int) -> LogicalMessageRecord | None:
        if proxy_row < 0:
            return None
        proxy_index = self.index(proxy_row, 0)
        if not proxy_index.isValid():
            return None
        source_index = self.mapToSource(proxy_index)
        return self._source_message(source_index.row())

    def snapshot_messages(self) -> tuple[LogicalMessageRecord, ...]:
        model = self.sourceModel()
        if not isinstance(model, LogicalMessageTableModel):
            return ()
        return tuple(
            message
            for row in range(model.rowCount())
            if (message := model.message_at(row)) is not None
        )

    def prune_to_messages(self, messages: Iterable[LogicalMessageRecord]) -> None:
        current = {logical_message_key(message) for message in messages}
        if len(self._evaluated_keys) <= max(10_000, len(current) * 2):
            return
        self._evaluated_keys.intersection_update(current)
        self._accepted_keys.intersection_update(current)

    def _source_message(self, row: int) -> LogicalMessageRecord | None:
        model = self.sourceModel()
        if not isinstance(model, LogicalMessageTableModel):
            return None
        return model.message_at(row)


def logical_message_key(message: LogicalMessageRecord) -> tuple[int, int, int | None]:
    return (
        int(message.sequence),
        int(message.first_timestamp_ns),
        None if message.arbitration_id is None else int(message.arbitration_id),
    )
