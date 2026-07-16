from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
)

from app.capture_service import CaptureConfig
from app.dbc import DbcDecoder
from app.project_dbc import active_project_dbc_paths
from kvaser.backend import KvaserReceiveMode

from .live_capture import LiveCaptureWidget


_installed = False


def install_live_save_integration() -> None:
    """Make disk persistence an explicit, one-capture opt-in action."""

    global _installed
    if _installed:
        return
    _installed = True

    original_init = LiveCaptureWidget.__init__
    original_set_capture_controls = LiveCaptureWidget._set_capture_controls
    original_finalize_project_session = LiveCaptureWidget._finalize_project_session

    def integrated_init(self: LiveCaptureWidget, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        self._current_capture_persistent = False
        self._save_reset_pending = False
        self._transient_finalized = False

        self.save_session_button = QPushButton()
        self.save_session_button.setObjectName("armSessionSaveButton")
        self.save_session_button.setCheckable(True)
        self.save_session_button.setChecked(False)
        self.save_session_button.setMinimumHeight(38)
        self.save_session_button.toggled.connect(lambda checked: _update_save_ui(self))

        self.save_session_hint = QLabel()
        self.save_session_hint.setWordWrap(True)

        save_row = QFrame()
        save_row.setObjectName("liveSaveRow")
        save_layout = QHBoxLayout(save_row)
        save_layout.setContentsMargins(7, 5, 7, 5)
        save_layout.addWidget(self.save_session_button)
        save_layout.addWidget(self.save_session_hint, 1)

        connection_group = next(
            (
                group
                for group in self.findChildren(QGroupBox)
                if group.title() == "Połączenie i sesja"
            ),
            None,
        )
        if connection_group is not None and connection_group.layout() is not None:
            connection_group.layout().insertWidget(1, save_row)
        else:
            self.layout().insertWidget(1, save_row)

        _update_save_ui(self)

    def integrated_start_capture(self: LiveCaptureWidget) -> None:
        channel_number = self.channel_combo.currentData()
        if channel_number is None:
            QMessageBox.warning(self, "CRT", "Nie wybrano poprawnego kanału Kvaser.")
            return

        persist = self.save_session_button.isChecked()
        name = self.session_name.text().strip()
        if persist and not name:
            name = datetime.now().strftime("capture_%Y%m%d_%H%M%S")
            self.session_name.setText(name)
        if not name:
            name = datetime.now().strftime("live_preview_%Y%m%d_%H%M%S")

        presets = self.project.list_marker_presets()
        active = [preset for preset in presets if preset.enabled]
        shortcuts = [preset.shortcut.lower() for preset in active]
        if len(shortcuts) != len(set(shortcuts)):
            QMessageBox.warning(self, "CRT", "Aktywne znaczniki mają zduplikowane skróty.")
            return

        dbc_paths = active_project_dbc_paths(self.project)
        paths = None
        try:
            self._dbc_decoder = DbcDecoder(dbc_paths) if dbc_paths else None
            paths = self._capture.start(
                CaptureConfig(
                    channel_number=int(channel_number),
                    bitrate=int(self.bitrate_combo.currentData()),
                    mode=KvaserReceiveMode(str(self.mode_combo.currentData())),
                    session_name=name,
                    output_dir=self.project.live_sessions_dir,
                    persist_to_disk=persist,
                    live_buffer_capacity=self.LIVE_CAPACITY,
                    live_message_capacity=self.LIVE_MESSAGE_CAPACITY,
                    marker_presets=tuple(active),
                )
            )
            if persist:
                if paths is None:
                    raise RuntimeError("tryb zapisu nie utworzył ścieżek sesji")
                self.project.register_session(
                    paths.session,
                    name=name,
                    source="kvaser-live-stream",
                    status="recording",
                )
        except Exception as exc:
            if self._capture.is_active:
                self._capture.stop()
                self._capture.wait(2.0)
            QMessageBox.critical(self, "Nie można rozpocząć rejestracji", str(exc))
            return

        self._current_capture_persistent = persist
        self._save_reset_pending = True
        self._transient_finalized = False
        self._current_session_path = paths.session if paths is not None else None
        self._finalized_session_path = None
        self._last_sequence = None
        self._last_message_sequence = None
        self._error_shown = ""
        self.frame_model.clear()
        self.message_model.clear()
        self.marker_history.clear()
        self.pause_view.setChecked(False)
        if paths is not None:
            self.path_label.setText(f"Sesja zapisywana: {paths.session}")
        else:
            self.path_label.setText(
                "Podgląd Live — zapis na dysk WYŁĄCZONY; dane istnieją tylko w buforze GUI"
            )
        self._install_marker_controls(active)
        self._set_capture_controls(True)
        if persist:
            assert paths is not None
            self.output_message.emit(
                f"Rozpoczęto rejestrację z zapisem: {paths.session} | "
                f"aktywne DBC={len(dbc_paths)}"
            )
            self.project_changed.emit()
        else:
            self.output_message.emit(
                "Rozpoczęto podgląd Live bez zapisu na dysk | "
                f"aktywne DBC={len(dbc_paths)}"
            )
        _update_save_ui(self)

    def integrated_set_capture_controls(self: LiveCaptureWidget, active: bool) -> None:
        original_set_capture_controls(self, active)
        save_button = getattr(self, "save_session_button", None)
        if save_button is None:
            return
        save_button.setEnabled(not active)
        self.session_name.setEnabled(not active and save_button.isChecked())

    def integrated_finalize_project_session(self: LiveCaptureWidget, status) -> None:
        if self._current_session_path is not None:
            original_finalize_project_session(self, status)
        elif not self._transient_finalized:
            self._transient_finalized = True
            self.output_message.emit(
                f"Podgląd Live zakończony bez zapisu | ramki={status.frame_count} | "
                f"wiadomości={status.logical_message_count} | znaczniki={status.marker_count}"
            )

        if self._save_reset_pending:
            self._save_reset_pending = False
            self._current_capture_persistent = False
            self.save_session_button.setChecked(False)
            _update_save_ui(self)

    LiveCaptureWidget.__init__ = integrated_init
    LiveCaptureWidget._start_capture = integrated_start_capture
    LiveCaptureWidget._set_capture_controls = integrated_set_capture_controls
    LiveCaptureWidget._finalize_project_session = integrated_finalize_project_session


def _update_save_ui(widget: LiveCaptureWidget) -> None:
    button = widget.save_session_button
    active = widget._capture.is_active
    if active:
        if widget._current_capture_persistent:
            button.setText("Zapis sesji: AKTYWNY")
            button.setStyleSheet(
                "QPushButton { font-weight: 700; padding: 7px 14px; "
                "border: 2px solid #2e9d52; }"
            )
            widget.save_session_hint.setText(
                "Pełny strumień tej sesji jest zapisywany. Filtry zmieniają tylko widok."
            )
        else:
            button.setText("Zapis sesji: WYŁĄCZONY")
            button.setStyleSheet(
                "QPushButton { font-weight: 700; padding: 7px 14px; "
                "border: 2px solid #b45f06; }"
            )
            widget.save_session_hint.setText(
                "Tryb podglądu: nie są tworzone pliki sesji, CSV ani markerów."
            )
        return

    if button.isChecked():
        button.setText("Zapisz sesję: UZBROJONY")
        button.setStyleSheet(
            "QPushButton { font-weight: 700; padding: 7px 14px; "
            "border: 2px solid #2e9d52; }"
        )
        widget.save_session_hint.setText(
            "Zapis jest uzbrojony dla następnego Start. Po zakończeniu zostanie automatycznie wyłączony."
        )
        widget.session_name.setEnabled(True)
    else:
        button.setText("Zapisz sesję: NIE")
        button.setStyleSheet(
            "QPushButton { font-weight: 700; padding: 7px 14px; "
            "border: 2px solid #b45f06; }"
        )
        widget.save_session_hint.setText(
            "Domyślnie Start uruchamia tylko Live View. Kliknij tutaj przed Start, aby utworzyć sesję na dysku."
        )
        widget.session_name.setEnabled(False)
