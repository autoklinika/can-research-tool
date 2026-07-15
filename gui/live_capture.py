from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
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

from app.capture_service import CaptureConfig, CaptureService, CaptureState
from app.markers import MarkerPreset
from app.project import CrtProject
from kvaser.backend import KvaserReceiveMode, list_channels

from .frame_model import FrameTableModel
from .logical_message_model import (
    LogicalMessageTableModel,
    format_logical_message_inspector,
)
from .marker_dialog import MarkerPresetDialog
from .marker_model import MarkerPresetTableModel


class LiveCaptureWidget(QWidget):
    inspector_text = Signal(str)
    output_message = Signal(str)
    status_text = Signal(str)
    project_changed = Signal()

    LIVE_CAPACITY = 20_000
    LIVE_MESSAGE_CAPACITY = 5_000
    GUI_REFRESH_MS = 100

    def __init__(self, project: CrtProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self._capture = CaptureService()
        self._last_sequence: int | None = None
        self._last_message_sequence: int | None = None
        self._last_state = CaptureState.IDLE
        self._current_session_path: Path | None = None
        self._finalized_session_path: Path | None = None
        self._shortcuts: list[QShortcut] = []
        self._marker_buttons: list[QPushButton] = []
        self._error_shown = ""

        self.frame_model = FrameTableModel(capacity=self.LIVE_CAPACITY, parent=self)
        self.message_model = LogicalMessageTableModel(
            capacity=self.LIVE_MESSAGE_CAPACITY,
            parent=self,
        )
        self.marker_model = MarkerPresetTableModel(project.list_marker_presets(), self)
        self._build_ui()
        self._refresh_channels()

        self.timer = QTimer(self)
        self.timer.setInterval(self.GUI_REFRESH_MS)
        self.timer.timeout.connect(self._refresh_view)
        self.timer.start()

    @property
    def is_capturing(self) -> bool:
        return self._capture.is_active

    def shutdown(self) -> None:
        if self._capture.is_active:
            self._capture.stop()
            self._capture.wait(3.0)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(7, 7, 7, 7)
        root.setSpacing(6)

        connection_group = QGroupBox("Połączenie i sesja")
        controls = QHBoxLayout(connection_group)
        controls.addWidget(QLabel("Adapter:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setMinimumWidth(280)
        controls.addWidget(self.channel_combo)
        self.refresh_button = QPushButton("Odśwież")
        self.refresh_button.clicked.connect(self._refresh_channels)
        controls.addWidget(self.refresh_button)
        controls.addWidget(QLabel("Bitrate:"))
        self.bitrate_combo = QComboBox()
        for bitrate in (125_000, 250_000, 500_000, 1_000_000):
            self.bitrate_combo.addItem(f"{bitrate:,}".replace(",", " "), bitrate)
        bitrate_index = self.bitrate_combo.findData(self.project.manifest.default_bitrate)
        self.bitrate_combo.setCurrentIndex(max(0, bitrate_index))
        controls.addWidget(self.bitrate_combo)
        controls.addWidget(QLabel("Tryb:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("BENCH — ACK aktywny", KvaserReceiveMode.BENCH.value)
        self.mode_combo.addItem("LISTEN ONLY — bez ACK", KvaserReceiveMode.LISTEN_ONLY.value)
        mode_index = self.mode_combo.findData(self.project.manifest.default_receive_mode)
        self.mode_combo.setCurrentIndex(max(0, mode_index))
        controls.addWidget(self.mode_combo)
        controls.addWidget(QLabel("Sesja:"))
        self.session_name = QLineEdit()
        self.session_name.setPlaceholderText("np. egr_disconnect")
        self.session_name.setMinimumWidth(180)
        controls.addWidget(self.session_name, 1)
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._start_capture)
        controls.addWidget(self.start_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_capture)
        controls.addWidget(self.stop_button)
        root.addWidget(connection_group)

        self.marker_group = QGroupBox("Znaczniki przygotowane przed logowaniem")
        marker_root = QVBoxLayout(self.marker_group)
        marker_top = QHBoxLayout()
        self.marker_table = QTableView()
        self.marker_table.setModel(self.marker_model)
        self.marker_table.setSelectionBehavior(QTableView.SelectRows)
        self.marker_table.setSelectionMode(QTableView.SingleSelection)
        self.marker_table.setMaximumHeight(155)
        self.marker_table.verticalHeader().setDefaultSectionSize(22)
        self.marker_table.horizontalHeader().setStretchLastSection(True)
        marker_top.addWidget(self.marker_table, 1)
        marker_actions = QVBoxLayout()
        self.add_marker_button = QPushButton("Dodaj")
        self.add_marker_button.clicked.connect(self._add_marker_preset)
        marker_actions.addWidget(self.add_marker_button)
        self.edit_marker_button = QPushButton("Edytuj")
        self.edit_marker_button.clicked.connect(self._edit_marker_preset)
        marker_actions.addWidget(self.edit_marker_button)
        self.remove_marker_button = QPushButton("Usuń")
        self.remove_marker_button.clicked.connect(self._remove_marker_preset)
        marker_actions.addWidget(self.remove_marker_button)
        marker_actions.addStretch(1)
        marker_top.addLayout(marker_actions)
        marker_root.addLayout(marker_top)

        self.runtime_marker_row = QHBoxLayout()
        self.runtime_marker_hint = QLabel(
            "Po uruchomieniu aktywne znaczniki pojawią się tutaj jako przyciski."
        )
        self.runtime_marker_row.addWidget(self.runtime_marker_hint)
        self.runtime_marker_row.addStretch(1)
        marker_root.addLayout(self.runtime_marker_row)
        root.addWidget(self.marker_group)

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
            channels = list_channels()
        except Exception as exc:
            self.channel_combo.addItem(f"Błąd Kvaser: {exc}", None)
            self.start_button.setEnabled(False)
            return
        for channel in channels:
            virtual = "Virtual CAN Driver" in channel.name
            suffix = " [virtual]" if virtual else ""
            self.channel_combo.addItem(
                f"{channel.number}: {channel.name}{suffix}",
                channel.number,
            )
        for index in range(self.channel_combo.count()):
            if "[virtual]" not in self.channel_combo.itemText(index):
                self.channel_combo.setCurrentIndex(index)
                break
        self.start_button.setEnabled(self.channel_combo.currentData() is not None)

    def _start_capture(self) -> None:
        channel_number = self.channel_combo.currentData()
        if channel_number is None:
            QMessageBox.warning(self, "CRT", "Nie wybrano poprawnego kanału Kvaser.")
            return
        name = self.session_name.text().strip()
        if not name:
            name = datetime.now().strftime("capture_%Y%m%d_%H%M%S")
            self.session_name.setText(name)

        presets = self.marker_model.presets()
        active = [preset for preset in presets if preset.enabled]
        shortcuts = [preset.shortcut.lower() for preset in active]
        if len(shortcuts) != len(set(shortcuts)):
            QMessageBox.warning(self, "CRT", "Aktywne znaczniki mają zduplikowane skróty.")
            return
        try:
            self.project.save_marker_presets(presets)
            paths = self._capture.start(
                CaptureConfig(
                    channel_number=int(channel_number),
                    bitrate=int(self.bitrate_combo.currentData()),
                    mode=KvaserReceiveMode(str(self.mode_combo.currentData())),
                    session_name=name,
                    output_dir=self.project.live_sessions_dir,
                    live_buffer_capacity=self.LIVE_CAPACITY,
                    live_message_capacity=self.LIVE_MESSAGE_CAPACITY,
                    marker_presets=tuple(active),
                )
            )
            self.project.register_session(
                paths.session,
                name=name,
                source="kvaser-live-stream",
                status="recording",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Nie można rozpocząć rejestracji", str(exc))
            return

        self._current_session_path = paths.session
        self._finalized_session_path = None
        self._last_sequence = None
        self._last_message_sequence = None
        self._error_shown = ""
        self.frame_model.clear()
        self.message_model.clear()
        self.marker_history.clear()
        self.pause_view.setChecked(False)
        self.path_label.setText(f"Sesja: {paths.session}")
        self._install_marker_controls(active)
        self._set_capture_controls(True)
        self.output_message.emit(f"Rozpoczęto rejestrację: {paths.session}")
        self.project_changed.emit()

    def _stop_capture(self) -> None:
        self._capture.stop()
        self.stop_button.setEnabled(False)

    def _refresh_view(self) -> None:
        status = self._capture.status()
        self._update_status(status)

        if not self.pause_view.isChecked() and status.state in (
            CaptureState.RUNNING,
            CaptureState.STOPPING,
            CaptureState.STOPPED,
        ):
            snapshot = self._capture.live_snapshot_since(self._last_sequence)
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

            message_snapshot = self._capture.live_messages_snapshot_since(
                self._last_message_sequence
            )
            if message_snapshot.messages:
                scrollbar = self.message_table.verticalScrollBar()
                was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 2
                if message_snapshot.truncated:
                    self.message_model.replace_messages(message_snapshot.messages)
                else:
                    self.message_model.append_messages(message_snapshot.messages)
                self._last_message_sequence = (
                    message_snapshot.last_available_sequence
                )
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

    def _set_capture_controls(self, active: bool) -> None:
        self.start_button.setEnabled(
            not active and self.channel_combo.currentData() is not None
        )
        self.stop_button.setEnabled(active and self._capture.is_active)
        self.channel_combo.setEnabled(not active)
        self.refresh_button.setEnabled(not active)
        self.bitrate_combo.setEnabled(not active)
        self.mode_combo.setEnabled(not active)
        self.session_name.setEnabled(not active)
        self.marker_table.setEnabled(not active)
        self.add_marker_button.setEnabled(not active)
        self.edit_marker_button.setEnabled(not active)
        self.remove_marker_button.setEnabled(not active)

    def _finalize_project_session(self, status) -> None:
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
        self.runtime_marker_hint.setVisible(not presets)
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
                max(0, self.runtime_marker_row.count() - 1),
                button,
            )
            self._marker_buttons.append(button)

    def _clear_marker_controls(self) -> None:
        for shortcut in self._shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._shortcuts.clear()
        for button in self._marker_buttons:
            button.deleteLater()
        self._marker_buttons.clear()
        self.runtime_marker_hint.setVisible(True)

    def _trigger_marker(self, preset: MarkerPreset, *, source: str) -> None:
        try:
            marker = self._capture.add_marker(preset, source=source)
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

    def _add_marker_preset(self) -> None:
        dialog = MarkerPresetDialog(
            areas=[area.name for area in self.project.list_study_areas()],
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        preset = dialog.preset(self.marker_model.rowCount())
        if self._shortcut_conflicts(preset.shortcut):
            QMessageBox.warning(
                self,
                "CRT",
                "Ten skrót jest już przypisany do innego znacznika.",
            )
            return
        self.marker_model.add_preset(preset)
        self._save_marker_presets()

    def _edit_marker_preset(self) -> None:
        rows = self.marker_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "CRT", "Zaznacz znacznik do edycji.")
            return
        row = rows[0].row()
        existing = self.marker_model.preset_at(row)
        if existing is None:
            return
        dialog = MarkerPresetDialog(
            existing=existing,
            areas=[area.name for area in self.project.list_study_areas()],
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.preset(row)
        if self._shortcut_conflicts(updated.shortcut, excluding_id=existing.id):
            QMessageBox.warning(
                self,
                "CRT",
                "Ten skrót jest już przypisany do innego znacznika.",
            )
            return
        self.marker_model.replace_preset(row, updated)
        self._save_marker_presets()

    def _remove_marker_preset(self) -> None:
        rows = self.marker_table.selectionModel().selectedRows()
        if not rows:
            return
        self.marker_model.remove_row(rows[0].row())
        self._save_marker_presets()

    def _save_marker_presets(self) -> None:
        try:
            self.project.save_marker_presets(self.marker_model.presets())
        except Exception as exc:
            QMessageBox.critical(self, "Błąd zapisu znaczników", str(exc))

    def _shortcut_conflicts(self, shortcut: str, *, excluding_id: str = "") -> bool:
        normalized = shortcut.strip().lower()
        return any(
            preset.id != excluding_id
            and preset.shortcut.strip().lower() == normalized
            for preset in self.marker_model.presets()
        )

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
