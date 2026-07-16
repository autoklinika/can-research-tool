from __future__ import annotations

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

from .live_capture import LiveCaptureWidget


LIVE_FRAME_CAPACITY = 250_000
LIVE_MESSAGE_CAPACITY = 100_000

_installed = False
_original_init = LiveCaptureWidget.__init__
_original_update_status = LiveCaptureWidget._update_status
_original_frame_selected = LiveCaptureWidget._frame_selected


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
    """Filter only the Live table; capture and source buffer always keep raw frames.

    Full-buffer predicate evaluation is performed by ``LiveFilterScanTask``. Once
    the scan completes, Qt only performs O(1) sequence-number membership checks.
    New rows arriving after the snapshot are evaluated incrementally.
    """

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
        # During the scan the full raw buffer stays visible. This invalidation is
        # cheap because filterAcceptsRow returns immediately while filter_ready=False.
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


def install_live_filter_integration() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    # The old 20k/5k ring buffers made a high-frequency CAN ID dominate the
    # retained tail and look like a filter. Keep a substantially larger raw Live
    # history; disk persistence remains independently controlled by "Zapisz".
    LiveCaptureWidget.LIVE_CAPACITY = LIVE_FRAME_CAPACITY
    LiveCaptureWidget.LIVE_MESSAGE_CAPACITY = LIVE_MESSAGE_CAPACITY

    def integrated_init(self: LiveCaptureWidget, *args, **kwargs) -> None:
        _original_init(self, *args, **kwargs)

        self.live_filter_proxy = LiveFrameFilterProxy(self)
        self.live_filter_proxy.setSourceModel(self.frame_model)
        self.frame_table.setModel(self.live_filter_proxy)
        self.frame_table.selectionModel().selectionChanged.connect(self._frame_selected)
        self._live_filter_generation = 0
        self._live_filter_tasks: list[LiveFilterScanTask] = []
        self.frame_model.modelReset.connect(lambda: _source_model_reset(self))
        self.frame_model.rowsRemoved.connect(lambda *_args: _prune_filter_cache(self))

        self.apply_live_filters = QCheckBox("Zastosuj filtry")
        self.apply_live_filters.setObjectName("applyLiveFilters")
        self.apply_live_filters.setChecked(False)
        self.apply_live_filters.setToolTip(
            "Filtry projektu są domyślnie wyłączone dla Live. Zaznacz, aby zastosować "
            "aktywne presety przeznaczone dla Live Capture."
        )
        self.apply_live_filters.toggled.connect(
            lambda checked: _set_filter_application(self, checked)
        )
        controls = _find_layout_containing(self.layout(), self.auto_scroll)
        if controls is not None:
            controls.insertWidget(2, self.apply_live_filters)
        else:
            self.layout().insertWidget(1, self.apply_live_filters)

        self._live_filter_reload_timer = QTimer(self)
        self._live_filter_reload_timer.setInterval(750)
        self._live_filter_reload_timer.timeout.connect(lambda: _reload_and_update(self))
        self._live_filter_reload_timer.start()
        _reload_and_update(self)

    def integrated_update_status(self: LiveCaptureWidget, status) -> None:
        _original_update_status(self, status)
        _update_live_counts(self, status.frame_count)

    def integrated_frame_selected(self: LiveCaptureWidget) -> None:
        proxy = getattr(self, "live_filter_proxy", None)
        if proxy is None:
            _original_frame_selected(self)
            return
        rows = self.frame_table.selectionModel().selectedRows()
        if not rows:
            return
        source_index = proxy.mapToSource(rows[0])
        frame = self.frame_model.frame_at(source_index.row())
        if frame is None:
            return
        width = 8 if frame.is_extended_id else 3
        self.inspector_text.emit(
            "\n".join(
                (
                    "SUROWA RAMKA CAN",
                    "",
                    f"Czas: {frame.timestamp_ns / 1_000_000:.6f} ms",
                    f"Sekwencja: {frame.sequence}",
                    f"CAN ID: 0x{frame.arbitration_id:0{width}X}",
                    f"Typ: {'EXT' if frame.is_extended_id else 'STD'}",
                    f"DLC: {frame.dlc}",
                    f"Dane: {frame.data_hex}",
                    f"Kanał: {frame.channel}",
                    f"Flagi źródłowe: 0x{frame.source_flags:X}",
                )
            )
        )

    LiveCaptureWidget.__init__ = integrated_init
    LiveCaptureWidget._update_status = integrated_update_status
    LiveCaptureWidget._frame_selected = integrated_frame_selected


def _set_filter_application(widget: LiveCaptureWidget, checked: bool) -> None:
    proxy = widget.live_filter_proxy
    proxy.set_filter_enabled(checked)
    if checked and proxy.filter_enabled:
        names = ", ".join(proxy.filter_set.active_names)
        widget.output_message.emit(f"Filtry Live włączone: {names}")
        _schedule_filter_scan(widget)
    else:
        widget._live_filter_generation += 1
        if checked and not proxy.filter_set.active_count:
            widget.apply_live_filters.setChecked(False)
        widget.output_message.emit("Filtry Live wyłączone — pokazuję cały bufor surowych ramek")
    _update_filter_control(widget)
    _update_live_counts(widget)


