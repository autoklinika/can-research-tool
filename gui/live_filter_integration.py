from __future__ import annotations

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, QTimer
from PySide6.QtWidgets import QCheckBox, QLayout

from app.filters import CanFrameRecord, ProjectFilterRepository
from app.live_filters import ActiveFilterSet

from .live_capture import LiveCaptureWidget


_installed = False
_original_init = LiveCaptureWidget.__init__
_original_update_status = LiveCaptureWidget._update_status
_original_frame_selected = LiveCaptureWidget._frame_selected


class LiveFrameFilterProxy(QSortFilterProxyModel):
    """Filter only the Live table; capture and source buffer always keep raw frames."""

    def __init__(self, widget: LiveCaptureWidget) -> None:
        super().__init__(widget)
        self.widget = widget
        self.filter_set = ActiveFilterSet((), scope="live")
        self.filter_enabled = False
        self._signature: tuple[object, ...] = self.filter_set.signature
        self.setDynamicSortFilter(True)

    def reload_project_filters(self) -> bool:
        repository = ProjectFilterRepository(self.widget.project.database_path)
        candidate = ActiveFilterSet(repository.list_presets(), scope="live")
        if candidate.signature == self._signature:
            return False
        self.filter_set = candidate
        self._signature = candidate.signature
        self.invalidateFilter()
        return True

    def set_filter_enabled(self, enabled: bool) -> None:
        normalized = bool(enabled and self.filter_set.active_count)
        if normalized == self.filter_enabled:
            return
        self.filter_enabled = normalized
        self.invalidateFilter()

    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QModelIndex,
    ) -> bool:  # noqa: N802
        if not self.filter_enabled:
            return True
        frame = self.widget.frame_model.frame_at(source_row)
        if frame is None:
            return False
        decision = self.filter_set.decide(
            CanFrameRecord(
                can_id=int(frame.arbitration_id),
                extended=bool(frame.is_extended_id),
                dlc=int(frame.dlc),
                relative_time_us=int(frame.timestamp_ns // 1_000),
                channel=int(frame.channel),
            )
        )
        return decision.visible


def install_live_filter_integration() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    def integrated_init(self: LiveCaptureWidget, *args, **kwargs) -> None:
        _original_init(self, *args, **kwargs)

        self.live_filter_proxy = LiveFrameFilterProxy(self)
        self.live_filter_proxy.setSourceModel(self.frame_model)
        self.frame_table.setModel(self.live_filter_proxy)
        self.frame_table.selectionModel().selectionChanged.connect(self._frame_selected)

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
        self._live_filter_reload_timer.setInterval(200)
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
    else:
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
        proxy.set_filter_enabled(False)
    elif changed and widget.apply_live_filters.isChecked():
        proxy.set_filter_enabled(True)
    _update_filter_control(widget)
    _update_live_counts(widget)


def _update_filter_control(widget: LiveCaptureWidget) -> None:
    proxy = widget.live_filter_proxy
    count = proxy.filter_set.active_count
    checkbox = widget.apply_live_filters
    checkbox.setEnabled(count > 0)
    checkbox.setText(f"Zastosuj filtry ({count})" if count else "Zastosuj filtry")
    if count:
        names = ", ".join(proxy.filter_set.active_names)
        state = "WŁĄCZONE" if proxy.filter_enabled else "WYŁĄCZONE"
        checkbox.setToolTip(
            f"Filtry Live: {state}. Aktywne presety dla Live: {names}. "
            "Niezaznaczony checkbox zawsze pokazuje cały surowy bufor."
        )
    else:
        checkbox.setToolTip("Brak aktywnych presetów przeznaczonych dla Live Capture.")


def _update_live_counts(widget: LiveCaptureWidget, total_received: int | None = None) -> None:
    proxy = widget.live_filter_proxy
    visible = proxy.rowCount()
    retained = widget.frame_model.frame_count
    widget.visible_label.setText(
        f"Widoczne: {visible:,} / bufor {retained:,}".replace(",", " ")
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
