from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Iterable

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QObject,
    QRunnable,
    QSortFilterProxyModel,
    Signal,
    Slot,
)

from app.live_filters import ActiveFilterSet
from app.logical_records import LogicalMessageRecord

from .logical_message_model import LogicalMessageTableModel


LOGICAL_FILTER_WORKER_YIELD_EVERY = 256
LOGICAL_FILTER_WORKER_YIELD_SECONDS = 0.001


@dataclass(frozen=True, slots=True)
class LogicalFilterScanResult:
    accepted_keys: frozenset[tuple[int, int, int | None]]
    evaluated_keys: frozenset[tuple[int, int, int | None]]
    protocol_counts: tuple[tuple[str, int], ...] = ()
    transport_counts: tuple[tuple[str, int], ...] = ()
    incomplete_count: int = 0


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
            protocol_counts: dict[str, int] = {}
            transport_counts: dict[str, int] = {}
            incomplete_count = 0
            for index, message in enumerate(self.messages, start=1):
                key = logical_message_key(message)
                evaluated.add(key)
                if self.filter_set.decide_logical_message(
                    message,
                    relative_time_us=int(message.first_timestamp_ns // 1_000),
                ).visible:
                    accepted.add(key)
                    _increment_count(protocol_counts, str(message.protocol).upper())
                    _increment_count(transport_counts, str(message.transport).upper())
                    if not message.complete:
                        incomplete_count += 1
                if index % LOGICAL_FILTER_WORKER_YIELD_EVERY == 0:
                    sleep(LOGICAL_FILTER_WORKER_YIELD_SECONDS)
            self.signals.completed.emit(
                self.generation,
                LogicalFilterScanResult(
                    accepted_keys=frozenset(accepted),
                    evaluated_keys=frozenset(evaluated),
                    protocol_counts=tuple(sorted(protocol_counts.items())),
                    transport_counts=tuple(sorted(transport_counts.items())),
                    incomplete_count=incomplete_count,
                ),
            )
        except Exception as exc:
            self.signals.failed.emit(self.generation, str(exc))


class LogicalMessageFilterProxy(QSortFilterProxyModel):
    """Presentation-only filter for logical-message tables.

    The source model keeps the full bounded GUI buffer. While a full scan is running,
    the proxy deliberately exposes all source rows. Once the generation-safe result is
    applied, rows beyond the immutable snapshot are evaluated incrementally.

    Summary counters are maintained with the filter cache. This avoids scanning the
    entire logical-message buffer every time the GUI updates its protocol summary.
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
        self._protocol_counts: dict[str, int] = {}
        self._transport_counts: dict[str, int] = {}
        self._incomplete_count = 0
        self._connected_source: QAbstractItemModel | None = None
        self.setDynamicSortFilter(True)

    @property
    def signature(self) -> tuple[object, ...]:
        return self._signature

    @property
    def cache_size(self) -> int:
        return len(self._evaluated_keys)

    def setSourceModel(self, source_model: QAbstractItemModel | None) -> None:  # noqa: N802
        previous = self._connected_source
        if previous is not None:
            try:
                previous.rowsAboutToBeRemoved.disconnect(
                    self._source_rows_about_to_be_removed
                )
            except (RuntimeError, TypeError):
                pass
        super().setSourceModel(source_model)
        self._connected_source = source_model
        if source_model is not None:
            source_model.rowsAboutToBeRemoved.connect(
                self._source_rows_about_to_be_removed
            )

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
            self._clear_filter_cache()
            self.invalidateFilter()
        else:
            # The Live table remains attached to its source model until the worker
            # result is ready. Do not synchronously remap the full source here.
            self.filter_ready = False
            self.filter_scanning = False

    def begin_background_scan(self) -> None:
        if not self.filter_enabled:
            return
        self.filter_scanning = True
        self.filter_ready = False
        self._clear_filter_cache(keep_state=True)
        # Applying the completed worker result performs the single required
        # invalidation. Avoid a second full pass before any filter result exists.

    def apply_background_result(self, result: LogicalFilterScanResult) -> None:
        if not self.filter_enabled:
            return
        self._accepted_keys = set(result.accepted_keys)
        self._evaluated_keys = set(result.evaluated_keys)
        self._protocol_counts = dict(result.protocol_counts)
        self._transport_counts = dict(result.transport_counts)
        self._incomplete_count = max(0, int(result.incomplete_count))
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
            self._add_to_summary(message)
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

    def summary_counts(self) -> tuple[dict[str, int], dict[str, int], int]:
        model = self.sourceModel()
        if not self.filter_enabled or not self.filter_ready:
            if isinstance(model, LogicalMessageTableModel):
                return model.summary_counts()
            return {}, {}, 0
        return (
            dict(self._protocol_counts),
            dict(self._transport_counts),
            self._incomplete_count,
        )

    def prune_source_cache_if_needed(self, maximum_keys: int) -> bool:
        """Prune stale keys only after the cache materially exceeds the live window.

        The old integration built a complete source snapshot on every front removal,
        even when the cache was small. That made each capacity rollover O(buffer).
        """

        if maximum_keys <= 0:
            raise ValueError("maximum_keys must be greater than zero")
        if len(self._evaluated_keys) <= maximum_keys:
            return False
        self.prune_to_messages(self.snapshot_messages())
        return True

    def prune_to_messages(self, messages: Iterable[LogicalMessageRecord]) -> None:
        current = {logical_message_key(message) for message in messages}
        if len(self._evaluated_keys) <= max(10_000, len(current) * 2):
            return
        self._evaluated_keys.intersection_update(current)
        self._accepted_keys.intersection_update(current)

    def _source_rows_about_to_be_removed(
        self,
        _parent: QModelIndex,
        first: int,
        last: int,
    ) -> None:
        if first < 0 or last < first:
            return
        for row in range(first, last + 1):
            message = self._source_message(row)
            if message is None:
                continue
            key = logical_message_key(message)
            was_accepted = key in self._accepted_keys
            self._evaluated_keys.discard(key)
            self._accepted_keys.discard(key)
            if was_accepted:
                self._remove_from_summary(message)

    def _clear_filter_cache(self, *, keep_state: bool = False) -> None:
        if not keep_state:
            self.filter_ready = False
            self.filter_scanning = False
        self._accepted_keys.clear()
        self._evaluated_keys.clear()
        self._protocol_counts.clear()
        self._transport_counts.clear()
        self._incomplete_count = 0

    def _add_to_summary(self, message: LogicalMessageRecord) -> None:
        _increment_count(self._protocol_counts, str(message.protocol).upper())
        _increment_count(self._transport_counts, str(message.transport).upper())
        if not message.complete:
            self._incomplete_count += 1

    def _remove_from_summary(self, message: LogicalMessageRecord) -> None:
        _decrement_count(self._protocol_counts, str(message.protocol).upper())
        _decrement_count(self._transport_counts, str(message.transport).upper())
        if not message.complete:
            self._incomplete_count = max(0, self._incomplete_count - 1)

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


def _increment_count(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _decrement_count(counts: dict[str, int], key: str) -> None:
    remaining = counts.get(key, 0) - 1
    if remaining > 0:
        counts[key] = remaining
    else:
        counts.pop(key, None)
