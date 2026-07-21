from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt, Slot
from PySide6.QtWidgets import QAbstractItemView, QPushButton

from app.markers import CaptureMarker

from .protocol_message_details import ProtocolMessageDetailsDialog
from .session_marker_window import SessionMarkerWindow
from .sqlite_logical_session_view import SqliteLogicalSessionViewWidget


class DetailedLogicalSessionViewWidget(SqliteLogicalSessionViewWidget):
    """Stored workspace with windowed marker navigation and message details."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._message_detail_windows: list[ProtocolMessageDetailsDialog] = []
        self._marker_window: SessionMarkerWindow | None = None
        self._pending_marker: CaptureMarker | None = None
        self.message_table.doubleClicked.connect(self._open_message_details)
        self._replace_marker_tab_with_window_button()

    def _replace_marker_tab_with_window_button(self) -> None:
        marker_page = self.marker_table.parentWidget()
        marker_index = self.tabs.indexOf(marker_page)
        if marker_index >= 0:
            self.tabs.removeTab(marker_index)
            marker_page.hide()

        marker_count = self.marker_model.rowCount()
        self.marker_window_button = QPushButton(f"Znaczniki ({marker_count})", self.tabs)
        self.marker_window_button.setObjectName("openSessionMarkerWindow")
        self.marker_window_button.setToolTip(
            "Otwórz znaczniki tej sesji w osobnym oknie nawigacyjnym."
        )
        self.marker_window_button.clicked.connect(self._open_marker_window)
        self.tabs.setCornerWidget(
            self.marker_window_button,
            Qt.Corner.TopRightCorner,
        )

    def _open_marker_window(self) -> None:
        window = self._marker_window
        if window is None:
            window = SessionMarkerWindow(self.path, parent=self.window())
            window.marker_activated.connect(self._navigate_to_marker)
            self._marker_window = window
        if window.isMinimized():
            window.showNormal()
        else:
            window.show()
        window.raise_()
        window.activateWindow()

    @Slot(object)
    def _navigate_to_marker(self, marker: CaptureMarker) -> None:
        self._show_marker_details(marker)
        if self.tabs.currentIndex() == self.message_tab_index:
            if not self._messages_ready:
                self._pending_marker = marker
                self._start_embedded_load()
                self.output_message.emit(
                    f"Znacznik '{marker.name}': oczekiwanie na wiadomości logiczne…"
                )
                return
            self._navigate_logical_to_marker(marker)
            return
        self._navigate_raw_to_marker(marker)

    def _navigate_raw_to_marker(self, marker: CaptureMarker) -> None:
        model = self.frame_table.model()
        frame_at = getattr(model, "frame_at", None)
        if not callable(frame_at):
            model = self.frame_model
            frame_at = model.frame_at
        count = int(model.rowCount())
        target_row = self._nearest_timestamp_row(count, frame_at, marker.timestamp_ns)
        if target_row is None:
            self.output_message.emit(
                f"Znacznik '{marker.name}': brak widocznej ramki w bieżącym widoku."
            )
            return

        index = model.index(target_row, 0)
        self.frame_table.selectRow(target_row)
        self.frame_table.setCurrentIndex(index)
        self.frame_table.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
        frame = frame_at(target_row)
        if frame is not None:
            delta_ms = (frame.timestamp_ns - marker.timestamp_ns) / 1_000_000
            self.output_message.emit(
                f"Znacznik '{marker.name}' → ramka {frame.sequence} "
                f"(różnica {delta_ms:+.3f} ms)"
            )

    def _navigate_logical_to_marker(self, marker: CaptureMarker) -> None:
        target_row = self._nearest_logical_row(marker.timestamp_ns)
        if target_row is None:
            self.output_message.emit(
                f"Znacznik '{marker.name}': brak widocznej wiadomości logicznej."
            )
            return

        index = self._display_model.index(target_row, 0)
        self.message_table.selectRow(target_row)
        self.message_table.setCurrentIndex(index)
        self.message_table.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
        message = self._display_model.message_at(target_row)
        if message is not None:
            delta_ms = (
                message.first_timestamp_ns - marker.timestamp_ns
            ) / 1_000_000
            self.output_message.emit(
                f"Znacznik '{marker.name}' → wiadomość logiczna "
                f"(różnica {delta_ms:+.3f} ms)"
            )

    def _nearest_logical_row(self, timestamp_ns: int) -> int | None:
        model = self._display_model
        connection = getattr(model, "_connection", None)
        if connection is None or model.rowCount() <= 0:
            return None

        visible_ids = getattr(model, "_visible_ids", None)
        if visible_ids is None:
            row = connection.execute(
                "SELECT id FROM messages "
                "ORDER BY ABS(first_timestamp_ns - ?) LIMIT 1",
                (int(timestamp_ns),),
            ).fetchone()
            return None if row is None else max(0, int(row[0]) - 1)

        identifiers = tuple(int(value) for value in visible_ids)
        if not identifiers:
            return None

        def timestamp_at(row_index: int) -> int | None:
            result = connection.execute(
                "SELECT first_timestamp_ns FROM messages WHERE id = ?",
                (identifiers[row_index],),
            ).fetchone()
            return None if result is None else int(result[0])

        low = 0
        high = len(identifiers)
        while low < high:
            middle = (low + high) // 2
            current = timestamp_at(middle)
            if current is None:
                return None
            if current < timestamp_ns:
                low = middle + 1
            else:
                high = middle

        candidates = [
            row for row in (low - 1, low) if 0 <= row < len(identifiers)
        ]
        timed = [
            (row, timestamp_at(row))
            for row in candidates
        ]
        timed = [(row, value) for row, value in timed if value is not None]
        if not timed:
            return None
        return min(timed, key=lambda item: abs(item[1] - timestamp_ns))[0]

    @staticmethod
    def _nearest_timestamp_row(count: int, item_at, timestamp_ns: int) -> int | None:
        if count <= 0:
            return None
        low = 0
        high = count
        while low < high:
            middle = (low + high) // 2
            item = item_at(middle)
            if item is None:
                return None
            if item.timestamp_ns < timestamp_ns:
                low = middle + 1
            else:
                high = middle
        candidates = [row for row in (low - 1, low) if 0 <= row < count]
        valid = [(row, item_at(row)) for row in candidates]
        valid = [(row, item) for row, item in valid if item is not None]
        if not valid:
            return None
        return min(
            valid,
            key=lambda entry: abs(entry[1].timestamp_ns - timestamp_ns),
        )[0]

    def _show_marker_details(self, marker: CaptureMarker) -> None:
        self.inspector_text.emit(
            "\n".join(
                (
                    "ZNACZNIK SESJI",
                    "",
                    f"Czas: {marker.timestamp_ns / 1_000_000:.6f} ms",
                    f"Nazwa: {marker.name}",
                    f"Skrót: {marker.shortcut}",
                    f"Obszar: {marker.area or '—'}",
                    f"Źródło: {marker.source}",
                    f"Notatka: {marker.note or '—'}",
                )
            )
        )

    def _logical_process_finished(self, exit_code: int, exit_status) -> None:
        super()._logical_process_finished(exit_code, exit_status)
        marker = self._pending_marker
        if marker is None or not self._messages_ready:
            return
        self._pending_marker = None
        self._navigate_logical_to_marker(marker)

    @Slot(QModelIndex)
    def _open_message_details(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        message = self._display_model.message_at(index.row())
        if message is None:
            return

        dialog = ProtocolMessageDetailsDialog(message, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._message_detail_windows.append(dialog)
        dialog.destroyed.connect(
            lambda *_args, current=dialog: self._discard_message_detail(current)
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _discard_message_detail(self, dialog: ProtocolMessageDetailsDialog) -> None:
        self._message_detail_windows = [
            current
            for current in self._message_detail_windows
            if current is not dialog
        ]

    def shutdown(self) -> None:
        window = self._marker_window
        if window is not None:
            window.close()
            window.deleteLater()
            self._marker_window = None
        self._pending_marker = None
        for dialog in tuple(self._message_detail_windows):
            dialog.close()
        self._message_detail_windows.clear()
        super().shutdown()
