from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QRunnable,
    QThreadPool,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtWidgets import QCheckBox, QLayout

from app.filters import CanFrameRecord, ProjectFilterRepository
from app.live_filters import ActiveFilterSet
from app.models import CanFrame

from .logical_filter_integration import (
    LogicalFilterScanResult,
    LogicalFilterScanTask,
    LogicalMessageFilterProxy,
)
from .logical_message_model import format_logical_message_inspector

if TYPE_CHECKING:
    from .live_capture import LiveCaptureWidget


LIVE_FRAME_CAPACITY = 250_000
LIVE_MESSAGE_CAPACITY = 100_000


class LiveFilterScanSignals(QObject):
    completed = Signal(int, object, int)
    failed = Signal(int, str)


class LiveFilterScanTask(QRunnable):
    """Evaluate an immutable Live-buffer snapshot outside the Qt GUI thread."""

    def __init__(
        self,
        generation: int,
        frames: tuple[CanFrame, ...],
        filter_set: ActiveFilterSet,
    ) -> None:
        super().__init__()
        self.generation = generation
        self.frames = frames
        self.filter_set = filter_set
        self.signals = LiveFilterScanSignals()

    @Slot()
    def run(self) -> None:
        try:
            accepted: list[CanFrame] = []
            evaluated_through = -1
            for frame in self.frames:
                if self.filter_set.decide(_frame_record(frame)).visible:
                    accepted.append(frame)
                evaluated_through = max(evaluated_through, frame.sequence)
            self.signals.completed.emit(
                self.generation,
                accepted,
                evaluated_through,
            )
        except Exception as exc:
            self.signals.failed.emit(self.generation, str(exc))