def _reload_and_update(widget: LiveCaptureWidget) -> None:
    proxy = widget.live_filter_proxy
    changed = proxy.reload_project_filters()
    if proxy.filter_set.active_count == 0:
        if widget.apply_live_filters.isChecked():
            widget.apply_live_filters.blockSignals(True)
            widget.apply_live_filters.setChecked(False)
            widget.apply_live_filters.blockSignals(False)
        widget._live_filter_generation += 1
        proxy.set_filter_enabled(False)
    elif changed and widget.apply_live_filters.isChecked():
        _schedule_filter_scan(widget)
    _update_filter_control(widget)
    _update_live_counts(widget)


def _source_model_reset(widget: LiveCaptureWidget) -> None:
    if widget.live_filter_proxy.filter_enabled:
        _schedule_filter_scan(widget)


def _schedule_filter_scan(widget: LiveCaptureWidget) -> None:
    proxy = widget.live_filter_proxy
    if not proxy.filter_enabled:
        return

    widget._live_filter_generation += 1
    generation = widget._live_filter_generation
    frames = widget.frame_model.snapshot_frames()
    proxy.begin_background_scan()

    if not frames:
        proxy.apply_background_result(set(), -1)
        _update_filter_control(widget)
        _update_live_counts(widget)
        return

    task = LiveFilterScanTask(generation, frames, proxy.filter_set)
    widget._live_filter_tasks.append(task)
    widget._live_filter_tasks = widget._live_filter_tasks[-3:]
    task.signals.completed.connect(
        lambda completed_generation, accepted, evaluated: _filter_scan_completed(
            widget,
            completed_generation,
            accepted,
            evaluated,
        )
    )
    task.signals.failed.connect(
        lambda failed_generation, error: _filter_scan_failed(
            widget,
            failed_generation,
            error,
        )
    )
    QThreadPool.globalInstance().start(task)
    _update_filter_control(widget)


def _filter_scan_completed(
    widget: LiveCaptureWidget,
    generation: int,
    accepted_sequences: object,
    evaluated_through_sequence: int,
) -> None:
    if generation != widget._live_filter_generation:
        return
    if not widget.live_filter_proxy.filter_enabled:
        return
    accepted = set(accepted_sequences)
    widget.live_filter_proxy.apply_background_result(
        accepted,
        evaluated_through_sequence,
    )
    widget._live_filter_tasks = widget._live_filter_tasks[-2:]
    _update_filter_control(widget)
    _update_live_counts(widget)


def _filter_scan_failed(widget: LiveCaptureWidget, generation: int, error: str) -> None:
    if generation != widget._live_filter_generation:
        return
    widget.apply_live_filters.blockSignals(True)
    widget.apply_live_filters.setChecked(False)
    widget.apply_live_filters.blockSignals(False)
    widget.live_filter_proxy.set_filter_enabled(False)
    widget.output_message.emit(f"Błąd filtrowania Live: {error}")
    _update_filter_control(widget)
    _update_live_counts(widget)


def _prune_filter_cache(widget: LiveCaptureWidget) -> None:
    first = widget.frame_model.frame_at(0)
    if first is not None:
        widget.live_filter_proxy.prune_before(int(first.sequence))


def _update_filter_control(widget: LiveCaptureWidget) -> None:
    proxy = widget.live_filter_proxy
    count = proxy.filter_set.active_count
    checkbox = widget.apply_live_filters
    checkbox.setEnabled(count > 0)
    checkbox.setText(f"Zastosuj filtry ({count})" if count else "Zastosuj filtry")
    if count:
        names = ", ".join(proxy.filter_set.active_names)
        if proxy.filter_scanning:
            state = "PRZELICZANIE"
        else:
            state = "WŁĄCZONE" if proxy.filter_enabled else "WYŁĄCZONE"
        checkbox.setToolTip(
            f"Filtry Live: {state}. Aktywne presety dla Live: {names}. "
            "Pełne przeliczenie bufora odbywa się poza wątkiem GUI."
        )
    else:
        checkbox.setToolTip("Brak aktywnych presetów przeznaczonych dla Live Capture.")


def _update_live_counts(widget: LiveCaptureWidget, total_received: int | None = None) -> None:
    proxy = widget.live_filter_proxy
    visible = proxy.rowCount()
    retained = widget.frame_model.frame_count
    suffix = " (przeliczanie)" if proxy.filter_scanning else ""
    widget.visible_label.setText(
        (f"Widoczne: {visible:,} / bufor {retained:,}{suffix}").replace(",", " ")
    )
    if total_received is None:
        try:
            total_received = widget._capture.status().frame_count
        except Exception:
            total_received = retained
    widget.data_tabs.setTabText(
        widget.raw_tab_index,
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


def _find_layout_containing(layout: QLayout | None, target) -> QLayout | None:
    if layout is None:
        return None
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is target:
            return layout
        child = item.layout()
        found = _find_layout_containing(child, target)
        if found is not None:
            return found
    return None
