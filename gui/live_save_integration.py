from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import QMessageBox

from app.capture_service import CapturePaths, CaptureStatus
from app.dbc import DbcDecoder
from app.live_capture_controller import CaptureMode, StartCaptureRequest
from app.logical_cache import logical_cache_path_for_session
from app.project_dbc import active_project_dbc_paths

if TYPE_CHECKING:
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
    """Always capture to temp and explicitly promote the finished log to project.

    Live never writes directly into ``sessions/live``. A completed capture remains
    pending in ``.crt/temp/live`` until the operator chooses ``Plik -> Zapisz log``.
    Starting another capture, closing Live, changing project or exiting must first
    resolve that pending log by saving, discarding or cancelling the operation.
    """

    def __init__(self, widget: LiveCaptureWidget) -> None:
        super().__init__(widget)
        self.widget = widget
        self._pending_paths: CapturePaths | None = None
        self._pending_status: CaptureStatus | None = None
        self._pending_name = ""
        self._transient_finalized = False
        self._dbc_load_generation = 0
        self._dbc_loaded_paths: tuple[Path, ...] = ()
        self._dbc_loading_paths: tuple[Path, ...] = ()
        self._dbc_load_tasks: list[_DbcLoadTask] = []
        self._schedule_dbc_load(active_project_dbc_paths(widget.project))

    @property
    def has_unsaved_log(self) -> bool:
        paths = self._pending_paths
        return bool(
            paths is not None
            and self._pending_status is not None
            and paths.session.is_file()
        )

    @property
    def pending_session_path(self) -> Path | None:
        paths = self._pending_paths
        return None if paths is None else paths.session

    def start_capture(self) -> None:
        if self.has_unsaved_log and not self.confirm_pending_log(reason="new_capture"):
            self._restore_pending_ui()
            return

        widget = self.widget
        channel_number = widget.channel_combo.currentData()
        if channel_number is None:
            QMessageBox.warning(
                widget,
                "CRT",
                "Nie wybrano poprawnego kanału Kvaser.",
            )
            return

        name = widget.session_name.text().strip()
        if not name:
            name = datetime.now().strftime("capture_%Y%m%d_%H%M%S")
            widget.session_name.setText(name)

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

        output_dir = Path(widget.project.root) / ".crt" / "temp" / "live"
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            paths = widget._controller.start(
                StartCaptureRequest(
                    channel_number=int(channel_number),
                    bitrate=int(widget.bitrate_combo.currentData()),
                    mode=CaptureMode(str(widget.mode_combo.currentData())),
                    session_name=name,
                    output_dir=output_dir,
                    persist_to_disk=True,
                    live_buffer_capacity=widget.LIVE_CAPACITY,
                    live_message_capacity=widget.LIVE_MESSAGE_CAPACITY,
                    marker_presets=tuple(active),
                )
            )
            if paths is None:
                raise RuntimeError("rejestracja nie utworzyła ścieżek sesji")
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

        self._pending_paths = paths
        self._pending_status = None
        self._pending_name = name
        self._transient_finalized = False
        widget._analysis_session_path = paths.session
        widget._current_session_path = None
        widget._finalized_session_path = None
        widget._last_sequence = None
        widget._last_message_sequence = None
        widget._error_shown = ""
        widget.frame_model.clear()
        widget.message_model.clear()
        widget.marker_history.clear()
        widget.pause_view.setChecked(False)
        widget.path_label.setText(f"Rejestracja tymczasowa: {paths.session}")
        widget._install_marker_controls(active)
        widget._set_capture_controls(True)
        widget.output_message.emit(
            f"Start Live do pliku tymczasowego: {paths.session}"
        )

    def update_controls(self, active: bool) -> None:
        self.widget.session_name.setEnabled(not active)

    def finalize(self, status: CaptureStatus) -> None:
        if self._transient_finalized:
            return
        paths = self._pending_paths
        if paths is None:
            return

        self._transient_finalized = True
        self._pending_status = status
        self.widget.path_label.setText(
            f"Niezapisany log: {paths.session} | Plik → Zapisz log"
        )
        self.widget.output_message.emit(
            f"Live zakończony — log oczekuje na zapis | "
            f"ramki={status.frame_count} | znaczniki={status.marker_count} | "
            f"plik={paths.session}"
        )

    def save_pending_log(self) -> bool:
        if not self.has_unsaved_log:
            return False
        paths = self._pending_paths
        status = self._pending_status
        assert paths is not None
        assert status is not None

        was_open = self._close_open_session(paths.session)
        try:
            destination = self._destination_paths(paths)
            self._move_capture_artifacts(paths, destination)
            self.widget.project.register_session(
                destination.session,
                name=self._pending_name or destination.session.stem,
                source="kvaser-live-stream",
                status="ready",
            )
            self.widget.project.finalize_session(
                destination.session,
                frame_count=status.frame_count,
                marker_count=status.marker_count,
                duration_s=status.elapsed_s,
                status="error" if status.state.value == "error" else "ready",
            )
        except Exception as exc:
            QMessageBox.critical(
                self.widget,
                "Nie można zapisać logu",
                str(exc),
            )
            self._restore_pending_ui()
            return False

        old_session = paths.session
        self._pending_paths = None
        self._pending_status = None
        self._pending_name = ""
        self._transient_finalized = False
        self.widget._analysis_session_path = destination.session
        self.widget._current_session_path = destination.session
        self.widget._finalized_session_path = destination.session
        self.widget.path_label.setText(f"Log zapisany w projekcie: {destination.session}")
        self.widget.output_message.emit(
            f"Zapisano log w projekcie: {old_session} → {destination.session}"
        )
        self.widget.project_changed.emit()

        main_window = self.widget.window()
        opener = getattr(main_window, "_open_session", None)
        if was_open and callable(opener):
            opener(str(destination.session))
        return True

    def discard_pending_log(self) -> bool:
        paths = self._pending_paths
        if paths is None:
            return True
        self._close_open_session(paths.session)
        errors: list[str] = []
        for path in self._artifact_paths(paths):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"{path.name}: {exc}")
        if errors:
            QMessageBox.critical(
                self.widget,
                "Nie można odrzucić logu",
                "\n".join(errors),
            )
            return False

        self._pending_paths = None
        self._pending_status = None
        self._pending_name = ""
        self._transient_finalized = False
        self.widget._analysis_session_path = None
        self.widget._current_session_path = None
        self.widget._finalized_session_path = None
        self.widget.path_label.setText(f"Projekt: {self.widget.project.root}")
        load_button = getattr(self.widget, "load_deferred_logical_button", None)
        if load_button is not None:
            load_button.setEnabled(False)
        status_label = getattr(self.widget, "deferred_logical_status", None)
        if status_label is not None:
            status_label.setText(
                "Brak zakończonego logu. Uruchom rejestrację, a po STOP możesz go przeanalizować lub zapisać."
            )
        self.widget.output_message.emit("Odrzucono niezapisany log tymczasowy.")
        return True

    def confirm_pending_log(self, *, reason: str) -> bool:
        if not self.has_unsaved_log:
            return True

        if reason == "new_capture":
            informative = (
                "Rozpoczęcie nowej rejestracji zastąpi bieżący log tymczasowy."
            )
        elif reason == "project_change":
            informative = "Zmiana projektu odrzuci bieżący log tymczasowy."
        elif reason == "close_tab":
            informative = "Zamknięcie zakładki Live odrzuci bieżący log tymczasowy."
        else:
            informative = "Zamknięcie programu odrzuci bieżący log tymczasowy."

        dialog = QMessageBox(self.widget)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Niezapisany log")
        dialog.setText("Zarejestrowany log nie został zapisany w projekcie.")
        dialog.setInformativeText(informative)
        save_button = dialog.addButton(
            "Zapisz log",
            QMessageBox.ButtonRole.AcceptRole,
        )
        discard_button = dialog.addButton(
            "Nie zapisuj",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = dialog.addButton(
            "Anuluj",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(save_button)
        dialog.exec()

        clicked = dialog.clickedButton()
        if clicked is save_button:
            return self.save_pending_log()
        if clicked is discard_button:
            return self.discard_pending_log()
        if clicked is cancel_button:
            self._restore_pending_ui()
            return False
        self._restore_pending_ui()
        return False

    def update_ui(self) -> None:
        """Compatibility hook retained for the Live widget control integration."""

        self.widget.session_name.setEnabled(not self.widget._controller.is_active)

    def _restore_pending_ui(self) -> None:
        paths = self._pending_paths
        if paths is None:
            return
        self.widget._analysis_session_path = paths.session
        load_button = getattr(self.widget, "load_deferred_logical_button", None)
        if load_button is not None:
            load_button.setEnabled(paths.session.is_file())
        status_label = getattr(self.widget, "deferred_logical_status", None)
        if status_label is not None:
            status_label.setText(
                "Rejestracja zakończona. Kliknij Załaduj, aby otworzyć analizę, "
                "albo wybierz Plik → Zapisz log."
            )
        self.widget.path_label.setText(
            f"Niezapisany log: {paths.session} | Plik → Zapisz log"
        )

    def _destination_paths(self, source: CapturePaths) -> CapturePaths:
        directory = self.widget.project.live_sessions_dir
        directory.mkdir(parents=True, exist_ok=True)
        original = source.session.name.removesuffix(".crt.jsonl")
        base = original
        suffix = 2
        while self._destination_base_exists(directory, base):
            base = f"{original}_{suffix:02d}"
            suffix += 1
        return CapturePaths(
            session=directory / f"{base}.crt.jsonl",
            raw_frames_csv=directory / f"{base}.frames.csv",
            logical_messages_csv=directory / f"{base}.messages.csv",
            markers=directory / f"{base}.markers.jsonl",
        )

    @staticmethod
    def _destination_base_exists(directory: Path, base: str) -> bool:
        names = (
            f"{base}.crt.jsonl",
            f"{base}.frames.csv",
            f"{base}.messages.csv",
            f"{base}.markers.jsonl",
            f"{base}.logical.sqlite",
        )
        return any((directory / name).exists() for name in names)

    def _move_capture_artifacts(
        self,
        source: CapturePaths,
        destination: CapturePaths,
    ) -> None:
        pairs = [
            (source.session, destination.session),
            (source.raw_frames_csv, destination.raw_frames_csv),
            (source.logical_messages_csv, destination.logical_messages_csv),
            (source.markers, destination.markers),
        ]
        source_cache = logical_cache_path_for_session(source.session)
        destination_cache = logical_cache_path_for_session(destination.session)
        pairs.extend(
            (
                (source_cache, destination_cache),
                (Path(str(source_cache) + "-wal"), Path(str(destination_cache) + "-wal")),
                (Path(str(source_cache) + "-shm"), Path(str(destination_cache) + "-shm")),
                (
                    Path(str(source_cache) + "-journal"),
                    Path(str(destination_cache) + "-journal"),
                ),
            )
        )
        destination.session.parent.mkdir(parents=True, exist_ok=True)
        moved: list[tuple[Path, Path]] = []
        try:
            for old, new in pairs:
                if not old.exists():
                    continue
                shutil.move(str(old), str(new))
                moved.append((old, new))
        except Exception:
            for old, new in reversed(moved):
                if new.exists() and not old.exists():
                    shutil.move(str(new), str(old))
            raise

    def _artifact_paths(self, paths: CapturePaths) -> tuple[Path, ...]:
        cache = logical_cache_path_for_session(paths.session)
        return (
            paths.session,
            paths.raw_frames_csv,
            paths.logical_messages_csv,
            paths.markers,
            cache,
            Path(str(cache) + "-wal"),
            Path(str(cache) + "-shm"),
            Path(str(cache) + "-journal"),
        )

    def _close_open_session(self, path: Path) -> bool:
        main_window = self.widget.window()
        navigator = getattr(main_window, "navigator", None)
        if navigator is None:
            return False
        key_fn = getattr(navigator, "session_key", None)
        widget_fn = getattr(navigator, "widget", None)
        close_fn = getattr(navigator, "close_session", None)
        if not callable(key_fn) or not callable(widget_fn) or not callable(close_fn):
            return False
        was_open = widget_fn(key_fn(path)) is not None
        if was_open:
            close_fn(path)
        return was_open

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
