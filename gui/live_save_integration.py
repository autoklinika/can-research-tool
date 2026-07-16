from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import QCheckBox, QGroupBox, QMessageBox

from app.capture_service import CaptureConfig
from app.dbc import DbcDecoder
from app.project_dbc import active_project_dbc_paths
from kvaser.backend import KvaserReceiveMode

from .live_capture import LiveCaptureWidget


_installed = False


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


def install_live_save_integration() -> None:
    """Make disk persistence explicit without slowing down capture startup."""

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
        self._dbc_load_generation = 0
        self._dbc_loaded_paths: tuple[Path, ...] = ()
        self._dbc_loading_paths: tuple[Path, ...] = ()
        self._dbc_load_tasks: list[_DbcLoadTask] = []

        self.save_session_button = QCheckBox("Zapisz")
        self.save_session_button.setObjectName("armSessionSaveButton")
        self.save_session_button.setChecked(False)
        self.save_session_button.setToolTip(
            "Zaznacz przed Start, aby zapisać pełną sesję na dysku."
        )
        self.save_session_button.toggled.connect(lambda _checked: _update_save_ui(self))

        connection_group = next(
            (
                group
                for group in self.findChildren(QGroupBox)
                if group.title() == "Połączenie i sesja"
            ),
            None,
        )
        if connection_group is not None and connection_group.layout() is not None:
            session_item = connection_group.layout().itemAt(1)
            session_layout = session_item.layout() if session_item is not None else None
            if session_layout is not None:
                session_layout.insertWidget(max(0, session_layout.count() - 2), self.save_session_button)
            else:
                connection_group.layout().addWidget(self.save_session_button)
        else:
            self.layout().insertWidget(0, self.save_session_button)

        _update_save_ui(self)
        _schedule_dbc_load(self, active_project_dbc_paths(self.project))

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
        _schedule_dbc_load(self, dbc_paths)

        paths = None
        try:
            # Capture starts immediately. DBC construction is intentionally not on
            # this GUI path and may finish shortly after the first frames arrive.
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
        self.path_label.setText(f"Zapis: {paths.session}" if paths is not None else "Live bez zapisu")
        self._install_marker_controls(active)
        self._set_capture_controls(True)

        if persist:
            assert paths is not None
            self.output_message.emit(f"Start z zapisem: {paths.session}")
            self.project_changed.emit()
        else:
            self.output_message.emit("Start Live bez zapisu")
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
                f"Live bez zapisu zakończony | ramki={status.frame_count} | "
                f"wiadomości={status.logical_message_count}"
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


def _schedule_dbc_load(widget: LiveCaptureWidget, paths: tuple[Path, ...]) -> None:
    normalized = tuple(Path(path) for path in paths)
    if normalized == widget._dbc_loaded_paths or normalized == widget._dbc_loading_paths:
        return
    widget._dbc_load_generation += 1
    generation = widget._dbc_load_generation
    widget._dbc_loading_paths = normalized

    if not normalized:
        widget._dbc_decoder = None
        widget._dbc_loaded_paths = ()
        widget._dbc_loading_paths = ()
        return

    task = _DbcLoadTask(normalized)
    widget._dbc_load_tasks.append(task)

    def ready(decoder: object) -> None:
        if generation != widget._dbc_load_generation:
            return
        widget._dbc_decoder = decoder
        widget._dbc_loaded_paths = normalized
        widget._dbc_loading_paths = ()
        widget.output_message.emit(f"Załadowano DBC w tle: {len(normalized)}")
        _trim_dbc_tasks(widget)

    def failed(error: str) -> None:
        if generation != widget._dbc_load_generation:
            return
        widget._dbc_loading_paths = ()
        widget.output_message.emit(f"Błąd ładowania DBC: {error}")
        _trim_dbc_tasks(widget)

    task.signals.ready.connect(ready)
    task.signals.failed.connect(failed)
    QThreadPool.globalInstance().start(task)


def _trim_dbc_tasks(widget: LiveCaptureWidget) -> None:
    widget._dbc_load_tasks = widget._dbc_load_tasks[-2:]


def _update_save_ui(widget: LiveCaptureWidget) -> None:
    checkbox = widget.save_session_button
    active = widget._capture.is_active
    checkbox.setText("Zapisz")
    checkbox.setToolTip(
        "Pełna sesja jest zapisywana na dysku."
        if active and widget._current_capture_persistent
        else "Zaznacz przed Start, aby zapisać pełną sesję na dysku."
    )
    widget.session_name.setEnabled(not active and checkbox.isChecked())
