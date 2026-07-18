from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.capture_service import CaptureState
from app.dbc import DbcDecoder
from app.live_capture_controller import (
    CaptureMode,
    LiveCaptureController,
)
from app.logical_records import reinterpret_raw_record
from app.markers import MarkerPreset
from app.project import CrtProject
from app.protocols import ProtocolRegistry

from .frame_model import FrameTableModel
from .live_filter_integration import (
    LIVE_FRAME_CAPACITY as DEFAULT_LIVE_FRAME_CAPACITY,
    LIVE_MESSAGE_CAPACITY as DEFAULT_LIVE_MESSAGE_CAPACITY,
    LiveFilterIntegration,
)
from .live_save_integration import LiveSaveIntegration
from .logical_message_model import (
    LogicalMessageTableModel,
    format_logical_message_inspector,
)
from .marker_manager import MarkerManagerDialog
from .protocol_summary import attach_protocol_summary
from .table_hover import install_fast_cell_hover


class LiveCaptureWidget(QWidget):
    inspector_text = Signal(str)
    output_message = Signal(str)
    status_text = Signal(str)
    project_changed = Signal()

    LIVE_CAPACITY = DEFAULT_LIVE_FRAME_CAPACITY
    LIVE_MESSAGE_CAPACITY = DEFAULT_LIVE_MESSAGE_CAPACITY
    GUI_REFRESH_MS = 100

    def __init__(
        self,
        project: CrtProject,
        parent: QWidget | None = None,
        *,
        controller: LiveCaptureController | None = None,
        filter_integration_factory: Callable[..., LiveFilterIntegration] = (
            LiveFilterIntegration
        ),
        save_integration_factory: Callable[..., LiveSaveIntegration] = (
            LiveSaveIntegration
        ),
        protocol_summary_attacher: Callable[..., None] = attach_protocol_summary,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self._controller = controller or LiveCaptureController()
        self._last_sequence: int | None = None
        self._last_message_sequence: int | None = None
        self._last_state = CaptureState.IDLE
        self._current_session_path: Path | None = None
        self._finalized_session_path: Path | None = None
        self._shortcuts: list[QShortcut] = []
        self._marker_buttons: list[QPushButton] = []
        self._error_shown = ""
        self._base_registry = ProtocolRegistry()
        self._dbc_decoder: DbcDecoder | None = None

        self.frame_model = FrameTableModel(capacity=self.LIVE_CAPACITY, parent=self)
        self.message_model = LogicalMessageTableModel(
            capacity=self.LIVE_MESSAGE_CAPACITY,
            parent=self,
        )
        self._build_ui()
        self._live_filter_integration = filter_integration_factory(self)
        self._live_save_integration = save_integration_factory(self)
        protocol_summary_attacher(self.message_table, self.message_model)
        self._update_marker_tile()
        self._refresh_channels()

        self.timer = QTimer(self)
        self.timer.setInterval(self.GUI_REFRESH_MS)
        self.timer.timeout.connect(self._refresh_view)
        self.timer.start()

    @property
    def is_capturing(self) -> bool:
        return self._controller.is_active

    def shutdown(self) -> None:
        if self._controller.is_active:
            self._controller.stop()
            self._controller.wait(3.0)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(7, 7, 7, 7)
        root.setSpacing(6)

        connection_group = QGroupBox("Połączenie i sesja")
        connection_root = QVBoxLayout(connection_group)
        connection_root.setSpacing(6)

        can_row = QHBoxLayout()
        can_row.addWidget(QLabel("Adapter:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setMinimumWidth(330)
        can_row.addWidget(self.channel_combo, 1)
        self.refresh_button = QPushButton("Odśwież")
        self.refresh_button.clicked.connect(self._refresh_channels)
        can_row.addWidget(self.refresh_button)
        can_row.addWidget(QLabel("Bitrate:"))
        self.bitrate_combo = QComboBox()
        for bitrate in (125_000, 250_000, 500_000, 1_000_000):
            self.bitrate_combo.addItem(f"{bitrate:,}".replace(",", " "), bitrate)
        bitrate_index = self.bitrate_combo.findData(self.project.manifest.default_bitrate)
        self.bitrate_combo.setCurrentIndex(max(0, bitrate_index))
        can_row.addWidget(self.bitrate_combo)
        can_row.addWidget(QLabel("Tryb:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("BENCH — ACK aktywny", CaptureMode.BENCH.value)
        self.mode_combo.addItem("LISTEN ONLY — bez ACK", CaptureMode.LISTEN_ONLY.value)
        mode_index = self.mode_combo.findData(self.project.manifest.default_receive_mode)
        self.mode_combo.setCurrentIndex(max(0, mode_index))
        can_row.addWidget(self.mode_combo)
        connection_root.addLayout(can_row)

        session_row = QHBoxLayout()
        session_row.addWidget(QLabel("Nazwa sesji:"))
        self.session_name = QLineEdit()
        self.session_name.setPlaceholderText("np. egr_disconnect")
        self.session_name.setMinimumWidth(260)
        session_row.addWidget(self.session_name, 1)

        self.marker_setup_button = QPushButton()
        self.marker_setup_button.setMinimumSize(190, 48)
        self.marker_setup_button.setToolTip(
            "Otwórz konfigurację nazw, skrótów, kolorów i aktywności znaczników."
        )
        self.marker_setup_button.clicked.connect(self._open_marker_manager)
        self.marker_setup_button.setStyleSheet(
            "QPushButton { text-align: left; padding: 6px 12px; font-weight: 600; }"
        )
        session_row.addWidget(self.marker_setup_button)

        self.start_button = QPushButton("Start")
        self.start_button.setMinimumSize(90, 48)
        self.start_button.clicked.connect(self._start_capture)
        session_row.addWidget(self.start_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setMinimumSize(90, 48)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_capture)
        session_row.addWidget(self.stop_button)
        connection_root.addLayout(session_row)

        self.runtime_marker_widget = QFrame()
        self.runtime_marker_widget.setFrameShape(QFrame.StyledPanel)
        self.runtime_marker_row = QHBoxLayout(self.runtime_marker_widget)
        self.runtime_marker_row.setContentsMargins(7, 5, 7, 5)
        self.runtime_marker_row.addWidget(QLabel("Znaczniki aktywnej sesji:"))
        self.runtime_marker_row.addStretch(1)
        self.runtime_marker_widget.setVisible(False)
        connection_root.addWidget(self.runtime_marker_widget)
        root.addWidget(connection_group)

        view_controls = QHBoxLayout()
        self.pause_view = QCheckBox("Pauza widoku")
        self.pause_view.setToolTip(
            "Zatrzymuje tabele ramek i wiadomości, ale nie odbiór ani zapis sesji."
        )
        view_controls.addWidget(self.pause_view)
        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)
        view_controls.addWidget(self.auto_scroll)
        view_controls.addWidget(
            QLabel(
                f"Bufory GUI: {self.LIVE_CAPACITY:,} ramek / "
                f"{self.LIVE_MESSAGE_CAPACITY:,} wiadomości".replace(",", " ")
            )
        )
        view_controls.addStretch(1)
        root.addLayout(view_controls)

        self.data_tabs = QTabWidget()
        root.addWidget(self.data_tabs, 1)

        raw_page = QWidget()
        raw_layout = QVBoxLayout(raw_page)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        self.frame_table = QTableView()
        self.frame_table.setModel(self.frame_model)
        self.frame_table.setAlternatingRowColors(True)
        self.frame_table.setWordWrap(False)
        self.frame_table.setSelectionBehavior(QTableView.SelectRows)
        self.frame_table.setSelectionMode(QTableView.SingleSelection)
        self.frame_table.verticalHeader().setDefaultSectionSize(22)
        self.frame_table.horizontalHeader().setStretchLastSection(True)
        install_fast_cell_hover(self.frame_table)
        self.frame_table.selectionModel().selectionChanged.connect(self._frame_selected)
        self.frame_table.setColumnWidth(0, 115)
        self.frame_table.setColumnWidth(1, 90)
        self.frame_table.setColumnWidth(2, 120)
        self.frame_table.setColumnWidth(3, 55)
        self.frame_table.setColumnWidth(4, 45)
        self.frame_table.setColumnWidth(5, 360)
        splitter.addWidget(self.frame_table)

        marker_history_group = QGroupBox("Znaczniki tej sesji")
        marker_history_layout = QVBoxLayout(marker_history_group)
        self.marker_history = QListWidget()
        marker_history_layout.addWidget(self.marker_history)
        marker_history_group.setMinimumWidth(260)
        splitter.addWidget(marker_history_group)
        splitter.setSizes([1050, 280])
        raw_layout.addWidget(splitter)
        self.raw_tab_index = self.data_tabs.addTab(raw_page, "Surowe ramki")

        message_page = QWidget()
        message_layout = QVBoxLayout(message_page)
        message_layout.setContentsMargins(0, 0, 0, 0)
        self.message_table = QTableView()
        self.message_table.setModel(self.message_model)
        self.message_table.setAlternatingRowColors(True)
        self.message_table.setWordWrap(False)
        self.message_table.setSelectionBehavior(QTableView.SelectRows)
        self.message_table.setSelectionMode(QTableView.SingleSelection)
        self.message_table.verticalHeader().setDefaultSectionSize(22)
        self.message_table.horizontalHeader().setStretchLastSection(True)
        install_fast_cell_hover(self.message_table)
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
        self.message_tab_index = self.data_tabs.addTab(
            message_page,
            "Wiadomości logiczne",
        )

        status_row = QHBoxLayout()
        self.state_label = QLabel("Stan: IDLE")
        self.elapsed_label = QLabel("Czas: 0.0 s")
        self.received_label = QLabel("Odebrane: 0")
        self.visible_label = QLabel("Widoczne: 0")
        self.outside_buffer_label = QLabel("Poza buforem: 0")
        self.messages_label = QLabel("Wiadomości: 0")
        self.markers_label = QLabel("Znaczniki: 0")
        self.ids_label = QLabel("CAN ID: 0")
        for widget in (
            self.state_label,
            self.elapsed_label,
            self.received_label,
            self.visible_label,
            self.outside_buffer_label,
            self.messages_label,
            self.markers_label,
            self.ids_label,
        ):
            status_row.addWidget(widget)
        status_row.addStretch(1)
        root.addLayout(status_row)

        self.path_label = QLabel(f"Projekt: {self.project.root}")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.path_label)

    def _refresh_channels(self) -> None:
        self.channel_combo.clear()
        try:
            channels = self._controller.list_adapters()
        except Exception as exc:
            self.channel_combo.addItem(f"Błąd Kvaser: {exc}", None)
            self.start_button.setEnabled(False)
            return
        for channel in channels:
            suffix = " [virtual]" if channel.is_virtual else ""
            self.channel_combo.addItem(
                f"{channel.number}: {channel.name}{suffix}",
                channel.number,
            )
        for index in range(self.channel_combo.count()):
            if "[virtual]" not in self.channel_combo.itemText(index):
                self.channel_combo.setCurrentIndex(index)
                break
        self.start_button.setEnabled(self.channel_combo.currentData() is not None)

    def _open_marker_manager(self) -> None:
        if self._controller.is_active:
            QMessageBox.information(
                self,
                "CRT",
                "Konfigurację znaczników można zmienić po zatrzymaniu rejestracji.",
            )
            return
        dialog = MarkerManagerDialog(self.project, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._update_marker_tile()
            self.output_message.emit("Zapisano konfigurację znaczników projektu")
            self.project_changed.emit()

    def _update_marker_tile(self) -> None:
        presets = self.project.list_marker_presets()
        active = sum(preset.enabled for preset in presets)
        self.marker_setup_button.setText(
            f"Znaczniki\n{active} aktywnych / {len(presets)}"
        )

    def _start_capture(self) -> None:
        self._live_save_integration.start_capture()

    def _stop_capture(self) -> None:
        self._controller.stop()
        self.stop_button.setEnabled(False)

    def _refresh_view(self) -> None:
        status = self._controller.status()
        self._update_status(status)

        if not self.pause_view.isChecked() and status.state in (
            CaptureState.RUNNING,
            CaptureState.STOPPING,
            CaptureState.STOPPED,
        ):
            snapshot = self._controller.frames_since(self._last_sequence)
            if snapshot.frames:
                scrollbar = self.frame_table.verticalScrollBar()
                was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 2
                if snapshot.truncated:
                    self.frame_model.replace_frames(snapshot.frames)
                else:
                    self.frame_model.append_frames(snapshot.frames)
                self._last_sequence = snapshot.last_available_sequence
                if self.auto_scroll.isChecked() and was_at_bottom:
                    self.frame_table.scrollToBottom()

            message_snapshot = self._controller.messages_since(
                self._last_message_sequence
            )
            if message_snapshot.messages:
                displayed = tuple(
                    reinterpret_raw_record(
                        message,
                        base_registry=self._base_registry,
                        dbc_decoder=self._dbc_decoder,
                    )
                    for message in message_snapshot.messages
                )
                scrollbar = self.message_table.verticalScrollBar()
                was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 2
                if message_snapshot.truncated:
                    self.message_model.replace_messages(displayed)
                else:
                    self.message_model.append_messages(displayed)
                self._last_message_sequence = message_snapshot.last_available_sequence
                if self.auto_scroll.isChecked() and was_at_bottom:
                    self.message_table.scrollToBottom()

        active = status.state in (
            CaptureState.STARTING,
            CaptureState.RUNNING,
            CaptureState.STOPPING,
        )
        self._set_capture_controls(active)

        if status.state in (CaptureState.STOPPED, CaptureState.ERROR):
            self._finalize_project_session(status)
            self._clear_marker_controls()

        if (
            status.state == CaptureState.ERROR
            and status.error
            and status.error != self._error_shown
        ):
            self._error_shown = status.error
            QMessageBox.critical(self, "Błąd rejestracji", status.error)

        self._last_state = status.state

    def _update_status(self, status) -> None:
        self.state_label.setText(f"Stan: {status.state.value.upper()}")
        self.elapsed_label.setText(f"Czas: {status.elapsed_s:.1f} s")
        self.received_label.setText(
            f"Odebrane: {status.frame_count:,}".replace(",", " ")
        )
        self.visible_label.setText(
            f"Widoczne: {self.frame_model.frame_count:,}".replace(",", " ")
        )
        self.outside_buffer_label.setText(
            f"Poza buforem: {status.live_dropped_from_view:,}".replace(",", " ")
        )
        self.messages_label.setText(
            (
                f"Wiadomości: {status.logical_message_count:,} / "
                f"widoczne {self.message_model.message_count:,}"
            ).replace(",", " ")
        )
        self.markers_label.setText(
            f"Znaczniki: {status.marker_count:,}".replace(",", " ")
        )
        self.ids_label.setText(
            f"CAN ID: {status.unique_can_ids:,}".replace(",", " ")
        )
        self.data_tabs.setTabText(
            self.raw_tab_index,
            f"Surowe ramki ({status.frame_count:,})".replace(",", " "),
        )
        self.data_tabs.setTabText(
            self.message_tab_index,
            f"Wiadomości logiczne ({status.logical_message_count:,})".replace(",", " "),
        )
        self.status_text.emit(
            f"{status.state.value.upper()} | {status.frame_count:,} ramek | "
            f"{status.live_retained:,}/{status.live_capacity:,} live".replace(",", " ")
        )
        self._live_filter_integration.update_status(
            status.frame_count,
            status.logical_message_count,
        )

    def _set_capture_controls(self, active: bool) -> None:
        self.start_button.setEnabled(
            not active and self.channel_combo.currentData() is not None
        )
        self.stop_button.setEnabled(active and self._controller.is_active)
        self.channel_combo.setEnabled(not active)
        self.refresh_button.setEnabled(not active)
        self.bitrate_combo.setEnabled(not active)
        self.mode_combo.setEnabled(not active)
        self.session_name.setEnabled(not active)
        self.marker_setup_button.setEnabled(not active)
        self._live_save_integration.update_controls(active)

    def _finalize_project_session(self, status) -> None:
        self._live_save_integration.finalize(status)

    def _finalize_persistent_session(self, status) -> None:
        path = self._current_session_path
        if path is None or path == self._finalized_session_path:
            return
        self.project.finalize_session(
            path,
            frame_count=status.frame_count,
            marker_count=status.marker_count,
            duration_s=status.elapsed_s,
            status="error" if status.state is CaptureState.ERROR else "ready",
        )
        self._finalized_session_path = path
        self.project_changed.emit()
        self.output_message.emit(
            f"Sesja zakończona: {path} | ramki={status.frame_count} | "
            f"wiadomości={status.logical_message_count} | znaczniki={status.marker_count}"
        )

    def _install_marker_controls(self, presets: list[MarkerPreset]) -> None:
        self._clear_marker_controls()
        if not presets:
            return
        self.runtime_marker_widget.setVisible(True)
        for preset in presets:
            shortcut = QShortcut(QKeySequence(preset.shortcut), self)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(
                lambda selected=preset: self._trigger_marker(
                    selected,
                    source="keyboard",
                )
            )
            self._shortcuts.append(shortcut)

            button = QPushButton(f"{preset.shortcut}  {preset.name}")
            button.setMinimumHeight(38)
            if preset.color:
                button.setStyleSheet(
                    f"border-left: 6px solid {preset.color}; padding: 6px;"
                )
            button.clicked.connect(
                lambda checked=False, selected=preset: self._trigger_marker(
                    selected,
                    source="button",
                )
            )
            self.runtime_marker_row.insertWidget(
                max(1, self.runtime_marker_row.count() - 1),
                button,
            )
            self._marker_buttons.append(button)

    def _clear_marker_controls(self) -> None:
        for shortcut in self._shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._shortcuts.clear()
        for button in self._marker_buttons:
            self.runtime_marker_row.removeWidget(button)
            button.deleteLater()
        self._marker_buttons.clear()
        self.runtime_marker_widget.setVisible(False)

    def _trigger_marker(self, preset: MarkerPreset, *, source: str) -> None:
        try:
            marker = self._controller.add_marker(preset, source=source)
        except Exception:
            return
        if self._current_session_path is not None:
            self.project.record_marker(self._current_session_path, marker)
        text = (
            f"{marker.timestamp_ns / 1_000_000:10.3f} ms — "
            f"{marker.name} [{marker.shortcut}]"
        )
        self.marker_history.addItem(text)
        self.marker_history.scrollToBottom()
        self.output_message.emit(f"Znacznik: {text}")
        self.inspector_text.emit(
            "\n".join(
                (
                    "NOWY ZNACZNIK",
                    "",
                    f"Czas: {marker.timestamp_ns / 1_000_000:.6f} ms",
                    f"Nazwa: {marker.name}",
                    f"Skrót: {marker.shortcut}",
                    f"Obszar: {marker.area or '—'}",
                    f"Źródło: {marker.source}",
                )
            )
        )

    def _frame_selected(self) -> None:
        frame = self._live_filter_integration.selected_frame()
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
