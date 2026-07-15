from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .analysis import AnalysisEngine, AnalysisResult
from .csv_import import CsvImportResult, import_can_csv
from .models import CanFrame, DecodedEvent


class FrameTableModel(QAbstractTableModel):
    HEADERS = ("Czas [s]", "Kanał", "CAN ID", "DLC", "Dane")

    def __init__(self) -> None:
        super().__init__()
        self._frames: list[CanFrame] = []

    def set_frames(self, frames: list[CanFrame]) -> None:
        self.beginResetModel()
        self._frames = frames
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._frames)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):  # noqa: N802
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        frame = self._frames[index.row()]
        values = (
            f"{frame.timestamp_s:.6f}",
            frame.channel,
            f"0x{frame.arbitration_id:08X}",
            len(frame.data),
            frame.data_hex,
        )
        return values[index.column()]


class EventTableModel(QAbstractTableModel):
    HEADERS = ("Czas [s]", "Kierunek", "CAN ID", "Zdarzenie", "Szczegóły", "Payload")

    def __init__(self) -> None:
        super().__init__()
        self._events: list[DecodedEvent] = []

    def set_events(self, events: list[DecodedEvent]) -> None:
        self.beginResetModel()
        self._events = events
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._events)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):  # noqa: N802
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        event = self._events[index.row()]
        values = (
            f"{event.timestamp_s:.6f}",
            event.direction,
            f"0x{event.arbitration_id:08X}",
            event.name,
            event.details,
            event.payload_hex,
        )
        return values[index.column()]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CRT — CAN Research Tool")
        self.resize(1280, 760)

        self._import_result = CsvImportResult([], [])
        self._analysis_result = AnalysisResult([], 0, 0)
        self._source_path: Path | None = None
        self._engine = AnalysisEngine()

        self._frame_model = FrameTableModel()
        self._event_model = EventTableModel()
        self._summary = QLabel("Tryb pasywny. Zaimportuj log CAN w formacie CSV.")
        self._summary.setWordWrap(True)

        frame_view = QTableView()
        frame_view.setModel(self._frame_model)
        frame_view.setSortingEnabled(False)
        frame_view.horizontalHeader().setStretchLastSection(True)

        event_view = QTableView()
        event_view.setModel(self._event_model)
        event_view.setSortingEnabled(False)
        event_view.horizontalHeader().setStretchLastSection(True)

        tabs = QTabWidget()
        tabs.addTab(frame_view, "Ramki CAN")
        tabs.addTab(event_view, "Dekodowanie SAC / UDS")

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.addWidget(self._summary)
        layout.addWidget(tabs)
        self.setCentralWidget(body)

        toolbar = QToolBar("Sesja")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        open_action = QAction("Importuj CSV", self)
        open_action.triggered.connect(self._open_csv)
        toolbar.addAction(open_action)

        export_action = QAction("Zapisz raport JSON", self)
        export_action.triggered.connect(self._export_report)
        toolbar.addAction(export_action)

    def _open_csv(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz log CAN",
            "",
            "CSV (*.csv);;Wszystkie pliki (*)",
        )
        if not filename:
            return

        try:
            self._source_path = Path(filename)
            self._import_result = import_can_csv(filename)
            self._analysis_result = self._engine.analyze(self._import_result.frames)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Błąd importu", str(exc))
            return

        self._frame_model.set_frames(self._import_result.frames)
        self._event_model.set_events(self._analysis_result.events)
        self._summary.setText(
            f"Plik: {self._source_path.name} | Ramki: {len(self._import_result.frames)} | "
            f"ISO-TP: {self._analysis_result.completed_isotp_messages} | "
            f"Zdarzenia UDS: {len(self._analysis_result.events)} | "
            f"Odrzucone ISO-TP: {self._analysis_result.dropped_isotp_messages} | "
            f"Ostrzeżenia importu: {len(self._import_result.warnings)}"
        )

    def _export_report(self) -> None:
        if self._source_path is None:
            QMessageBox.information(self, "Brak sesji", "Najpierw zaimportuj log CAN.")
            return

        default_name = self._source_path.with_suffix(".crt-report.json").name
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Zapisz raport CRT",
            default_name,
            "JSON (*.json)",
        )
        if not filename:
            return

        report = {
            "mode": "passive",
            "source": str(self._source_path),
            "frame_count": len(self._import_result.frames),
            "warnings": self._import_result.warnings,
            "completed_isotp_messages": self._analysis_result.completed_isotp_messages,
            "dropped_isotp_messages": self._analysis_result.dropped_isotp_messages,
            "events": [
                {
                    **asdict(event),
                    "payload": event.payload.hex(" ").upper(),
                }
                for event in self._analysis_result.events
            ],
        }
        Path(filename).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
