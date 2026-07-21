from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import QCheckBox, QGroupBox, QMessageBox

from app.dbc import DbcDecoder
from app.live_capture_controller import CaptureMode, StartCaptureRequest
from app.project_dbc import active_project_dbc_paths

if TYPE_CHECKING:
    from app.capture_service import CaptureStatus

    from .live_capture import LiveCaptureWidget


class _DbcLoadSignals(QObject):
    ready = Signal(object)
    failed = Signal(str)


class _DbcLoadTask(QRunnable):
    def __init__(self, paths: tuple[Path, ...]) -> None:
        super().__init__()
        self.paths = paths
        self.signals = _DbcLoadSignals()

    @Slot()
    def run(self) -> None:
        try:
            decoder = DbcDecoder(self.paths) if self.paths else None
        except Exception as exc:
            self.signals.failed.emit(str(exc))
            return
        self.signals.ready.emit(decoder)


class LiveSaveIntegration(QObject):
    """Live persistence with temporary full-session capture and optional retention.

    Every capture writes a complete raw session. The ``Zapisz`` checkbox decides
    whether the session is registered permanently in the project or placed in
    ``.crt/temp/live`` for post-capture analysis. This keeps Live presentation
    bounded while allowing the standard stored-session SQLite pipeline to analyse
    even a capture that was not armed for permanent saving.
    """

    def __init__(self, widget: LiveCaptureWidget) -> None:
        super().__init__(widget)
        self.widget = widget
        self._current_capture_persistent = False
        self._save_reset_pending = False
        self._transient_finalized = False
        self._dbc_load_generation = 0
        self._dbc_loaded_paths: tuple[Path, ...] = ()
        self._dbc_loading_paths: tuple[Path, ...] = ()
        self._dbc_load_tasks: list[_DbcLoadTask] = []

        self.save_checkbox = QCheckBox("Zapisz")
        self.save_checkbox.setObjectName("armSessionSaveButton")
        self.save_checkbox.setChecked(False)
        self.save_checkbox.setToolTip(
            "Zaznacz przed Start, aby zachować sesję w projekcie. "
            "Bez zaznaczenia pełny log trafi do pliku tymczasowego do analizy po STOP."
        )
        self.save_checkbox.toggled.connect(lambda _checked: self.update_ui())
        widget.save_session_button = self.save_checkbox

        connection_group = next(
            (
                group
                for group in widget.findChildren(QGroupBox)
                if group.title() == "Połączenie i sesja"
            ),
            None,
        )
        if connection_group is not None and connection_group.layout() is not None:
            session_item = connection_group.layout().itemAt(1)
            session_layout = session_item.layout() if session_item is not None else None
            if session_layout is not None:
                session_layout.insertWidget(
                    max(0, session_layout.count() - 2),
                    self.save_checkbox,
                )
            else:
                connection_group.layout().addWidget(self.save_checkbox)
        else:
            widget.layout().insertWidget(0, self.save_checkbox)

        self.update_ui()
        self._schedule_dbc_load(active_project_dbc_paths(widget.project))

    def start_capture(self) -> None:
        widget = self.widget
        channel_number = widget.channel_combo.currentData()
        if channel_number is None:
            QMessageBox.warning(
                widget,
                "CRT",
                "Nie wybrano poprawnego kanału Kvaser.",
            )
            return

        persist = self.save_checkbox.isChecked()
        name = widget.session_name.text().strip()
        if persist and not name:
            name = datetime.now().strftime("capture_%Y%m%d_%H%M%S")
            widget.session_name.setText(name)
        if not name:
            name = datetime.now().strftime("live_temp_%Y%m%d_%H%M%S")

        presets = widget.project.list_marker_presets()
        active = [preset for preset in presets if preset.enabled]
        shortcuts = [preset.shortcut.lower() for preset in active]
        if len(shortcuts) != len(set(shortcuts)):
            QMessageBox.warning(
                widget,
                "CRT",
                "Aktywne znaczniki mają zduplikowane skróty.",
            )
            return

        dbc_paths = active_project_dbc_paths(widget.project)
        self._schedule_dbc_load(dbc_paths)

        output_dir = (
            widget.project.live_sessions_dir
            if persist
            else Path(widget.project.root) / ".crt" / "temp" / "live"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        paths = None
        try:
            paths = widget._controller.start(
                StartCaptureRequest(
                    channel_number=int(channel_number),
                    bitrate=int(widget.bitrate_combo.currentData()),
                    mode=CaptureMode(str(widget.mode_combo.currentData())),
                    session_name=name,
                    output_dir=output_dir,
                    # A complete raw session is always required for deferred analysis.
                    persist_to_disk=True,
                    live_buffer_capacity=widget.LIVE_CAPACITY,
                    live_message_capacity=widget.LIVE_MESSAGE_CAPACITY,
                    marker_presets=tuple(active),
                )
            )
            if paths is None:
                raise RuntimeError("rejestracja nie utworzyła ścieżek sesji")
            if persist:
                widget.project.register_session(
                    paths.session,
                    name=name,
                    source="kvaser-live-stream",
                    status="recording",
                )
        except Exception as exc:
            if widget._controller.is_active:
                widget._controller.stop()
                widget._controller.wait(2.0)
            QMessageBox.critical(
                widget,
                "Nie można rozpocząć rejestracji",
                str(exc),
            )
            return

        self._current_capture_persistent = persist
        self._save_reset_pending = True
        self._transient_finalized = False
        widget._analysis_session_path = paths.session
        widget._current_session_path = paths.session if persist else None
        widget._finalized_session_path = None
        widget._last_sequence = None
        widget._last_message_sequence = None
        widget._error_shown = ""
        widget.frame_model.clear()
        widget.message_model.clear()
        widget.marker_history.clear()
        widget.pause_view.setChecked(False)
        widget.path_label.setText(
            f"Zapis trwały: {paths.session}"
            if persist
            else f"Plik tymczasowy do analizy: {paths.session}"
        )
        widget._install_marker_controls(active)
        widget._set_capture_controls(True)

        if persist:
            widget.output_message.emit(f"Start z zapisem: {paths.session}")
            widget.project_changed.emit()
        else:
            widget.output_message.emit(
                f"Start Live z pełnym plikiem tymczasowym: {paths.session}"
            )
        self.update_ui()

    def update_controls(self, active: bool) -> None:
        self.save_checkbox.setEnabled(not active)
        self.widget.session_name.setEnabled(
            not active and self.save_checkbox.isChecked()
        )

    def finalize(self, status: CaptureStatus) -> None:
        if self._current_capture_persistent:
            if self.widget._current_session_path is not None:
                self.widget._finalize_persistent_session(status)
        elif not self._transient_finalized:
            self._transient_finalized = True
            path = getattr(self.widget, "_analysis_session_path", None)
            self.widget.output_message.emit(
                f"Tymczasowy Live zakończony | ramki={status.frame_count} | "
                f"analiza={path or 'brak pliku'}"
            )

        if self._save_reset_pending:
            self._save_reset_pending = False
            self._current_capture_persistent = False
            self.save_checkbox.setChecked(False)
            self.update_ui()

    def update_ui(self) -> None:
        active = self.widget._controller.is_active
        self.save_checkbox.setText("Zapisz")
        if active and self._current_capture_persistent:
            tooltip = "Pełna sesja jest zapisywana i zostanie zachowana w projekcie."
        elif active:
            tooltip = "Pełna sesja jest zapisywana tymczasowo do analizy po STOP."
        else:
            tooltip = (
                "Zaznacz przed Start, aby zachować sesję w projekcie. "
                "Bez zaznaczenia powstanie pełny plik tymczasowy."
            )
        self.save_checkbox.setToolTip(tooltip)
        self.widget.session_name.setEnabled(
            not active and self.save_checkbox.isChecked()
        )

    def _schedule_dbc_load(self, paths: tuple[Path, ...]) -> None:
        normalized = tuple(Path(path) for path in paths)
        if (
            normalized == self._dbc_loaded_paths
            or normalized == self._dbc_loading_paths
        ):
            return
        self._dbc_load_generation += 1
        generation = self._dbc_load_generation
        self._dbc_loading_paths = normalized

        if not normalized:
            self.widget._dbc_decoder = None
            self._dbc_loaded_paths = ()
            self._dbc_loading_paths = ()
            return

        task = _DbcLoadTask(normalized)
        self._dbc_load_tasks.append(task)

        def ready(decoder: object) -> None:
            if generation != self._dbc_load_generation:
                return
            self.widget._dbc_decoder = decoder
            self._dbc_loaded_paths = normalized
            self._dbc_loading_paths = ()
            self.widget.output_message.emit(
                f"Załadowano DBC w tle: {len(normalized)}"
            )
            self._trim_dbc_tasks()

        def failed(error: str) -> None:
            if generation != self._dbc_load_generation:
                return
            self._dbc_loading_paths = ()
            self.widget.output_message.emit(f"Błąd ładowania DBC: {error}")
            self._trim_dbc_tasks()

        task.signals.ready.connect(ready)
        task.signals.failed.connect(failed)
        QThreadPool.globalInstance().start(task)

    def _trim_dbc_tasks(self) -> None:
        self._dbc_load_tasks = self._dbc_load_tasks[-2:]
