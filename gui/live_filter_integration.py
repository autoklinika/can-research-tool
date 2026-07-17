from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QModelIndex,
    QObject,
    QRunnable,
    QSortFilterProxyModel,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtWidgets import QCheckBox, QLayout

from app.filters import CanFrameRecord, ProjectFilterRepository
from app.live_filters import ActiveFilterSet
from app.models import CanFrame

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
            accepted: set[int] = set()
            evaluated_through = -1
            for frame in self.frames:
                if self.filter_set.decide(_frame_record(frame)).visible:
                    accepted.add(frame.sequence)
                evaluated_through = max(evaluated_through, frame.sequence)
            self.signals.completed.emit(
                self.generation,
                accepted,
                evaluated_through,
            )
        except Exception as exc:
            self.signals.failed.emit(self.generation, str(exc))


class LiveFrameFilterProxy(QSortFilterProxyModel):
    """Filter only the Live table; capture and source buffer keep raw frames."""

    def __init__(self, widget: LiveCaptureWidget) -> None:
        super().__init__(widget)
        self.widget = widget
        self.filter_set = ActiveFilterSet((), scope="live")
        self.filter_enabled = False
        self.filter_ready = False
        self.filter_scanning = False
        self._signature: tuple[object, ...] = self.filter_set.signature
        self._accepted_sequences: set[int] = set()
        self._evaluated_through_sequence = -1
        self.setDynamicSortFilter(True)

    def reload_project_filters(self) -> bool:
        repository = ProjectFilterRepository(self.widget.project.database_path)
        candidate = ActiveFilterSet(repository.list_presets(), scope="live")
        if candidate.signature == self._signature:
            return False
        self.filter_set = candidate
        self._signature = candidate.signature
        return True

    def set_filter_enabled(self, enabled: bool) -> None:
        normalized = bool(enabled and self.filter_set.active_count)
        if normalized == self.filter_enabled:
            return
        self.filter_enabled = normalized
        if not normalized:
            self.filter_ready = False
            self.filter_scanning = False
            self._accepted_sequences.clear()
            self._evaluated_through_sequence = -1
        self.invalidateFilter()

    def begin_background_scan(self) -> None:
        if not self.filter_enabled:
            return
        self.filter_scanning = True
        self.filter_ready = False
        self._accepted_sequences.clear()
        self._evaluated_through_sequence = -1
        self.invalidateFilter()

    def apply_background_result(
        self,
        accepted_sequences: set[int],
        evaluated_through_sequence: int,
    ) -> None:
        if not self.filter_enabled:
            return
        self._accepted_sequences = accepted_sequences
        self._evaluated_through_sequence = evaluated_through_sequence
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
        frame = self.widget.frame_model.frame_at(source_row)
        if frame is None:
            return False

        sequence = int(frame.sequence)
        if sequence <= self._evaluated_through_sequence:
            return sequence in self._accepted_sequences

        visible = self.filter_set.decide(_frame_record(frame)).visible
        self._evaluated_through_sequence = sequence
        if visible:
            self._accepted_sequences.add(sequence)
        return visible

    def prune_before(self, first_sequence: int) -> None:
        if len(self._accepted_sequences) <= LIVE_FRAME_CAPACITY * 2:
            return
        self._accepted_sequences = {
            sequence
            for sequence in self._accepted_sequences
            if sequence >= first_sequence
        }


