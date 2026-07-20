from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt, Slot

from .protocol_message_details import ProtocolMessageDetailsDialog
from .sqlite_logical_session_view import SqliteLogicalSessionViewWidget


class DetailedLogicalSessionViewWidget(SqliteLogicalSessionViewWidget):
    """Stored logical workspace with modeless protocol-aware detail windows."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._message_detail_windows: list[ProtocolMessageDetailsDialog] = []
        self.message_table.doubleClicked.connect(self._open_message_details)

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
