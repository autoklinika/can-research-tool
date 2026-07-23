from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QMainWindow, QTableView, QVBoxLayout, QWidget

from app.marker_stream import iter_markers, marker_path_for_session
from app.markers import CaptureMarker

from .session_view import MarkerHistoryModel
from .table_hover import enable_fast_cell_hover


class SessionMarkerWindow(QMainWindow):
    """Independent non-modal marker navigator for one stored session."""

    marker_activated = Signal(object)

    def __init__(
        self,
        session_path: str | Path,
        *,
        parent: QWidget,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.session_path = Path(session_path)
        self.setObjectName("sessionMarkerWindow")
        self.setWindowTitle(f"Znaczniki — {self.session_path.stem}")
        self.setMinimumSize(620, 360)
        self.resize(900, 520)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)

        hint = QLabel(
            "Kliknij znacznik, aby przejść do najbliższej ramki lub wiadomości "
            "w aktualnie otwartej zakładce sesji.",
            central,
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        markers = list(iter_markers(marker_path_for_session(self.session_path)))
        self.model = MarkerHistoryModel(markers, self)
        self.table = QTableView(central)
        self.table.setObjectName("sessionMarkerTable")
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 125)
        self.table.setColumnWidth(1, 170)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 150)
        self.table.setColumnWidth(4, 100)
        enable_fast_cell_hover(self.table)
        self.table.clicked.connect(self._marker_clicked)
        layout.addWidget(self.table, 1)

        self.setCentralWidget(central)

        geometry = QSettings().value("windows/sessionMarkerGeometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    @property
    def marker_count(self) -> int:
        return self.model.rowCount()

    def _marker_clicked(self, index) -> None:
        marker: CaptureMarker | None = self.model.marker_at(index.row())
        if marker is not None:
            self.marker_activated.emit(marker)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        QSettings().setValue("windows/sessionMarkerGeometry", self.saveGeometry())
        super().closeEvent(event)
