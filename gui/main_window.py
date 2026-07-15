from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.capture_service import CaptureConfig, CaptureService, CaptureState
from kvaser.backend import KvaserReceiveMode, list_channels

from .frame_model import FrameTableModel
from .session_loader import SessionLoadTask


class MainWindow(QMainWindow):
    LIVE_CAPACITY = 20_000
    GUI_REFRESH_MS = 100

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CAN Research Tool")
        self.resize(1440, 850)

        self._capture = CaptureService()
        self._last_sequence: int | None = None
        self._last_state = CaptureState.IDLE
        self._view_mode = "live"
        self._load_task: SessionLoadTask | None = None
        self._error_shown = ""

        self._frame_model = FrameTableModel(capacity=self.LIVE_CAPACITY, parent=self)
        self._build_ui()
        self._refresh_channels()

        self._timer = QTimer(self)
        self._timer.setInterval(self.GUI_REFRESH_MS)
        self._timer.timeout.connect(self._refresh_view)
        self._timer.start()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        controls = QHBoxLayout()
        controls.setSpacing(6)

        controls.addWidget(QLabel("Adapter:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setMinimumWidth(300)
        controls.addWidget(self.channel_combo)

        self.refresh_button = QPushButton("Odśwież")
        self.refresh_button.clicked.connect(self._refresh_channels)
        controls.addWidget(self.refresh_button)

        controls.addWidget(QLabel("Bitrate:"))
        self.bitrate_combo = QComboBox()
        for bitrate in (125_000, 250_000, 500_000, 1_000_000):
            self.bitrate_combo.addItem(f"{bitrate:,}".replace(",", " "), bitrate)
        self.bitrate_combo.setCurrentIndex(1)
        controls.addWidget(self.bitrate_combo)

        controls.addWidget(QLabel("Tryb:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("BENCH — ACK aktywny", KvaserReceiveMode.BENCH.value)
        self.mode_combo.addItem(
            "LISTEN ONLY — bez ACK",
            KvaserReceiveMode.LISTEN_ONLY.value,
        )
        controls.addWidget(self.mode_combo)

        controls.addWidget(QLabel("Sesja:"))
        self.session_name = QLineEdit()
        self.session_name.setPlaceholderText("np. ecu_idle")
        self.session_name.setMinimumWidth(150)
        controls.addWidget(self.session_name)

        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._start_capture)
        controls.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_capture)
        controls.addWidget(self.stop_button)

        self.open_button = QPushButton("Otwórz sesję")
        self.open_button.clicked.connect(self._open_session)
        controls.addWidget(self.open_button)

        root.addLayout(controls)

        view_controls = QHBoxLayout()
        self.pause_view = QCheckBox("Pauza widoku")
        self.pause_view.setToolTip(
            "Zatrzymuje tylko tabelę. Odbiór i zapis sesji nadal działają."
        )
        view_controls.addWidget(self.pause_view)

        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)
        view_controls.addWidget(self.auto_scroll)

        self.buffer_label = QLabel(
            f"Bufor widoku: maksymalnie {self.LIVE_CAPACITY:,} ramek".replace(",", " ")
        )
        view_controls.addWidget(self.buffer_label)
        view_controls.addStretch(1)
        root.addLayout(view_controls)

        splitter = QSplitter(Qt.Vertical)
        self.table = QTableView()
        self.table.setModel(self._frame_model)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSortingEnabled(False)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.selectionModel().selectionChanged.connect(self._show_selected_frame)
        self.table.setColumnWidth(0, 115)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 55)
        self.table.setColumnWidth(4, 45)
        self.table.setColumnWidth(5, 360)
        self.table.setColumnWidth(6, 55)
        splitter.addWidget(self.table)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumBlockCount(200)
        self.details.setPlaceholderText("Zaznacz ramkę, aby zobaczyć szczegóły.")
        splitter.addWidget(self.details)
        splitter.setSizes([700, 130])
        root.addWidget(splitter, 1)

        status_row = QHBoxLayout()
        self.state_label = QLabel("Stan: IDLE")
        self.elapsed_label = QLabel("Czas: 0.0 s")
        self.received_label = QLabel("Odebrane: 0")
        self.visible_label = QLabel("Widoczne: 0")
        self.outside_buffer_label = QLabel("Poza buforem widoku: 0")
        self.messages_label = QLabel("Wiadomości logiczne: 0")
        self.ids_label = QLabel("CAN ID: 0")
        for widget in (
            self.state_label,
            self.elapsed_label,
            self.received_label,
            self.visible_label,
            self.outside_buffer_label,
            self.messages_label,
            self.ids_label,
        ):
            status_row.addWidget(widget)
        status_row.addStretch(1)
        root.addLayout(status_row)

        self.path_label = QLabel("Brak aktywnej sesji")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.path_label)

        self.setCentralWidget(central)

    def _refresh_channels(self) -> None:
        self.channel_combo.clear()
        try:
            channels = list_channels()
        except Exception as exc:
            self.channel_combo.addItem(f"Błąd Kvaser: {exc}", None)
            self.start_button.setEnabled(False)
            return

        physical_count = 0
        for channel in channels:
            is_virtual = "Virtual CAN Driver" in channel.name
            suffix = " [virtual]" if is_virtual else ""
            label = f"{channel.number}: {channel.name}{suffix}"
            self.channel_combo.addItem(label, channel.number)
            if not is_virtual:
                physical_count += 1

        self.start_button.setEnabled(bool(channels) and not self._capture.is_active)
        if physical_count:
            for index in range(self.channel_combo.count()):
                if "[virtual]" not in self.channel_combo.itemText(index):
                    self.channel_combo.setCurrentIndex(index)
                    break

    def _start_capture(self) -> None:
        channel_number = self.channel_combo.currentData()
        if channel_number is None:
            QMessageBox.warning(self, "CRT", "Nie wybrano poprawnego kanału Kvaser.")
            return

        name = self.session_name.text().strip()
        if not name:
            name = datetime.now().strftime("capture_%Y%m%d_%H%M%S")
            self.session_name.setText(name)

        try:
            paths = self._capture.start(
                CaptureConfig(
                    channel_number=int(channel_number),
                    bitrate=int(self.bitrate_combo.currentData()),
                    mode=KvaserReceiveMode(str(self.mode_combo.currentData())),
                    session_name=name,
                    output_dir=Path("sessions"),
                    live_buffer_capacity=self.LIVE_CAPACITY,
                )
            )
        except Exception as exc:
            QMessageBox.critical(self, "Nie można rozpocząć rejestracji", str(exc))
            return

        self._view_mode = "live"
        self._last_sequence = None
        self._error_shown = ""
        self._frame_model.clear()
        self.details.clear()
        self.pause_view.setChecked(False)
        self.path_label.setText(f"Sesja: {paths.session}")
        self._set_capture_controls(True)

    def _stop_capture(self) -> None:
        self._capture.stop()
        self.stop_button.setEnabled(False)

    def _refresh_view(self) -> None:
        status = self._capture.status()
        self._update_status_labels(status)

        if self._view_mode == "live" and not self.pause_view.isChecked():
            snapshot = self._capture.live_snapshot_since(self._last_sequence)
            if snapshot.frames:
                scrollbar = self.table.verticalScrollBar()
                was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 2
                if snapshot.truncated:
                    self._frame_model.replace_frames(snapshot.frames)
                else:
                    self._frame_model.append_frames(snapshot.frames)
                self._last_sequence = snapshot.last_available_sequence
                if self.auto_scroll.isChecked() and was_at_bottom:
                    self.table.scrollToBottom()

        active = status.state in (
            CaptureState.STARTING,
            CaptureState.RUNNING,
            CaptureState.STOPPING,
        )
        self._set_capture_controls(active)

        if status.state == CaptureState.ERROR and status.error:
            if status.error != self._error_shown:
                self._error_shown = status.error
                QMessageBox.critical(self, "Błąd rejestracji", status.error)

        self._last_state = status.state

    def _update_status_labels(self, status) -> None:
        self.state_label.setText(f"Stan: {status.state.value.upper()}")
        self.elapsed_label.setText(f"Czas: {status.elapsed_s:.1f} s")
        self.received_label.setText(f"Odebrane: {status.frame_count:,}".replace(",", " "))
        self.visible_label.setText(
            f"Widoczne: {self._frame_model.frame_count:,}".replace(",", " ")
        )
        self.outside_buffer_label.setText(
            f"Poza buforem widoku: {status.live_dropped_from_view:,}".replace(",", " ")
        )
        self.messages_label.setText(
            f"Wiadomości logiczne: {status.logical_message_count:,}".replace(",", " ")
        )
        self.ids_label.setText(f"CAN ID: {status.unique_can_ids}")

    def _set_capture_controls(self, active: bool) -> None:
        self.start_button.setEnabled(not active and self.channel_combo.currentData() is not None)
        self.stop_button.setEnabled(active and self._last_state != CaptureState.STOPPING)
        self.channel_combo.setEnabled(not active)
        self.refresh_button.setEnabled(not active)
        self.bitrate_combo.setEnabled(not active)
        self.mode_combo.setEnabled(not active)
        self.session_name.setEnabled(not active)
        self.open_button.setEnabled(not active)

    def _open_session(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Otwórz sesję CRT",
            str(Path("sessions").resolve()),
            "CRT session (*.crt.jsonl);;JSON Lines (*.jsonl);;Wszystkie pliki (*)",
        )
        if not path:
            return

        self.path_label.setText(f"Indeksowanie i otwieranie: {path}")
        self.open_button.setEnabled(False)
        task = SessionLoadTask(path, max_rows=self.LIVE_CAPACITY)
        task.signals.loaded.connect(self._session_loaded)
        task.signals.failed.connect(self._session_load_failed)
        self._load_task = task
        QThreadPool.globalInstance().start(task)

    def _session_loaded(
        self,
        path: str,
        frames: object,
        total_frames: int,
        start: int,
    ) -> None:
        loaded_frames = list(frames)
        self._view_mode = "session"
        self._frame_model.replace_frames(loaded_frames)
        self._last_sequence = loaded_frames[-1].sequence if loaded_frames else None
        self.path_label.setText(
            f"Sesja: {path} | pokazano {len(loaded_frames):,} z {total_frames:,} "
            f"ramek, od rekordu {start:,}".replace(",", " ")
        )
        self.open_button.setEnabled(True)
        self._load_task = None
        if loaded_frames:
            self.table.scrollToBottom()

    def _session_load_failed(self, path: str, error: str) -> None:
        self.path_label.setText(f"Nie udało się otworzyć: {path}")
        self.open_button.setEnabled(True)
        self._load_task = None
        QMessageBox.critical(self, "Błąd otwierania sesji", error)

    def _show_selected_frame(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.details.clear()
            return
        frame = self._frame_model.frame_at(rows[0].row())
        if frame is None:
            self.details.clear()
            return
        width = 8 if frame.is_extended_id else 3
        self.details.setPlainText(
            "\n".join(
                [
                    f"Czas: {frame.timestamp_ns / 1_000_000:.6f} ms",
                    f"Sekwencja: {frame.sequence}",
                    f"CAN ID: 0x{frame.arbitration_id:0{width}X}",
                    f"Typ: {'EXT' if frame.is_extended_id else 'STD'}",
                    f"DLC: {frame.dlc}",
                    f"DATA: {frame.data_hex}",
                    f"Kanał: {frame.channel}",
                    f"Flagi źródłowe: 0x{frame.source_flags:X}",
                    f"Timestamp adaptera: {frame.source_timestamp}",
                ]
            )
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._capture.is_active:
            self._capture.stop()
            self._capture.wait(2.0)
        event.accept()
