from __future__ import annotations

from threading import Event
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from app.comparison_evidence import (
    ComparisonEvidenceCancelled,
    ComparisonEvidenceLocation,
    locate_comparison_evidence,
)

from .stored_search_navigation import StoredSearchNavigator

if TYPE_CHECKING:
    from .main_window import MainWindow


class _EvidenceSignals(QObject):
    completed = Signal(int, object)
    failed = Signal(int, str)


class _EvidenceTask(QRunnable):
    def __init__(
        self,
        generation: int,
        project,
        session_id: str,
        message_key: str,
    ) -> None:
        super().__init__()
        self.generation = generation
        self.project = project
        self.session_id = session_id
        self.message_key = message_key
        self.cancel_event = Event()
        self.signals = _EvidenceSignals()

    def cancel(self) -> None:
        self.cancel_event.set()

    @Slot()
    def run(self) -> None:
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


class ComparisonEvidenceCoordinator(QObject):
    """Open one source session and navigate to the first matching raw frame."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._window = window
        self._generation = 0
        self._tasks: list[_EvidenceTask] = []
        window.destroyed.connect(self._window_destroyed)

    def open_evidence(self, session_id: str, message_key: str) -> None:
        project = self._window.project
        if project is None:
            self._report("Nie można otworzyć dowodów bez aktywnego projektu.")
            return
        self._generation += 1
        generation = self._generation
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        self._report(f"Szukam dowodów dla {message_key} w zapisanej sesji…")
        task = _EvidenceTask(
            generation,
            project,
            session_id,
            message_key,
        )
        task.signals.completed.connect(self._location_ready)
        task.signals.failed.connect(self._location_failed)
        self._tasks.append(task)
        QThreadPool.globalInstance().start(task)

    @Slot(int, object)
    def _location_ready(self, generation: int, value: object) -> None:
        if generation != self._generation:
            return
        if not isinstance(value, ComparisonEvidenceLocation):
            self._report("Nie udało się odczytać lokalizacji dowodu.")
            return
        window = self._window
        project = window.project
        if project is None:
            return
        view = window.navigator.open_session(
            value.session_path,
            project=project,
            inspector_sink=window.inspector.setPlainText,
            output_sink=window._append_output,
        )
        navigator = getattr(view, "_comparison_evidence_navigator", None)
        if not isinstance(navigator, StoredSearchNavigator):
            navigator = StoredSearchNavigator(view, parent=view)
            view._comparison_evidence_navigator = navigator
        navigator.navigate_to_source_row(value.source_row)
        window.raise_()
        window.activateWindow()
        self._report(
            f"Otwarto dowód: {value.message_key}, "
            f"ramka źródłowa {value.source_row + 1}."
        )

    @Slot(int, str)
    def _location_failed(self, generation: int, error: str) -> None:
        if generation != self._generation:
            return
        self._report(f"Nie udało się otworzyć dowodów: {error}")

    def _report(self, message: str) -> None:
        try:
            self._window._append_output(message)
        except RuntimeError:
            pass

    def _window_destroyed(self, *_args: object) -> None:
        self._generation += 1
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
