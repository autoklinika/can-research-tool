from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.capture_service import CaptureState

from .live_capture import LiveCaptureWidget
from .project_navigator import ProjectNavigator

LIVE_PREVIEW_FRAME_CAPACITY = 20_000
LIVE_PREVIEW_MESSAGE_CAPACITY = 1


class BoundedLiveCaptureWidget(LiveCaptureWidget):
    """Production Live Capture with raw-only realtime presentation.

    Full raw traffic is always persisted by ``LiveSaveIntegration``. Logical
    messages are deliberately not requested, decoded or rendered while capture
    is active. After STOP the operator can open the completed temporary or
    permanent session through the same SQLite-backed stored-session workspace.
    """

    LIVE_CAPACITY = LIVE_PREVIEW_FRAME_CAPACITY
    LIVE_MESSAGE_CAPACITY = LIVE_PREVIEW_MESSAGE_CAPACITY

    def __init__(self, *args, **kwargs) -> None:
        self._analysis_session_path: Path | None = None
        super().__init__(*args, **kwargs)
        self.marker_setup_button.setMinimumSize(190, 40)
        self.marker_setup_button.setStyleSheet(
            "QPushButton { text-align: center; padding: 5px 10px; font-weight: 600; }"
        )
        self._update_marker_tile()
        self._install_space_capture_shortcut()
        self._install_marker_history_navigation()
        self._install_deferred_logical_controls()

    def _update_marker_tile(self) -> None:
        presets = self.project.list_marker_presets()
        active = sum(preset.enabled for preset in presets)
        self.marker_setup_button.setText(f"Znaczniki: {active}/{len(presets)}")
        self.marker_setup_button.setToolTip(
            "Otwórz konfigurację znaczników. "
            f"Aktywne: {active}, wszystkie: {len(presets)}."
        )

    def _install_space_capture_shortcut(self) -> None:
        self.capture_space_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self.capture_space_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self.capture_space_shortcut.setAutoRepeat(False)
        self.capture_space_shortcut.activated.connect(self._toggle_capture_from_space)
        self.start_button.setToolTip("Rozpocznij rejestrację — Spacja")
        self.stop_button.setToolTip("Zatrzymaj rejestrację — Spacja")

    def _toggle_capture_from_space(self) -> None:
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QComboBox, QPushButton, QCheckBox)):
            return

        if self._controller.is_active:
            if self.stop_button.isEnabled():
                self._stop_capture()
            return

        if self.start_button.isEnabled():
            self._start_capture()

    def _install_marker_history_navigation(self) -> None:
        self.marker_history.setToolTip(
            "Kliknij dwukrotnie znacznik, aby przejść do najbliższej surowej ramki."
        )
        self.marker_history.itemDoubleClicked.connect(
            self._jump_to_marker_from_history
        )

    def _trigger_marker(self, preset, *, source: str) -> None:
        before = self.marker_history.count()
        super()._trigger_marker(preset, source=source)
        if self.marker_history.count() <= before:
            return
        item = self.marker_history.item(self.marker_history.count() - 1)
        if item is None:
            return
        try:
            timestamp_ms = float(item.text().split("ms", 1)[0].strip())
        except (TypeError, ValueError):
            return
        item.setData(Qt.ItemDataRole.UserRole, int(round(timestamp_ms * 1_000_000)))

    def _jump_to_marker_from_history(self, item, _column: int = 0) -> None:
        timestamp_ns = item.data(Qt.ItemDataRole.UserRole)
        if timestamp_ns is None:
            try:
                timestamp_ms = float(item.text().split("ms", 1)[0].strip())
            except (TypeError, ValueError):
                self.output_message.emit("Nie można odczytać czasu wybranego znacznika.")
                return
            timestamp_ns = int(round(timestamp_ms * 1_000_000))

        model = self.frame_table.model()
        frame_at = getattr(model, "frame_at", None)
        if not callable(frame_at) or model.rowCount() <= 0:
            self.output_message.emit("Brak surowych ramek dostępnych dla znacznika.")
            return

        target_row = -1
        target_frame = None
        best_delta = None
        for row in range(model.rowCount()):
            frame = frame_at(row)
            if frame is None:
                continue
            delta = abs(int(frame.timestamp_ns) - int(timestamp_ns))
            if best_delta is None or delta < best_delta:
                best_delta = delta
                target_row = row
                target_frame = frame
            if int(frame.timestamp_ns) >= int(timestamp_ns) and best_delta == delta:
                break

        if target_row < 0 or target_frame is None:
            self.output_message.emit("Nie znaleziono ramki odpowiadającej znacznikowi.")
            return

        self.data_tabs.setCurrentIndex(self.raw_tab_index)
        self.pause_view.setChecked(True)
        self.auto_scroll.setChecked(False)
        index = model.index(target_row, 0)
        self.frame_table.setCurrentIndex(index)
        self.frame_table.selectRow(target_row)
        self.frame_table.scrollTo(
            index,
            QAbstractItemView.ScrollHint.PositionAtCenter,
        )
        self.frame_table.setFocus(Qt.FocusReason.OtherFocusReason)
        self.output_message.emit(
            "Przejście do znacznika: "
            f"ramka {target_frame.sequence}, "
            f"czas {target_frame.timestamp_ns / 1_000_000:.3f} ms, "
            f"różnica {int(best_delta or 0) / 1_000_000:.3f} ms."
        )

    def _install_deferred_logical_controls(self) -> None:
        page = self.data_tabs.widget(self.message_tab_index)
        layout = page.layout() if page is not None else None
        if page is None or layout is None:
            return

        self.message_table.hide()
        self.deferred_logical_status = QLabel(
            "Wiadomości logiczne nie są analizowane na żywo. "
            "Zakończ rejestrację i kliknij Załaduj.",
            page,
        )
        self.deferred_logical_status.setObjectName("deferredLiveLogicalStatus")
        self.deferred_logical_status.setWordWrap(True)

        self.load_deferred_logical_button = QPushButton("Załaduj", page)
        self.load_deferred_logical_button.setObjectName("loadDeferredLiveLogicalMessages")
        self.load_deferred_logical_button.setEnabled(False)
        self.load_deferred_logical_button.setToolTip(
            "Otwórz zakończony zapis Live przez ten sam cache SQLite co zapisaną sesję."
        )
        self.load_deferred_logical_button.clicked.connect(
            self._open_deferred_logical_session
        )

        container = QVBoxLayout()
        container.addStretch(1)
        container.addWidget(self.deferred_logical_status)
        container.addWidget(self.load_deferred_logical_button)
        container.addStretch(1)
        layout.addLayout(container)
        self.data_tabs.setTabText(
            self.message_tab_index,
            "Wiadomości logiczne — po STOP",
        )

    def _start_capture(self) -> None:
        self._analysis_session_path = None
        self.load_deferred_logical_button.setEnabled(False)
        self.deferred_logical_status.setText(
            "Rejestracja trwa. Analiza logiczna jest wyłączona, aby nie obciążać aplikacji."
        )
        self.message_model.clear()
        super()._start_capture()

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

        active = status.state in (
            CaptureState.STARTING,
            CaptureState.RUNNING,
            CaptureState.STOPPING,
        )
        self._set_capture_controls(active)

        if status.state in (CaptureState.STOPPED, CaptureState.ERROR):
            self._finalize_project_session(status)
            self._clear_marker_controls()
            ready = (
                self._analysis_session_path is not None
                and self._analysis_session_path.is_file()
            )
            self.load_deferred_logical_button.setEnabled(ready)
            if ready:
                self.deferred_logical_status.setText(
                    "Rejestracja zakończona. Kliknij Załaduj, aby zbudować lub otworzyć "
                    "obraz analityczny SQLite."
                )

        if (
            status.state == CaptureState.ERROR
            and status.error
            and status.error != self._error_shown
        ):
            self._error_shown = status.error
            from PySide6.QtWidgets import QMessageBox

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
        self.messages_label.setText("Wiadomości: analiza po STOP")
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
            "Wiadomości logiczne — Załaduj" if not self._controller.is_active
            else "Wiadomości logiczne — po STOP",
        )
        self.status_text.emit(
            f"{status.state.value.upper()} | {status.frame_count:,} ramek | "
            f"{status.live_retained:,}/{status.live_capacity:,} live".replace(",", " ")
        )
        self._live_filter_integration.update_status(status.frame_count, 0)

    def _open_deferred_logical_session(self) -> None:
        path = self._analysis_session_path
        if path is None or not path.is_file():
            self.deferred_logical_status.setText(
                "Brak zakończonego pliku tymczasowego do analizy."
            )
            return

        main_window = self.window()
        opener = getattr(main_window, "_open_session", None)
        navigator = getattr(main_window, "navigator", None)
        if not callable(opener) or navigator is None:
            self.deferred_logical_status.setText(
                "Nie można otworzyć sesji w bieżącym oknie aplikacji."
            )
            return

        opener(str(path))
        stored = navigator.widget(ProjectNavigator.session_key(path))
        if stored is not None and hasattr(stored, "message_tab_index"):
            stored.tabs.setCurrentIndex(stored.message_tab_index)
        self.deferred_logical_status.setText(
            "Sesja została otwarta w standardowym widoku zapisanych logów."
        )