class LiveFrameFilterProxy(QAbstractTableModel):
    """Projection model populated from background-filtered frame snapshots.

    The model deliberately does not inherit ``QSortFilterProxyModel``. Building a
    proxy mapping for a 250k-row source blocked the GUI twice whenever filters were
    enabled: once before the worker scan and once after it. This projection receives
    already accepted frame references and exposes them directly.
    """

    def __init__(self, widget: LiveCaptureWidget) -> None:
        super().__init__(widget)
        self.widget = widget
        self.filter_set = ActiveFilterSet((), scope="live")
        self.filter_enabled = False
        self.filter_ready = False
        self.filter_scanning = False
        self._signature: tuple[object, ...] = self.filter_set.signature
        self._frames: list[CanFrame] = []

    def sourceModel(self):  # noqa: N802
        """Compatibility accessor for code that inspects the backing frame model."""

        return self.widget.frame_model

    def reload_project_filters(self) -> bool:
        repository = ProjectFilterRepository(self.widget.project.database_path)
        candidate = ActiveFilterSet(repository.list_presets(), scope="live")
        if candidate.signature == self._signature:
            return False
        self.filter_set = candidate
        self._signature = candidate.signature
        return True

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        if not self.filter_enabled or not self.filter_ready:
            return self.widget.frame_model.frame_count
        return len(self._frames)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return self.widget.frame_model.columnCount(parent)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ):  # noqa: N802
        return self.widget.frame_model.headerData(section, orientation, role)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        if not self.filter_enabled or not self.filter_ready:
            source = self.widget.frame_model.index(index.row(), index.column())
            return self.widget.frame_model.data(source, role)
        frame = self.frame_at(index.row())
        if frame is None:
            return None
        return _frame_data(frame, index.column(), role)

    def frame_at(self, row: int) -> CanFrame | None:
        if not self.filter_enabled or not self.filter_ready:
            return self.widget.frame_model.frame_at(row)
        if 0 <= row < len(self._frames):
            return self._frames[row]
        return None

    def set_filter_enabled(self, enabled: bool) -> None:
        normalized = bool(enabled and self.filter_set.active_count)
        if normalized == self.filter_enabled:
            return
        self.beginResetModel()
        self.filter_enabled = normalized
        self.filter_ready = False
        self.filter_scanning = False
        self._frames.clear()
        self.endResetModel()

    def begin_background_scan(self) -> None:
        if not self.filter_enabled:
            return
        self.beginResetModel()
        self.filter_scanning = True
        self.filter_ready = False
        self._frames.clear()
        self.endResetModel()

    def apply_background_result(
        self,
        accepted_frames: tuple[CanFrame, ...],
        evaluated_through_sequence: int,
    ) -> None:
        if not self.filter_enabled:
            return
        first = self.widget.frame_model.frame_at(0)
        first_sequence = int(first.sequence) if first is not None else None
        retained = [
            frame
            for frame in accepted_frames
            if first_sequence is None or int(frame.sequence) >= first_sequence
        ][-LIVE_FRAME_CAPACITY:]
        self.beginResetModel()
        self._frames = retained
        self.filter_scanning = False
        self.filter_ready = True
        self.endResetModel()

    def append_source_frames(self, frames: tuple[CanFrame, ...]) -> None:
        if not frames or not self.filter_enabled or not self.filter_ready:
            return
        visible = [
            frame
            for frame in frames
            if self.filter_set.decide(_frame_record(frame)).visible
        ]
        if not visible:
            return
        overflow = max(0, len(self._frames) + len(visible) - LIVE_FRAME_CAPACITY)
        if overflow:
            trim_chunk = max(1, LIVE_FRAME_CAPACITY // 10)
            remove_count = min(len(self._frames), max(overflow, trim_chunk))
            self.beginRemoveRows(QModelIndex(), 0, remove_count - 1)
            del self._frames[:remove_count]
            self.endRemoveRows()
        first_row = len(self._frames)
        self.beginInsertRows(QModelIndex(), first_row, first_row + len(visible) - 1)
        self._frames.extend(visible)
        self.endInsertRows()

    def prune_before(self, first_sequence: int) -> None:
        if not self._frames:
            return
        remove_count = 0
        for frame in self._frames:
            if int(frame.sequence) >= first_sequence:
                break
            remove_count += 1
        if not remove_count:
            return
        self.beginRemoveRows(QModelIndex(), 0, remove_count - 1)
        del self._frames[:remove_count]
        self.endRemoveRows()


class LiveFilterIntegration(QObject):
    """Compose one opt-in filter control into raw and logical Live views."""

    def __init__(self, widget: LiveCaptureWidget) -> None:
        super().__init__(widget)
        self.widget = widget
        self._frame_generation = 0
        self._message_generation = 0
        self._frame_tasks: list[LiveFilterScanTask] = []
        self._message_tasks: list[LogicalFilterScanTask] = []
        self._pending_frames: list[CanFrame] = []

        self.proxy = LiveFrameFilterProxy(widget)
        widget.live_filter_proxy = self.proxy
        # Keep the high-volume raw table directly on its source model until the
        # user explicitly enables filters. An identity QSortFilterProxyModel over
        # hundreds of thousands of rows caused progressive Live GUI slowdown.
        widget.frame_model.modelReset.connect(self._source_frame_model_reset)
        widget.frame_model.rowsInserted.connect(self._source_frame_rows_inserted)
        widget.frame_model.rowsRemoved.connect(self._prune_frame_filter_cache)

        self.message_proxy = LogicalMessageFilterProxy(widget)
        self.message_proxy.set_filter_set(self.proxy.filter_set)
        self.message_proxy.setSourceModel(widget.message_model)
        widget.live_message_filter_proxy = self.message_proxy
        # Keep the logical table on its source model until the worker has produced
        # a complete result. This avoids synchronously invalidating 100k rows on click.
        widget.message_model.modelReset.connect(self._source_message_model_reset)
        widget.message_model.rowsRemoved.connect(self._prune_message_filter_cache)

        self.checkbox = QCheckBox("Zastosuj filtry")
        self.checkbox.setObjectName("applyLiveFilters")
        self.checkbox.setChecked(False)
        self.checkbox.setToolTip(
            "Filtry projektu są domyślnie wyłączone dla Live. Zaznacz, aby zastosować "
            "aktywne presety do surowych ramek i wiadomości logicznych."
        )
        self.checkbox.toggled.connect(self._set_filter_application)
        widget.apply_live_filters = self.checkbox
        controls = _find_layout_containing(widget.layout(), widget.auto_scroll)
        if controls is not None:
            controls.insertWidget(2, self.checkbox)
        else:
            widget.layout().insertWidget(1, self.checkbox)

        self._reload_timer = QTimer(widget)
        self._reload_timer.setInterval(750)
        self._reload_timer.timeout.connect(self._reload_and_update)
        self._reload_timer.start()
        self._reload_and_update()

    def selected_frame(self) -> CanFrame | None:
        rows = self.widget.frame_table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        if self.widget.frame_table.model() is self.proxy:
            return self.proxy.frame_at(row)
        return self.widget.frame_model.frame_at(row)

    def update_status(
        self,
        total_received: int,
        logical_total: int | None = None,
    ) -> None:
        self._update_live_counts(total_received, logical_total)

    def _message_selected(self) -> None:
        rows = self.widget.message_table.selectionModel().selectedRows()
        if not rows:
            return
        if self.widget.message_table.model() is self.message_proxy:
            message = self.message_proxy.message_at(rows[0].row())
        else:
            message = self.widget.message_model.message_at(rows[0].row())
        if message is not None:
            self.widget.inspector_text.emit(format_logical_message_inspector(message))

    def _set_filter_application(self, checked: bool) -> None:
        if not checked:
            # Detach filtered presentation models before clearing their state.
            self._set_frame_display_model(False)
            self._set_message_display_model(False)
        self.proxy.set_filter_enabled(checked)
        self.message_proxy.set_filter_enabled(checked)
        if checked and self.proxy.filter_enabled:
            names = ", ".join(self.proxy.filter_set.active_names)
            self.widget.output_message.emit(
                f"Filtry Live włączone — obliczam widok w tle: {names}"
            )
            self._schedule_frame_scan()
            self._schedule_message_scan()
        else:
            self._frame_generation += 1
            self._message_generation += 1
            self._pending_frames.clear()
            if checked and not self.proxy.filter_set.active_count:
                self.checkbox.setChecked(False)
            self.widget.output_message.emit(
                "Filtry Live wyłączone — pokazuję pełne bufory ramek i wiadomości"
            )
        self._update_filter_control()
        self._update_live_counts()

    def _reload_and_update(self) -> None:
        changed = self.proxy.reload_project_filters()
        logical_changed = self.message_proxy.set_filter_set(self.proxy.filter_set)
        if self.proxy.filter_set.active_count == 0:
            if self.checkbox.isChecked():
                self.checkbox.blockSignals(True)
                self.checkbox.setChecked(False)
                self.checkbox.blockSignals(False)
            self._frame_generation += 1
            self._message_generation += 1
            self._set_frame_display_model(False)
            self._set_message_display_model(False)
            self.proxy.set_filter_enabled(False)
            self.message_proxy.set_filter_enabled(False)
        elif (changed or logical_changed) and self.checkbox.isChecked():
            self._schedule_frame_scan()
            self._schedule_message_scan()
        self._update_filter_control()
        self._update_live_counts()

    def _source_frame_model_reset(self) -> None:
        if self.proxy.filter_enabled:
            self._set_frame_display_model(False)
            self._schedule_frame_scan()

    def _source_frame_rows_inserted(
        self,
        _parent: QModelIndex,
        first: int,
        last: int,
    ) -> None:
        if not self.proxy.filter_enabled or first < 0 or last < first:
            return
        frames = tuple(
            frame
            for row in range(first, last + 1)
            if (frame := self.widget.frame_model.frame_at(row)) is not None
        )
        if not frames:
            return
        if self.proxy.filter_scanning:
            self._pending_frames.extend(frames)
        elif self.proxy.filter_ready:
            self.proxy.append_source_frames(frames)

    def _source_message_model_reset(self) -> None:
        if self.message_proxy.filter_enabled:
            self._schedule_message_scan()

    def _schedule_frame_scan(self) -> None:
        if not self.proxy.filter_enabled:
            return
        self._frame_generation += 1
        generation = self._frame_generation
        frames = self.widget.frame_model.snapshot_frames()
        self._pending_frames.clear()
        self._set_frame_display_model(False)
        self.proxy.begin_background_scan()
        if not frames:
            self.proxy.apply_background_result((), -1)
            self._set_frame_display_model(True)
            self._update_filter_control()
            self._update_live_counts()
            return
        task = LiveFilterScanTask(generation, frames, self.proxy.filter_set)
        self._frame_tasks.append(task)
        self._frame_tasks = self._frame_tasks[-3:]
        task.signals.completed.connect(self._frame_scan_completed)
        task.signals.failed.connect(self._filter_scan_failed)
        QThreadPool.globalInstance().start(task)
        self._update_filter_control()

    def _schedule_message_scan(self) -> None:
        if not self.message_proxy.filter_enabled:
            return
        self._message_generation += 1
        generation = self._message_generation
        messages = self.message_proxy.snapshot_messages()
        self._set_message_display_model(False)
        self.message_proxy.begin_background_scan()
        if not messages:
            self.message_proxy.apply_background_result(
                LogicalFilterScanResult(frozenset(), frozenset())
            )
            self._set_message_display_model(True)
            self._update_filter_control()
            self._update_live_counts()
            return
        task = LogicalFilterScanTask(generation, messages, self.message_proxy.filter_set)
        self._message_tasks.append(task)
        self._message_tasks = self._message_tasks[-3:]
        task.signals.completed.connect(self._message_scan_completed)
        task.signals.failed.connect(self._logical_filter_scan_failed)
        QThreadPool.globalInstance().start(task)
        self._update_filter_control()

    def _frame_scan_completed(
        self,
        generation: int,
        accepted_frames: object,
        evaluated_through_sequence: int,
    ) -> None:
        if generation != self._frame_generation or not self.proxy.filter_enabled:
            return
        result_frames = tuple(
            frame for frame in accepted_frames if isinstance(frame, CanFrame)
        )
        self.proxy.apply_background_result(result_frames, evaluated_through_sequence)
        pending = tuple(
            frame
            for frame in self._pending_frames
            if int(frame.sequence) > evaluated_through_sequence
        )
        self._pending_frames.clear()
        self.proxy.append_source_frames(pending)
        self._prune_frame_filter_cache()
        self._set_frame_display_model(True)
        self._frame_tasks = self._frame_tasks[-2:]
        self._update_filter_control()
        self._update_live_counts()

    def _message_scan_completed(self, generation: int, result: object) -> None:
        if generation != self._message_generation or not self.message_proxy.filter_enabled:
            return
        if not isinstance(result, LogicalFilterScanResult):
            self._logical_filter_scan_failed(generation, "nieprawidłowy wynik workera")
            return
        self.message_proxy.apply_background_result(result)
        self._set_message_display_model(True)
        self._message_tasks = self._message_tasks[-2:]
        self._update_filter_control()
        self._update_live_counts()

    def _filter_scan_failed(self, generation: int, error: str) -> None:
        if generation != self._frame_generation:
            return
        self._disable_after_error(f"Błąd filtrowania ramek Live: {error}")

    def _logical_filter_scan_failed(self, generation: int, error: str) -> None:
        if generation != self._message_generation:
            return
        self._disable_after_error(f"Błąd filtrowania wiadomości Live: {error}")

    def _disable_after_error(self, message: str) -> None:
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(False)
        self.checkbox.blockSignals(False)
        self._set_frame_display_model(False)
        self._set_message_display_model(False)
        self.proxy.set_filter_enabled(False)
        self.message_proxy.set_filter_enabled(False)
        self._pending_frames.clear()
        self.widget.output_message.emit(message)
        self._update_filter_control()
        self._update_live_counts()

    def _prune_frame_filter_cache(self, *_args: object) -> None:
        first = self.widget.frame_model.frame_at(0)
        if first is not None:
            self.proxy.prune_before(int(first.sequence))

    def _prune_message_filter_cache(self, *_args: object) -> None:
        self.message_proxy.prune_source_cache_if_needed(LIVE_MESSAGE_CAPACITY * 2)

    def _set_frame_display_model(self, filtered: bool) -> None:
        target = self.proxy if filtered else self.widget.frame_model
        if self.widget.frame_table.model() is target:
            return
        self.widget.frame_table.setModel(target)
        self.widget.frame_table.selectionModel().selectionChanged.connect(
            self.widget._frame_selected
        )

    def _set_message_display_model(self, filtered: bool) -> None:
        target = self.message_proxy if filtered else self.widget.message_model
        if self.widget.message_table.model() is target:
            return
        self.widget.message_table.setModel(target)
        callback = self._message_selected if filtered else self.widget._message_selected
        self.widget.message_table.selectionModel().selectionChanged.connect(callback)

    def _update_filter_control(self) -> None:
        count = self.proxy.filter_set.active_count
        self.checkbox.setEnabled(count > 0)
        self.checkbox.setText(f"Zastosuj filtry ({count})" if count else "Zastosuj filtry")
        if count:
            names = ", ".join(self.proxy.filter_set.active_names)
            scanning = self.proxy.filter_scanning or self.message_proxy.filter_scanning
            if scanning:
                state = "PRZELICZANIE"
            else:
                state = "WŁĄCZONE" if self.proxy.filter_enabled else "WYŁĄCZONE"
            self.checkbox.setToolTip(
                f"Filtry Live: {state}. Aktywne presety: {names}. "
                "Pełne przeliczenie ramek i wiadomości odbywa się poza wątkiem GUI."
            )
        else:
            self.checkbox.setToolTip("Brak aktywnych presetów przeznaczonych dla Live Capture.")

    def _update_live_counts(
        self,
        total_received: int | None = None,
        logical_total: int | None = None,
    ) -> None:
        retained = self.widget.frame_model.frame_count
        visible = (
            self.proxy.rowCount()
            if self.proxy.filter_enabled and self.proxy.filter_ready
            else retained
        )
        frame_suffix = " (przeliczanie)" if self.proxy.filter_scanning else ""
        self.widget.visible_label.setText(
            (f"Widoczne: {visible:,} / bufor {retained:,}{frame_suffix}").replace(",", " ")
        )

        if total_received is None or logical_total is None:
            try:
                status = self.widget._controller.status()
            except Exception:
                status = None
            if total_received is None:
                total_received = int(status.frame_count) if status is not None else retained
            if logical_total is None:
                logical_total = (
                    int(status.logical_message_count)
                    if status is not None
                    else self.widget.message_model.message_count
                )

        self.widget.data_tabs.setTabText(
            self.widget.raw_tab_index,
            f"Surowe ramki ({visible:,}/{total_received:,})".replace(",", " "),
        )

        message_retained = self.widget.message_model.message_count
        message_visible = (
            self.message_proxy.rowCount()
            if self.message_proxy.filter_enabled and self.message_proxy.filter_ready
            else message_retained
        )
        message_suffix = " (przeliczanie)" if self.message_proxy.filter_scanning else ""
        self.widget.messages_label.setText(
            (
                f"Wiadomości: {logical_total:,} / widoczne {message_visible:,}{message_suffix}"
            ).replace(",", " ")
        )
        self.widget.data_tabs.setTabText(
            self.widget.message_tab_index,
            (
                f"Wiadomości logiczne ({message_visible:,}/{logical_total:,})"
                if self.message_proxy.filter_enabled
                else f"Wiadomości logiczne ({logical_total:,})"
            ).replace(",", " "),
        )


def _frame_data(frame: CanFrame, column: int, role: int):
    if role == Qt.TextAlignmentRole:
        if column in (0, 1, 2, 4, 6):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return int(Qt.AlignLeft | Qt.AlignVCenter)
    if role != Qt.DisplayRole:
        return None
    if column == 0:
        return f"{frame.timestamp_ns / 1_000_000:.3f}"
    if column == 1:
        return frame.sequence
    if column == 2:
        width = 8 if frame.is_extended_id else 3
        return f"0x{frame.arbitration_id:0{width}X}"
    if column == 3:
        return "EXT" if frame.is_extended_id else "STD"
    if column == 4:
        return frame.dlc
    if column == 5:
        return frame.data_hex
    if column == 6:
        return frame.channel
    if column == 7:
        flags: list[str] = []
        if frame.is_remote_frame:
            flags.append("RTR")
        if frame.is_error_frame:
            flags.append("ERR")
        if frame.source_flags:
            flags.append(f"0x{frame.source_flags:X}")
        return ", ".join(flags)
    return None


def _frame_record(frame: CanFrame) -> CanFrameRecord:
    return CanFrameRecord(
        can_id=int(frame.arbitration_id),
        extended=bool(frame.is_extended_id),
        dlc=int(frame.dlc),
        relative_time_us=int(frame.timestamp_ns // 1_000),
        channel=int(frame.channel),
    )


def _find_layout_containing(layout: QLayout | None, target: object) -> QLayout | None:
    if layout is None:
        return None
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is target:
            return layout
        found = _find_layout_containing(item.layout(), target)
        if found is not None:
            return found
    return None
