from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QThreadPool, Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QTableView, QTabWidget, QVBoxLayout, QWidget

from app.marker_stream import iter_markers, marker_path_for_session
from app.markers import CaptureMarker
from app.stored_session_controller import (
    StoredSessionController,
    StoredSessionPageState,
)

from .frame_model import FrameTableModel
from .logical_message_loader import LogicalMessageLoadTask
from .logical_message_model import (
    LogicalMessageTableModel,
    format_logical_message_inspector,
)
from .protocol_summary import attach_protocol_summary
from .session_filter_integration import StoredSessionIntegration


class MarkerHistoryModel(QAbstractTableModel):
    _HEADERS = ("Czas [ms]", "Nazwa", "Skrót", "Obszar", "Źródło", "Notatka")

    def __init__(self, markers: list[CaptureMarker], parent=None) -> None:
        super().__init__(parent)
        self._markers = markers

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._markers)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):  # noqa: N802,E501
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self._HEADERS):
            return self._HEADERS[section]
        return section + 1

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._markers):
            return None
        if role != Qt.DisplayRole:
            return None
        marker = self._markers[index.row()]
        values = (
            f"{marker.timestamp_ns / 1_000_000:.3f}",
            marker.name,
            marker.shortcut,
            marker.area or "—",
            marker.source,
            marker.note,
        )
        return values[index.column()]

    def marker_at(self, row: int) -> CaptureMarker | None:
        return self._markers[row] if 0 <= row < len(self._markers) else None


