from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt, Slot
from PySide6.QtWidgets import QAbstractItemView

from .protocol_message_details import ProtocolMessageDetailsDialog
from .sqlite_logical_session_view import SqliteLogicalSessionViewWidget


class DetailedLogicalSessionViewWidget(SqliteLogicalSessionViewWidget):
    """Stored workspace with marker navigation and protocol detail windows."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._message_detail_windows: list[ProtocolMessageDetailsDialog] = []
        self.message_table.doubleClicked.connect(self._open_message_details)

    def _marker_selected(self) -> None:
        """Show marker details and center the nearest raw frame in the log."""

        super()._marker_selected()
        rows = self.marker_table.selectionModel().selectedRows()
        if not rows:
            return
        marker = self.marker_model.marker_at(rows[0].row())
        if marker is None or self.frame_model.frame_count <= 0:
            return

        target_row = self._nearest_frame_row(marker.timestamp_ns)
        if target_row is None:
            return

        self.tabs.setCurrentIndex(self.raw_tab_index)
        index = self.frame_model.index(target_row, 0)
        self.frame_table.selectRow(target_row)
        self.frame_table.setCurrentIndex(index)
        self.frame_table.scrollTo(
            index,
            QAbstractItemView.ScrollHint.PositionAtCenter,
        )
        frame = self.frame_model.frame_at(target_row)
        if frame is not None:
            delta_ms = (frame.timestamp_ns - marker.timestamp_ns) / 1_000_000
            self.output_message.emit(
                f"Znacznik '{marker.name}' → ramka {frame.sequence} "
                f"({frame.timestamp_ns / 1_000_000:.3f} ms, różnica {delta_ms:+.3f} ms)"
            )

    def _nearest_frame_row(self, timestamp_ns: int) -> int | None:
        """Return the closest frame row using binary search on capture time."""

        count = self.frame_model.frame_count
        if count <= 0:
            return None

        low = 0
        high = count
        while low < high:
            middle = (low + high) // 2
            frame = self.frame_model.frame_at(middle)
            if frame is None:
                return None
            if frame.timestamp_ns < timestamp_ns:
                low = middle + 1
            else:
                high = middle

        candidates = [row for row in (low - 1, low) if 0 <= row < count]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda row: abs(
                self.frame_model.frame_at(row).timestamp_ns - timestamp_ns
            ),
        )

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
        for dialog in tuple(self._message_detail_windows):
            dialog.close()
        self._message_detail_windows.clear()
        super().shutdown()