class LiveFilterIntegration(QObject):
    """Explicitly compose Live filtering into an already-built capture widget."""

    def __init__(self, widget: LiveCaptureWidget) -> None:
        super().__init__(widget)
        self.widget = widget
        self._generation = 0
        self._tasks: list[LiveFilterScanTask] = []

        self.proxy = LiveFrameFilterProxy(widget)
        self.proxy.setSourceModel(widget.frame_model)
        widget.live_filter_proxy = self.proxy
        widget.frame_table.setModel(self.proxy)
        widget.frame_table.selectionModel().selectionChanged.connect(
            widget._frame_selected
        )
        widget.frame_model.modelReset.connect(self._source_model_reset)
        widget.frame_model.rowsRemoved.connect(self._prune_filter_cache)

        self.checkbox = QCheckBox("Zastosuj filtry")
        self.checkbox.setObjectName("applyLiveFilters")
        self.checkbox.setChecked(False)
        self.checkbox.setToolTip(
            "Filtry projektu są domyślnie wyłączone dla Live. Zaznacz, aby zastosować "
            "aktywne presety przeznaczone dla Live Capture."
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
        source_index = self.proxy.mapToSource(rows[0])
        return self.widget.frame_model.frame_at(source_index.row())

    def update_status(self, total_received: int) -> None:
        self._update_live_counts(total_received)

    def _set_filter_application(self, checked: bool) -> None:
        self.proxy.set_filter_enabled(checked)
        if checked and self.proxy.filter_enabled:
            names = ", ".join(self.proxy.filter_set.active_names)
            self.widget.output_message.emit(f"Filtry Live włączone: {names}")
            self._schedule_filter_scan()
        else:
            self._generation += 1
            if checked and not self.proxy.filter_set.active_count:
                self.checkbox.setChecked(False)
            self.widget.output_message.emit(
                "Filtry Live wyłączone — pokazuję cały bufor surowych ramek"
            )
        self._update_filter_control()
        self._update_live_counts()

    def _reload_and_update(self) -> None:
        changed = self.proxy.reload_project_filters()
        if self.proxy.filter_set.active_count == 0:
            if self.checkbox.isChecked():
                self.checkbox.blockSignals(True)
                self.checkbox.setChecked(False)
                self.checkbox.blockSignals(False)
            self._generation += 1
            self.proxy.set_filter_enabled(False)
        elif changed and self.checkbox.isChecked():
            self._schedule_filter_scan()
        self._update_filter_control()
        self._update_live_counts()

    def _source_model_reset(self) -> None:
        if self.proxy.filter_enabled:
            self._schedule_filter_scan()

    def _schedule_filter_scan(self) -> None:
        if not self.proxy.filter_enabled:
            return

        self._generation += 1
        generation = self._generation
        frames = self.widget.frame_model.snapshot_frames()
        self.proxy.begin_background_scan()

        if not frames:
            self.proxy.apply_background_result(set(), -1)
            self._update_filter_control()
            self._update_live_counts()
            return

        task = LiveFilterScanTask(generation, frames, self.proxy.filter_set)
        self._tasks.append(task)
        self._tasks = self._tasks[-3:]
        task.signals.completed.connect(self._filter_scan_completed)
        task.signals.failed.connect(self._filter_scan_failed)
        QThreadPool.globalInstance().start(task)
        self._update_filter_control()

    def _filter_scan_completed(
        self,
        generation: int,
        accepted_sequences: object,
        evaluated_through_sequence: int,
    ) -> None:
        if generation != self._generation or not self.proxy.filter_enabled:
            return
        self.proxy.apply_background_result(
            set(accepted_sequences),
            evaluated_through_sequence,
        )
        self._tasks = self._tasks[-2:]
        self._update_filter_control()
        self._update_live_counts()

    def _filter_scan_failed(self, generation: int, error: str) -> None:
        if generation != self._generation:
            return
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(False)
        self.checkbox.blockSignals(False)
        self.proxy.set_filter_enabled(False)
        self.widget.output_message.emit(f"Błąd filtrowania Live: {error}")
        self._update_filter_control()
        self._update_live_counts()

    def _prune_filter_cache(self, *_args: object) -> None:
        first = self.widget.frame_model.frame_at(0)
        if first is not None:
            self.proxy.prune_before(int(first.sequence))

    def _update_filter_control(self) -> None:
        count = self.proxy.filter_set.active_count
        self.checkbox.setEnabled(count > 0)
        self.checkbox.setText(
            f"Zastosuj filtry ({count})" if count else "Zastosuj filtry"
        )
        if count:
            names = ", ".join(self.proxy.filter_set.active_names)
            if self.proxy.filter_scanning:
                state = "PRZELICZANIE"
            else:
                state = "WŁĄCZONE" if self.proxy.filter_enabled else "WYŁĄCZONE"
            self.checkbox.setToolTip(
                f"Filtry Live: {state}. Aktywne presety dla Live: {names}. "
                "Pełne przeliczenie bufora odbywa się poza wątkiem GUI."
            )
        else:
            self.checkbox.setToolTip(
                "Brak aktywnych presetów przeznaczonych dla Live Capture."
            )

    def _update_live_counts(self, total_received: int | None = None) -> None:
        visible = self.proxy.rowCount()
        retained = self.widget.frame_model.frame_count
        suffix = " (przeliczanie)" if self.proxy.filter_scanning else ""
        self.widget.visible_label.setText(
            (f"Widoczne: {visible:,} / bufor {retained:,}{suffix}").replace(",", " ")
        )
        if total_received is None:
            try:
                total_received = self.widget._controller.status().frame_count
            except Exception:
                total_received = retained
        self.widget.data_tabs.setTabText(
            self.widget.raw_tab_index,
            f"Surowe ramki ({visible:,}/{total_received:,})".replace(",", " "),
        )


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