class SessionViewWidget(QWidget):
    inspector_text = Signal(str)
    output_message = Signal(str)

    MAX_ROWS = 20_000
    MAX_MESSAGES = 20_000

    def __init__(
        self,
        path: str | Path,
        *,
        dbc_paths: tuple[Path, ...] = (),
        parent: QWidget | None = None,
        controller: StoredSessionController | None = None,
        stored_integration_factory: Callable[
            [SessionViewWidget, StoredSessionController], StoredSessionIntegration
        ] = StoredSessionIntegration,
        protocol_summary_attacher: Callable[..., None] = attach_protocol_summary,
    ) -> None:
        super().__init__(parent)
        self.path = Path(path)
        self._dbc_paths = tuple(Path(item) for item in dbc_paths)
        self._stored_session_controller = controller or StoredSessionController(
            self.path,
            page_size=self.MAX_ROWS,
        )
        self._stored_rendered_generation = 0
        self._message_load_tasks: list[LogicalMessageLoadTask] = []
        self._message_load_generation = 0
        self.frame_model = FrameTableModel(capacity=self.MAX_ROWS, parent=self)
        self.message_model = LogicalMessageTableModel(
            capacity=self.MAX_MESSAGES,
            parent=self,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        self.header = QLabel(f"Otwieranie sesji: {self.path}")
        self.header.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.header)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        raw_page = QWidget()
        raw_layout = QVBoxLayout(raw_page)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        self.frame_table = QTableView()
        self.frame_table.setModel(self.frame_model)
        self.frame_table.setWordWrap(False)
        self.frame_table.setSelectionBehavior(QTableView.SelectRows)
        self.frame_table.setSelectionMode(QTableView.SingleSelection)
        self.frame_table.verticalHeader().setDefaultSectionSize(22)
        self.frame_table.horizontalHeader().setStretchLastSection(True)
        self.frame_table.selectionModel().selectionChanged.connect(self._frame_selected)
        raw_layout.addWidget(self.frame_table)
        self.raw_tab_index = self.tabs.addTab(raw_page, "Surowe ramki")

        message_page = QWidget()
        message_layout = QVBoxLayout(message_page)
        message_layout.setContentsMargins(0, 0, 0, 0)
        self.message_table = QTableView()
        self.message_table.setModel(self.message_model)
        self.message_table.setWordWrap(False)
        self.message_table.setSelectionBehavior(QTableView.SelectRows)
        self.message_table.setSelectionMode(QTableView.SingleSelection)
        self.message_table.verticalHeader().setDefaultSectionSize(22)
        self.message_table.horizontalHeader().setStretchLastSection(True)
        self.message_table.selectionModel().selectionChanged.connect(
            self._message_selected
        )
        self.message_table.setColumnWidth(0, 115)
        self.message_table.setColumnWidth(1, 90)
        self.message_table.setColumnWidth(2, 130)
        self.message_table.setColumnWidth(3, 130)
        self.message_table.setColumnWidth(4, 75)
        self.message_table.setColumnWidth(5, 75)
        self.message_table.setColumnWidth(6, 70)
        self.message_table.setColumnWidth(7, 65)
        self.message_table.setColumnWidth(8, 105)
        self.message_table.setColumnWidth(9, 180)
        message_layout.addWidget(self.message_table)
        self.message_tab_index = self.tabs.addTab(
            message_page,
            "Wiadomości logiczne — ładowanie…",
        )

        markers = list(iter_markers(marker_path_for_session(self.path)))
        self.marker_model = MarkerHistoryModel(markers, self)
        marker_page = QWidget()
        marker_layout = QVBoxLayout(marker_page)
        marker_layout.setContentsMargins(0, 0, 0, 0)
        self.marker_table = QTableView()
        self.marker_table.setModel(self.marker_model)
        self.marker_table.setSelectionBehavior(QTableView.SelectRows)
        self.marker_table.setSelectionMode(QTableView.SingleSelection)
        self.marker_table.verticalHeader().setDefaultSectionSize(22)
        self.marker_table.horizontalHeader().setStretchLastSection(True)
        self.marker_table.selectionModel().selectionChanged.connect(self._marker_selected)
        marker_layout.addWidget(self.marker_table)
        self.tabs.addTab(marker_page, f"Znaczniki ({len(markers)})")

        self._stored_session_integration = stored_integration_factory(
            self,
            self._stored_session_controller,
        )
        self._start_message_load()
        protocol_summary_attacher(self.message_table, self.message_model)

    def reload_logical_messages(self, dbc_paths: tuple[Path, ...]) -> None:
        self._dbc_paths = tuple(Path(item) for item in dbc_paths)
        self.message_model.clear()
        self.tabs.setTabText(self.message_tab_index, "Wiadomości logiczne — ładowanie…")
        self._start_message_load()

    def _start_message_load(self) -> None:
        self._message_load_generation += 1
        generation = self._message_load_generation
        task = LogicalMessageLoadTask(
            self.path,
            max_rows=self.MAX_MESSAGES,
            dbc_paths=self._dbc_paths,
        )
        task.signals.loaded.connect(
            lambda path, messages, total, source, current=generation: self._messages_loaded(
                current,
                path,
                messages,
                total,
                source,
            )
        )
        task.signals.failed.connect(
            lambda path, error, current=generation: self._messages_failed(
                current,
                path,
                error,
            )
        )
        self._message_load_tasks.append(task)
        QThreadPool.globalInstance().start(task)

    def _apply_stored_session_state(self, state: StoredSessionPageState) -> None:
        if state.loading or state.generation == self._stored_rendered_generation:
            return
        self._stored_rendered_generation = state.generation
        if state.error:
            self.header.setText(
                f"Nie udało się otworzyć sesji: {state.path}\n{state.error}"
            )
            self.output_message.emit(
                f"Błąd filtrowania sesji {state.path}: {state.error}"
            )
            return
        if state.page is None:
            return

        page = state.page
        loaded = list(page.frames)
        self.frame_model.replace_frames(loaded)
        start = page.loaded_from_visible_index
        end = start + len(loaded)
        if state.filter_affects_visibility:
            text = (
                f"{state.session_title} — {state.path} | wyniki "
                f"{start + 1 if loaded else 0:,}–{end:,} z {page.visible_frames:,} "
                f"| cały log: {page.total_frames:,} ramek"
            ).replace(",", " ")
            tab_text = (
                f"Surowe ramki ({page.visible_frames:,}/{page.total_frames:,})"
            ).replace(",", " ")
        else:
            text = (
                f"{state.session_title} — {state.path} | ramki "
                f"{start + 1 if loaded else 0:,}–{end:,} z {page.total_frames:,}"
            ).replace(",", " ")
            tab_text = f"Surowe ramki ({page.total_frames:,})".replace(",", " ")

        self.header.setText(text)
        self.tabs.setTabText(self.raw_tab_index, tab_text)
        if loaded:
            self.frame_table.scrollToTop()
        self.output_message.emit(
            f"Otwarto stronę sesji {state.path}: zakres={start}-{end}, "
            f"widoczne={page.visible_frames}, wszystkie={page.total_frames}"
        )

    def _messages_loaded(
        self,
        generation: int,
        path: str,
        messages: object,
        total_messages: int,
        source: str,
    ) -> None:
        if generation != self._message_load_generation:
            self._discard_finished_message_tasks()
            return
        loaded = list(messages)
        self.message_model.replace_messages(loaded)
        self.tabs.setTabText(
            self.message_tab_index,
            f"Wiadomości logiczne ({total_messages:,})".replace(",", " "),
        )
        if loaded:
            self.message_table.scrollToBottom()
        if source.startswith("messages-csv"):
            source_text = "messages.csv"
        else:
            source_text = "rekonstrukcja z ramek"
        if source.endswith("+dbc"):
            source_text += " + aktywne DBC"
        self.output_message.emit(
            f"Wiadomości logiczne {path}: {total_messages} ({source_text})"
        )
        self._discard_finished_message_tasks()

    def _messages_failed(self, generation: int, path: str, error: str) -> None:
        if generation != self._message_load_generation:
            self._discard_finished_message_tasks()
            return
        self.tabs.setTabText(self.message_tab_index, "Wiadomości logiczne — błąd")
        self.output_message.emit(
            f"Błąd odczytu wiadomości logicznych {path}: {error}"
        )
        self._discard_finished_message_tasks()

    def _discard_finished_message_tasks(self) -> None:
        self._message_load_tasks = [
            task for task in self._message_load_tasks if task is not None
        ][-2:]

    def _frame_selected(self) -> None:
        rows = self.frame_table.selectionModel().selectedRows()
        if not rows:
            return
        frame = self.frame_model.frame_at(rows[0].row())
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

    def _message_selected(self) -> None:
        rows = self.message_table.selectionModel().selectedRows()
        if not rows:
            return
        message = self.message_model.message_at(rows[0].row())
        if message is not None:
            self.inspector_text.emit(format_logical_message_inspector(message))

    def _marker_selected(self) -> None:
        rows = self.marker_table.selectionModel().selectedRows()
        if not rows:
            return
        marker = self.marker_model.marker_at(rows[0].row())
        if marker is None:
            return
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

    def shutdown(self) -> None:
        self._stored_session_integration.shutdown()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.shutdown()
        super().closeEvent(event)
