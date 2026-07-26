from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication

from app.comparison_evidence import (
    ComparisonEvidenceCancelled,
    ComparisonEvidenceLocation,
    locate_comparison_evidence,
)

from .comparison_evidence_stored_navigation import (
    ComparisonStoredSearchNavigator,
)

if TYPE_CHECKING:
    from .main_window import MainWindow


class _EvidenceSignals(QObject):
    completed = Signal(int, object)
    failed = Signal(int, str)
    finished = Signal(int)


class _EvidenceTask(QRunnable):
    def __init__(
        self,
        generation: int,
        project,
        session_id: str,
        message_key: str,
        cancel_event: Event,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.generation = generation
        self.project = project
        self.session_id = session_id
        self.message_key = message_key
        self.cancel_event = cancel_event
        self.signals = _EvidenceSignals()

    @Slot()
    def run(self) -> None:
        try:
            try:
                location = locate_comparison_evidence(
                    self.project,
                    self.session_id,
                    self.message_key,
                    should_cancel=self.cancel_event.is_set,
                )
            except ComparisonEvidenceCancelled:
                return
            except Exception as exc:  # pragma: no cover - surfaced through GUI
                if not self.cancel_event.is_set():
                    self.signals.failed.emit(self.generation, str(exc))
                return
            if not self.cancel_event.is_set():
                self.signals.completed.emit(self.generation, location)
        finally:
            self.signals.finished.emit(self.generation)


@dataclass(slots=True)
class _EvidenceRequest:
    project: Any
    cancel_event: Event
    on_opened: Callable[[ComparisonEvidenceLocation], None] | None
    on_failed: Callable[[str], None] | None


class ComparisonEvidenceCoordinator(QObject):
    """Open source sessions and confirm selection of matching raw frames."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._window = window
        self._generation = 0
        self._tasks: dict[int, _EvidenceTask] = {}
        self._requests: dict[int, _EvidenceRequest] = {}
        window.destroyed.connect(self._window_destroyed)

    def open_evidence(
        self,
        session_id: str,
        message_key: str,
        *,
        on_opened: Callable[[ComparisonEvidenceLocation], None] | None = None,
        on_failed: Callable[[str], None] | None = None,
    ) -> None:
        project = self._window.project
        if project is None:
            error = "Nie można otworzyć dowodów bez aktywnego projektu."
            self._report(error)
            if on_failed is not None:
                on_failed(error)
            return

        self._generation += 1
        generation = self._generation
        cancel_event = Event()
        self._requests[generation] = _EvidenceRequest(
            project=project,
            cancel_event=cancel_event,
            on_opened=on_opened,
            on_failed=on_failed,
        )
        self._report(f"Szukam dowodów dla {message_key} w zapisanej sesji…")
        task = _EvidenceTask(
            generation,
            project,
            session_id,
            message_key,
            cancel_event,
        )
        task.signals.completed.connect(self._location_ready)
        task.signals.failed.connect(self._location_failed)
        task.signals.finished.connect(self._task_finished)
        self._tasks[generation] = task
        QThreadPool.globalInstance().start(task)

    @Slot(int, object)
    def _location_ready(self, generation: int, value: object) -> None:
        request = self._requests.get(generation)
        if request is None:
            return
        if not isinstance(value, ComparisonEvidenceLocation):
            self._finish_failed(
                generation,
                "Nie udało się odczytać lokalizacji dowodu.",
            )
            return

        window = self._window
        if window.project is not request.project:
            self._finish_failed(
                generation,
                "Aktywny projekt zmienił się podczas wyszukiwania dowodu.",
            )
            return
        try:
            view = window.navigator.open_session(
                value.session_path,
                project=request.project,
                inspector_sink=window.inspector.setPlainText,
                output_sink=window._append_output,
            )
            navigator = getattr(view, "_comparison_evidence_navigator", None)
            if not isinstance(navigator, ComparisonStoredSearchNavigator):
                navigator = ComparisonStoredSearchNavigator(view, parent=view)
                view._comparison_evidence_navigator = navigator
            navigator.navigate_to_source_row(
                value.source_row,
                on_selected=lambda g=generation, v=value: self._navigation_succeeded(
                    g,
                    v,
                ),
                on_failed=lambda error, g=generation: self._finish_failed(
                    g,
                    error,
                ),
            )
        except Exception as exc:  # pragma: no cover - surfaced through GUI
            self._finish_failed(generation, str(exc))

    def _navigation_succeeded(
        self,
        generation: int,
        value: ComparisonEvidenceLocation,
    ) -> None:
        request = self._requests.get(generation)
        if request is None:
            return
        window = self._window
        if window.project is not request.project:
            self._finish_failed(
                generation,
                "Aktywny projekt zmienił się przed zaznaczeniem dowodu.",
            )
            return

        self._requests.pop(generation, None)
        self._report(
            f"Otwarto dowód: {value.message_key}, "
            f"ramka źródłowa {value.source_row + 1}."
        )
        callback = request.on_opened
        if callback is not None:
            try:
                callback(value)
            except RuntimeError:
                pass

        _activate_main_window(window)
        QTimer.singleShot(0, lambda target=window: _activate_main_window(target))

    @Slot(int, str)
    def _location_failed(self, generation: int, error: str) -> None:
        self._finish_failed(generation, error)

    def _finish_failed(self, generation: int, error: str) -> None:
        request = self._requests.pop(generation, None)
        if request is None:
            return
        request.cancel_event.set()
        message = f"Nie udało się otworzyć dowodów: {error}"
        self._report(message)
        callback = request.on_failed
        if callback is not None:
            try:
                callback(error)
            except RuntimeError:
                pass

    @Slot(int)
    def _task_finished(self, generation: int) -> None:
        self._tasks.pop(generation, None)

    def cancel_all(self, reason: str = "Nawigacja została anulowana.") -> None:
        for generation in tuple(self._requests):
            self._finish_failed(generation, reason)
        for task in tuple(self._tasks.values()):
            task.cancel_event.set()

    def _report(self, message: str) -> None:
        try:
            self._window._append_output(message)
        except RuntimeError:
            pass

    def _window_destroyed(self, *_args: object) -> None:
        for request in self._requests.values():
            request.cancel_event.set()
        for task in self._tasks.values():
            task.cancel_event.set()
        self._requests.clear()


def _activate_main_window(window) -> None:
    try:
        if window.isMinimized():
            window.showNormal()
        else:
            window.show()
        window.raise_()
        window.activateWindow()
        QApplication.setActiveWindow(window)
    except RuntimeError:
        pass
