from __future__ import annotations

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, QTimer
from PySide6.QtWidgets import QLabel

from app.filters import CanFrameRecord, ProjectFilterRepository
from app.live_filters import ActiveFilterSet

from .live_capture import LiveCaptureWidget


_installed = False
_original_init = LiveCaptureWidget.__init__
_original_update_status = LiveCaptureWidget._update_status
_original_frame_selected = LiveCaptureWidget._frame_selected


class LiveFrameFilterProxy(QSortFilterProxyModel):
    """Filters only the Live Capture table; the source model retains every frame."""

    def __init__(self, widget: LiveCaptureWidget) -> None:
        super().__init__(widget)
        self.widget = widget
        self.filter_set = ActiveFilterSet(())
        self._signature: tuple[object, ...] = ()
        self.setDynamicSortFilter(True)

    def reload_project_filters(self) -> bool:
        repository = ProjectFilterRepository(self.widget.project.database_path)
        candidate = ActiveFilterSet(repository.list_presets())
        if candidate.signature == self._signature:
            return False
        self.filter_set = candidate
        self._signature = candidate.signature
        self.invalidateFilter()
        return True

    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QModelIndex,
    ) -> bool:  # noqa: N802
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

        self.live_filter_label = QLabel()
        self.live_filter_label.setObjectName("liveFilterStatus")
        self.live_filter_label.setStyleSheet(
            "QLabel { padding: 5px 9px; border: 1px solid palette(mid); font-weight: 600; }"
        )
        self.layout().insertWidget(1, self.live_filter_label)

        self._live_filter_reload_timer = QTimer(self)
        self._live_filter_reload_timer.setInterval(500)
        self._live_filter_reload_timer.timeout.connect(
            lambda: _reload_and_update(self)
        )
        self._live_filter_reload_timer.start()
        _reload_and_update(self)

    def integrated_update_status(self: LiveCaptureWidget, status) -> None:
        _original_update_status(self, status)
        proxy = getattr(self, "live_filter_proxy", None)
        if proxy is None:
            return
        visible = proxy.rowCount()
        retained = self.frame_model.frame_count
        self.visible_label.setText(
            f"Widoczne: {visible:,} / bufor {retained:,}".replace(",", " ")
        )
        self.data_tabs.setTabText(
            self.raw_tab_index,
            f"Surowe ramki ({visible:,}/{status.frame_count:,})".replace(",", " "),
        )

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


def _reload_and_update(widget: LiveCaptureWidget) -> None:
    proxy = widget.live_filter_proxy
    proxy.reload_project_filters()
    count = proxy.filter_set.active_count
    save_text = _save_status_text(widget)
    if count:
        invalid = len(proxy.filter_set.validation_issues)
        suffix = f" | błędne: {invalid}" if invalid else ""
        widget.live_filter_label.setText(
            f"Filtr widoku aktywny: {count}{suffix} | {save_text}"
        )
    else:
        widget.live_filter_label.setText(
            f"Filtr widoku: wyłączony | {save_text}"
        )
    widget.visible_label.setText(
        f"Widoczne: {proxy.rowCount():,} / bufor {widget.frame_model.frame_count:,}".replace(",", " ")
    )


def _save_status_text(widget: LiveCaptureWidget) -> str:
    if widget._capture.is_active:
        return (
            "Zapis: wszystkie ramki"
            if widget._capture.status().persist_to_disk
            else "Zapis: WYŁĄCZONY"
        )
    button = getattr(widget, "save_session_button", None)
    if button is not None and button.isChecked():
        return "Zapis następnej sesji: UZBROJONY"
    return "Zapis następnej sesji: wyłączony"
