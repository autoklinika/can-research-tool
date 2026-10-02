from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QThreadPool,
    QTimer,
    Qt,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QWidget,
)

from app.filter_preferences import ProjectFilterPreferences
from app.filters import ProjectFilterRepository
from app.models import CanFrame
from app.static_active_filters import StaticCombinedActiveFilterSet

from .grouped_frame_model import GroupedFrameTableModel
from .logical_filter_integration import (
    LogicalFilterScanResult,
    LogicalFilterScanTask,
    LogicalMessageFilterProxy,
)
from .logical_message_model import format_logical_message_inspector
from .static_live_filter_tasks import (
    StaticLiveFilterScanTask,
    StaticLiveIncrementalFilterTask,
)

if TYPE_CHECKING:
    from .live_capture import LiveCaptureWidget


LIVE_FRAME_CAPACITY = 250_000
LIVE_MESSAGE_CAPACITY = 100_000
INCREMENTAL_FILTER_BATCH_SIZE = 4_096
INCREMENTAL_FILTER_DELAY_MS = 10
STREAM_FILTER_VIEW_CAPACITY = 5_000


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
        self._preferences = ProjectFilterPreferences(widget.project.database_path)
        self.filter_set = StaticCombinedActiveFilterSet((), scope="live")
        self.filter_enabled = False
        self.filter_ready = False
        self.filter_scanning = False
        self._signature: tuple[object, ...] = self.filter_set.signature
        self._frames: list[CanFrame] = []

    def sourceModel(self):  # noqa: N802
        """Compatibility accessor for code that inspects the backing frame model."""

        return self.widget.frame_model

    def reload_project_filters(self) -> bool:
        """Re-read Live presets and the project's include combination mode.

        Returns True when the effective filter set changed.
        """

        repository = ProjectFilterRepository(self.widget.project.database_path)
        candidate = StaticCombinedActiveFilterSet(
            repository.list_presets(),
            scope="live",
            combination_mode=self._preferences.combination_mode(),
        )
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

    def restart_on_empty_source(self) -> None:
        """Show an empty, ready filtered view that grows from new frames only."""

        self.beginResetModel()
        self.filter_scanning = False
        self.filter_ready = True
        self._frames.clear()
        self.endResetModel()

    def append_accepted_frames(self, frames: tuple[CanFrame, ...]) -> None:
        if not frames or not self.filter_enabled or not self.filter_ready:
            return
        overflow = max(0, len(self._frames) + len(frames) - LIVE_FRAME_CAPACITY)
        if overflow:
            trim_chunk = max(1, LIVE_FRAME_CAPACITY // 10)
            self._remove_front(min(len(self._frames), max(overflow, trim_chunk)))
        first_row = len(self._frames)
        self.beginInsertRows(QModelIndex(), first_row, first_row + len(frames) - 1)
        self._frames.extend(frames)
        self.endInsertRows()

    def trim_to(self, capacity: int) -> bool:
        """Drop the oldest accepted frames above ``capacity`` in 10% chunks."""

        overflow = len(self._frames) - capacity
        if overflow <= 0:
            return False
        trim_chunk = max(1, capacity // 10)
        self._remove_front(min(len(self._frames), max(overflow, trim_chunk)))
        return True

    def prune_before(self, first_sequence: int) -> None:
        if not self._frames:
            return
        remove_count = 0
        for frame in self._frames:
            if int(frame.sequence) >= first_sequence:
                break
            remove_count += 1
        self._remove_front(remove_count)

    def _remove_front(self, count: int) -> None:
        if count <= 0:
            return
        self.beginRemoveRows(QModelIndex(), 0, count - 1)
        del self._frames[:count]
        self.endRemoveRows()


class LiveFilterIntegration(QObject):
    """Opt-in project filters and List/Grouped presentation for Live views.

    While capture is stopped, the full GUI buffer is re-filtered in background
    workers. While capture is running, enabling or changing filters resets only
    the presentation models and the filtered view grows from that moment on;
    the sequence cursors owned by ``LiveCaptureWidget``, ``CaptureService``, its
    bounded buffers and the persistent session writers are not touched.
    """

    def __init__(self, widget: LiveCaptureWidget) -> None:
        super().__init__(widget)
        self.widget = widget
        self._frame_generation = 0
        self._message_generation = 0
        self._frame_tasks: list[StaticLiveFilterScanTask] = []
        self._incremental_tasks: list[StaticLiveIncrementalFilterTask] = []
        self._message_tasks: list[LogicalFilterScanTask] = []
        self._pending_frames: deque[CanFrame] = deque(maxlen=LIVE_FRAME_CAPACITY)
        self._incremental_running_generation: int | None = None
        self._stream_reset_in_progress = False
        self._streaming_filter_view = False
        self._grouped_view_enabled = False
        self._frame_display_filtered = False

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

        self.raw_grouped_model = GroupedFrameTableModel(widget)
        self.filtered_grouped_model = GroupedFrameTableModel(widget)
        widget.grouped_frame_model = self.raw_grouped_model
        widget.live_grouped_filter_model = self.filtered_grouped_model
        widget.frame_model.modelReset.connect(self._rebuild_raw_grouped_model)
        widget.frame_model.rowsInserted.connect(self._raw_rows_inserted)
        self.proxy.modelReset.connect(self._rebuild_filtered_grouped_model)
        self.proxy.rowsInserted.connect(self._filtered_rows_inserted)

        self.checkbox = QCheckBox("Zastosuj filtry")
        self.checkbox.setObjectName("applyLiveFilters")
        self.checkbox.setChecked(False)
        self.checkbox.setToolTip(
            "Filtry projektu są domyślnie wyłączone dla Live. Zaznacz, aby zastosować "
            "aktywne presety do surowych ramek i wiadomości logicznych."
        )
        self.checkbox.toggled.connect(self._set_filter_application)
        widget.apply_live_filters = self.checkbox

        self.active_filter_label = QLabel()
        self.active_filter_label.setObjectName("activeLiveFilterNames")
        widget.active_live_filter_label = self.active_filter_label

        widget.filter_controls.addWidget(self.checkbox)
        widget.filter_controls.addWidget(self.active_filter_label)
        widget.view_mode_controls.addWidget(self._build_view_mode_controls())

        self._reload_timer = QTimer(widget)
        self._reload_timer.setInterval(750)
        self._reload_timer.timeout.connect(self._reload_and_update)
        self._reload_timer.start()

        self._incremental_timer = QTimer(widget)
        self._incremental_timer.setSingleShot(True)
        self._incremental_timer.setInterval(INCREMENTAL_FILTER_DELAY_MS)
        self._incremental_timer.timeout.connect(self._start_incremental_scan)

        self._rebuild_raw_grouped_model()
        self._rebuild_filtered_grouped_model()
        self._reload_and_update()

    # ------------------------------------------------------------ public API

    def selected_frame(self) -> CanFrame | None:
        rows = self.widget.frame_table.selectionModel().selectedRows()
        if not rows:
            return None
        model = self.widget.frame_table.model()
        frame_at = getattr(model, "frame_at", None)
        if callable(frame_at):
            return frame_at(rows[0].row())
        return self.widget.frame_model.frame_at(rows[0].row())

    def update_status(
        self,
        total_received: int,
        logical_total: int | None = None,
    ) -> None:
        self._update_live_counts(total_received, logical_total)

    # ---------------------------------------------------- filter application

    def _set_filter_application(self, checked: bool) -> None:
        if self.widget.is_capturing:
            self._apply_streaming_filters(checked)
        else:
            self._streaming_filter_view = False
            self._apply_buffered_filters(checked)
        self._update_filter_control()
        self._update_live_counts()

    def _apply_buffered_filters(self, checked: bool) -> None:
        """Stopped capture: re-filter the whole retained GUI buffer in the background."""

        if not checked:
            # Detach filtered presentation models before clearing their state.
            self._set_frame_display_model(False)
            self._set_message_display_model(False)
        applied = bool(checked and self.proxy.filter_set.active_count)
        self.proxy.set_filter_enabled(applied and self.proxy.filter_set.affects_raw_visibility)
        self.message_proxy.set_filter_enabled(applied and self.proxy.filter_set.affects_visibility)
        if applied:
            names = ", ".join(self.proxy.filter_set.active_names)
            self.widget.output_message.emit(
                f"Filtry Live włączone — obliczam widok w tle: {names}"
            )
            if self.proxy.filter_enabled:
                self._schedule_frame_scan()
            else:
                self._set_frame_display_model(False)
            if self.message_proxy.filter_enabled:
                self._schedule_message_scan()
            else:
                self._set_message_display_model(False)
        else:
            self._frame_generation += 1
            self._message_generation += 1
            self._stop_incremental_filtering()
            if checked and not self.proxy.filter_set.active_count:
                self.checkbox.setChecked(False)
            self.widget.output_message.emit(
                "Filtry Live wyłączone — pokazuję pełne bufory ramek i wiadomości"
            )

    def _apply_streaming_filters(self, checked: bool) -> None:
        """Active capture: the filtered view starts empty and follows new traffic."""

        if not checked:
            self._set_frame_display_model(False)
            self._set_message_display_model(False)

        applied = bool(checked and self.proxy.filter_set.active_count)
        self.proxy.set_filter_enabled(
            applied and self.proxy.filter_set.affects_raw_visibility
        )
        self.message_proxy.set_filter_enabled(
            applied and self.proxy.filter_set.affects_visibility
        )
        self._streaming_filter_view = applied
        self._reset_streaming_presentation()

        if applied:
            names = ", ".join(self.proxy.filter_set.active_names)
            self.widget.output_message.emit(
                f"Filtry Live włączone od bieżącego momentu: {names}"
            )
        elif checked:
            self.widget.output_message.emit(
                "Filtry Live oczekują — brak aktywnych presetów; "
                "pierwszy ponownie aktywowany preset zostanie zastosowany automatycznie"
            )
        else:
            self.widget.output_message.emit(
                "Filtry Live wyłączone — widok od bieżącego momentu pokazuje wszystkie ramki"
            )

    def _reload_and_update(self) -> None:
        changed = self.proxy.reload_project_filters()
        logical_changed = self.message_proxy.set_filter_set(self.proxy.filter_set)

        if not self.widget.is_capturing:
            self._reload_stopped_view(changed, logical_changed)
        else:
            self._reload_streaming_view(changed, logical_changed)

        self._update_filter_control()
        self._update_live_counts()

    def _reload_stopped_view(self, changed: bool, logical_changed: bool) -> None:
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
            self._stop_incremental_filtering()
            return

        if not (changed or logical_changed) or not self.checkbox.isChecked():
            return
        self._set_frame_display_model(False)
        self._set_message_display_model(False)
        self.proxy.set_filter_enabled(self.proxy.filter_set.affects_raw_visibility)
        self.message_proxy.set_filter_enabled(self.proxy.filter_set.affects_visibility)
        if self.proxy.filter_enabled:
            self._schedule_frame_scan()
        else:
            self._stop_incremental_filtering()
        if self.message_proxy.filter_enabled:
            self._schedule_message_scan()

    def _reload_streaming_view(self, changed: bool, logical_changed: bool) -> None:
        if self.proxy.filter_set.active_count == 0:
            was_filtering = bool(
                self.proxy.filter_enabled
                or self.message_proxy.filter_enabled
                or self._streaming_filter_view
            )
            self.proxy.set_filter_enabled(False)
            self.message_proxy.set_filter_enabled(False)
            if self.checkbox.isChecked() and (
                changed or logical_changed or was_filtering
            ):
                self._streaming_filter_view = False
                self._reset_streaming_presentation()
                self.widget.output_message.emit(
                    "Brak aktywnych presetów Live — pokazuję pełny strumień; "
                    "filtrowanie wznowi się automatycznie po aktywacji presetu"
                )
            return

        if not (changed or logical_changed) or not self.checkbox.isChecked():
            return
        self.proxy.set_filter_enabled(self.proxy.filter_set.affects_raw_visibility)
        self.message_proxy.set_filter_enabled(self.proxy.filter_set.affects_visibility)
        self._streaming_filter_view = True
        self._reset_streaming_presentation()
        self.widget.output_message.emit(
            "Zmieniono filtry Live — nowy widok obowiązuje od bieżącego momentu"
        )

    def _reset_streaming_presentation(self) -> None:
        """Reset only presentation models and preserve capture tail cursors."""

        self._frame_generation += 1
        self._message_generation += 1
        self._stop_incremental_filtering()
        self._set_frame_display_model(False)
        self._set_message_display_model(False)

        self._stream_reset_in_progress = True
        try:
            self.widget.frame_model.clear()
            self.widget.message_model.clear()
        finally:
            self._stream_reset_in_progress = False

        if self.proxy.filter_enabled:
            self.proxy.restart_on_empty_source()
            self._set_frame_display_model(True)

        if self.message_proxy.filter_enabled:
            self.message_proxy.restart_on_empty_source()
            self._set_message_display_model(True)

    def _stop_incremental_filtering(self) -> None:
        self._pending_frames.clear()
        self._incremental_running_generation = None
        self._incremental_timer.stop()

    # ------------------------------------------------------- source updates

    def _source_frame_model_reset(self) -> None:
        if self._stream_reset_in_progress:
            return
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
        self._pending_frames.extend(frames)
        if self.proxy.filter_ready and not self.proxy.filter_scanning:
            self._schedule_incremental_scan()

    def _source_message_model_reset(self) -> None:
        if self._stream_reset_in_progress:
            return
        if self.message_proxy.filter_enabled:
            self._schedule_message_scan()

    # ------------------------------------------------------- background scans

    def _schedule_frame_scan(self) -> None:
        if not self.proxy.filter_enabled:
            return
        self._frame_generation += 1
        generation = self._frame_generation
        frames = self.widget.frame_model.snapshot_frames()
        self._stop_incremental_filtering()
        self._set_frame_display_model(False)
        self.proxy.begin_background_scan()
        if not frames:
            self.proxy.apply_background_result((), -1)
            self._set_frame_display_model(True)
            self._update_filter_control()
            self._update_live_counts()
            return
        task = StaticLiveFilterScanTask(generation, frames, self.proxy.filter_set)
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

    def _schedule_incremental_scan(self) -> None:
        if (
            not self.proxy.filter_enabled
            or not self.proxy.filter_ready
            or self.proxy.filter_scanning
            or not self._pending_frames
            or self._incremental_running_generation is not None
        ):
            return
        if not self._incremental_timer.isActive():
            self._incremental_timer.start()

    def _start_incremental_scan(self) -> None:
        if (
            not self.proxy.filter_enabled
            or not self.proxy.filter_ready
            or self.proxy.filter_scanning
            or self._incremental_running_generation is not None
        ):
            return
        self._prune_frame_filter_cache()
        if not self._pending_frames:
            return

        batch_size = min(INCREMENTAL_FILTER_BATCH_SIZE, len(self._pending_frames))
        frames = tuple(self._pending_frames.popleft() for _ in range(batch_size))
        generation = self._frame_generation
        task = StaticLiveIncrementalFilterTask(
            generation,
            frames,
            self.proxy.filter_set,
        )
        self._incremental_running_generation = generation
        self._incremental_tasks.append(task)
        self._incremental_tasks = self._incremental_tasks[-3:]
        task.signals.completed.connect(self._incremental_scan_completed)
        task.signals.failed.connect(self._incremental_scan_failed)
        QThreadPool.globalInstance().start(task)

    def _incremental_scan_completed(
        self,
        generation: int,
        accepted_frames: object,
    ) -> None:
        if generation != self._frame_generation:
            return
        self._incremental_running_generation = None
        if not self.proxy.filter_enabled or not self.proxy.filter_ready:
            return
        result_frames = tuple(
            frame for frame in accepted_frames if isinstance(frame, CanFrame)
        )
        first = self.widget.frame_model.frame_at(0)
        if first is not None:
            first_sequence = int(first.sequence)
            result_frames = tuple(
                frame for frame in result_frames if int(frame.sequence) >= first_sequence
            )
        scrollbar = self.widget.frame_table.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 2
        self.proxy.append_accepted_frames(result_frames)
        if result_frames and self.widget.auto_scroll.isChecked() and was_at_bottom:
            self.widget.frame_table.scrollToBottom()
        self._incremental_tasks = self._incremental_tasks[-2:]
        self._update_live_counts()
        self._schedule_incremental_scan()

        # The streaming view only keeps a short tail of accepted frames.
        if (
            self._streaming_filter_view
            and generation == self._frame_generation
            and self.proxy.filter_enabled
            and self.proxy.filter_ready
            and self.proxy.trim_to(STREAM_FILTER_VIEW_CAPACITY)
        ):
            self._update_live_counts()

    def _incremental_scan_failed(self, generation: int, error: str) -> None:
        if generation != self._frame_generation:
            return
        self._incremental_running_generation = None
        self._disable_after_error(f"Błąd przyrostowego filtrowania ramek Live: {error}")

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
        while (
            self._pending_frames
            and int(self._pending_frames[0].sequence) <= evaluated_through_sequence
        ):
            self._pending_frames.popleft()
        self._prune_frame_filter_cache()
        self._set_frame_display_model(True)
        self._schedule_incremental_scan()
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
        self._stop_incremental_filtering()
        self.widget.output_message.emit(message)
        self._update_filter_control()
        self._update_live_counts()

    def _prune_frame_filter_cache(self, *_args: object) -> None:
        first = self.widget.frame_model.frame_at(0)
        if first is not None:
            first_sequence = int(first.sequence)
            self.proxy.prune_before(first_sequence)
            while (
                self._pending_frames
                and int(self._pending_frames[0].sequence) < first_sequence
            ):
                self._pending_frames.popleft()

    def _prune_message_filter_cache(self, *_args: object) -> None:
        self.message_proxy.prune_source_cache_if_needed(LIVE_MESSAGE_CAPACITY * 2)

    # ------------------------------------------------------- table bindings

    def _set_frame_display_model(self, filtered: bool) -> None:
        self._frame_display_filtered = bool(filtered)
        if self._grouped_view_enabled:
            target = (
                self.filtered_grouped_model if filtered else self.raw_grouped_model
            )
        else:
            target = self.proxy if filtered else self.widget.frame_model
        table = self.widget.frame_table
        if table.model() is target:
            return
        table.setModel(target)
        table.selectionModel().selectionChanged.connect(self.widget._frame_selected)

    def _set_message_display_model(self, filtered: bool) -> None:
        target = self.message_proxy if filtered else self.widget.message_model
        if self.widget.message_table.model() is target:
            return
        self.widget.message_table.setModel(target)
        callback = self._message_selected if filtered else self.widget._message_selected
        self.widget.message_table.selectionModel().selectionChanged.connect(callback)

    def _synchronize_display_models(self) -> None:
        """Keep table bindings consistent with the counters shown to the user."""

        self._set_frame_display_model(
            self.proxy.filter_enabled and self.proxy.filter_ready
        )
        self._set_message_display_model(
            self.message_proxy.filter_enabled and self.message_proxy.filter_ready
        )

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

    # ------------------------------------------------------- grouped by ID

    def _build_view_mode_controls(self) -> QWidget:
        controls = QWidget(self.widget)
        controls.setObjectName("rawFrameViewControls")
        row = QHBoxLayout(controls)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(QLabel("Widok:"))

        list_button = QRadioButton("Lista")
        list_button.setObjectName("rawFrameListView")
        list_button.setToolTip(
            "Każda odebrana ramka CAN jest wyświetlana jako osobny wiersz."
        )
        grouped_button = QRadioButton("Grupuj po ID")
        grouped_button.setObjectName("rawFrameGroupedView")
        grouped_button.setToolTip(
            "Jeden stabilny wiersz dla każdego kanału, formatu STD/EXT i CAN ID. "
            "Nowsza ramka aktualizuje czas, sekwencję, DLC, dane oraz flagi."
        )

        button_group = QButtonGroup(controls)
        button_group.setExclusive(True)
        button_group.addButton(list_button)
        button_group.addButton(grouped_button)
        list_button.setChecked(True)
        grouped_button.toggled.connect(self._set_grouped_view_enabled)

        row.addWidget(list_button)
        row.addWidget(grouped_button)

        self.widget.raw_frame_view_controls = controls
        self.widget.raw_frame_view_group = button_group
        self.widget.raw_frame_list_view = list_button
        self.widget.raw_frame_grouped_view = grouped_button
        return controls

    def _set_grouped_view_enabled(self, enabled: bool) -> None:
        self._grouped_view_enabled = bool(enabled)
        self._set_frame_display_model(self._frame_display_filtered)
        self._update_live_counts()

    def _rebuild_raw_grouped_model(self) -> None:
        self.raw_grouped_model.replace_frames(
            self.widget.frame_model.snapshot_frames()
        )

    def _raw_rows_inserted(self, _parent, first: int, last: int) -> None:
        self.raw_grouped_model.append_frames(
            _frames_from_model(self.widget.frame_model, first, last)
        )

    def _rebuild_filtered_grouped_model(self) -> None:
        if not self.proxy.filter_enabled or not self.proxy.filter_ready:
            self.filtered_grouped_model.clear()
            return
        self.filtered_grouped_model.replace_frames(
            _frames_from_model(self.proxy, 0, self.proxy.rowCount() - 1)
        )

    def _filtered_rows_inserted(self, _parent, first: int, last: int) -> None:
        if not self.proxy.filter_enabled or not self.proxy.filter_ready:
            return
        self.filtered_grouped_model.append_frames(
            _frames_from_model(self.proxy, first, last)
        )

    # ---------------------------------------------------------- indicators

    def _update_filter_control(self) -> None:
        filter_set = self.proxy.filter_set
        count = filter_set.active_count
        names = ", ".join(filter_set.active_names)
        checked = self.checkbox.isChecked()
        capturing = self.widget.is_capturing

        self.checkbox.setText(f"Zastosuj filtry ({count})" if count else "Zastosuj filtry")
        # While capturing, keep a checked control enabled without presets: the
        # user's intent is preserved and they can still cancel it explicitly.
        self.checkbox.setEnabled(count > 0 or (capturing and checked))
        if count and capturing and checked:
            tooltip = (
                f"Filtry Live: WŁĄCZONE. Aktywne presety: {names}. "
                "Widok działa strumieniowo od momentu aktywacji; pełny zapis sesji trwa nadal."
            )
        elif count:
            scanning = (
                self.proxy.filter_scanning
                or self.message_proxy.filter_scanning
                or self._incremental_running_generation is not None
            )
            if scanning:
                state = "PRZELICZANIE"
            else:
                state = "WŁĄCZONE" if checked else "WYŁĄCZONE"
            tooltip = (
                f"Filtry Live: {state}. Aktywne presety: {names}. "
                "Pełne przeliczenie ramek i wiadomości odbywa się poza wątkiem GUI."
            )
        elif capturing and checked:
            tooltip = (
                "Filtry Live: OCZEKIWANIE. Brak aktywnych presetów. "
                "Pierwszy aktywowany preset zostanie zastosowany automatycznie."
            )
        else:
            tooltip = "Brak aktywnych presetów przeznaczonych dla Live Capture."
        self.checkbox.setToolTip(tooltip)

        mode = filter_set.combination_mode.value.upper()
        if checked and names:
            text = f"Filtry: {names} | Include: {mode}"
        elif checked:
            text = f"Filtry: oczekiwanie na preset | Include: {mode}"
        elif names:
            text = f"{names} | zastosowanie Live: WYŁĄCZONE | Include: {mode}"
        else:
            text = f"Filtry: brak aktywnych presetów | Include: {mode}"
        self.active_filter_label.setText(text)

    def _update_live_counts(
        self,
        total_received: int | None = None,
        logical_total: int | None = None,
    ) -> None:
        self._synchronize_display_models()

        retained = self.widget.frame_model.frame_count
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

        if self._grouped_view_enabled:
            grouped = (
                self.filtered_grouped_model
                if self._frame_display_filtered
                else self.raw_grouped_model
            )
            visible_groups = grouped.rowCount()
            suffix = " (przeliczanie filtrów)" if self.proxy.filter_scanning else ""
            self.widget.visible_label.setText(
                (
                    f"Widoczne ID: {visible_groups:,} / bufor {retained:,}{suffix}"
                ).replace(",", " ")
            )
            self.widget.data_tabs.setTabText(
                self.widget.raw_tab_index,
                (
                    f"Surowe ramki — grupy ID "
                    f"({visible_groups:,}/{total_received:,})"
                ).replace(",", " "),
            )
        else:
            visible = (
                self.proxy.rowCount()
                if self.proxy.filter_enabled and self.proxy.filter_ready
                else retained
            )
            frame_suffix = " (przeliczanie)" if self.proxy.filter_scanning else ""
            self.widget.visible_label.setText(
                (f"Widoczne: {visible:,} / bufor {retained:,}{frame_suffix}").replace(",", " ")
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


def _frames_from_model(model, first: int, last: int) -> tuple[CanFrame, ...]:
    if first < 0 or last < first:
        return ()
    frame_at = getattr(model, "frame_at", None)
    if not callable(frame_at):
        return ()
    frames: list[CanFrame] = []
    for row in range(first, last + 1):
        frame = frame_at(row)
        if isinstance(frame, CanFrame):
            frames.append(frame)
    return tuple(frames)


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
