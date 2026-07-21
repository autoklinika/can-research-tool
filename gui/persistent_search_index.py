from __future__ import annotations

from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from app.project import CrtProject, SessionRecord
from app.project_search_index import (
    FailedQuerySource,
    ProjectSearchIndex,
    SEARCH_HEADERS,
    SessionSearchFingerprint,
)


class _PersistentBuildSignals(QObject):
    progress = Signal(int, int)
    completed = Signal(object)
    failed = Signal(str)


class _PersistentBuildTask(QRunnable):
    def __init__(
        self,
        project: CrtProject,
        session: SessionRecord,
        repository: ProjectSearchIndex,
    ) -> None:
        super().__init__()
        self.project = project
        self.session = session
        self.repository = repository
        self.cancel_event = Event()
        self.signals = _PersistentBuildSignals()

    def cancel(self) -> None:
        self.cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            fingerprint = self.repository.rebuild_session(
                self.project,
                self.session,
                progress=self.signals.progress.emit,
                cancel_event=self.cancel_event,
            )
        except Exception as exc:
            if not self.cancel_event.is_set():
                self.signals.failed.emit(str(exc))
            return
        if not self.cancel_event.is_set():
            self.signals.completed.emit(fingerprint)


class PersistentSessionSearchIndex(QObject):
    """Qt adapter exposing a durable project index through the in-memory index API."""

    progress_changed = Signal(int, int)
    ready_changed = Signal(bool)
    failed = Signal(str)

    def __init__(
        self,
        project: CrtProject,
        session: SessionRecord,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.session = session
        self.repository = ProjectSearchIndex(project)
        self._fingerprint = self.repository.fingerprint(project, session)
        self._ready = self.repository.is_current(self._fingerprint)
        state = self.repository.state(self._fingerprint.source_id)
        current = self._fingerprint.frame_count if self._ready else 0
        if state is not None and state.total_rows == self._fingerprint.frame_count:
            current = min(state.indexed_rows, state.total_rows)
        self._progress = (current, self._fingerprint.frame_count)
        self._active = False
        self._error = ""
        self._task: _PersistentBuildTask | None = None

    @property
    def model(self):
        return None

    @property
    def source_id(self) -> str:
        return self._fingerprint.source_id

    @property
    def headers(self) -> list[str]:
        return list(SEARCH_HEADERS)

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def progress(self) -> tuple[int, int]:
        return self._progress

    def start(self) -> None:
        self._active = True
        if self._ready or self._task is not None:
            return
        self._error = ""
        task = _PersistentBuildTask(self.project, self.session, self.repository)
        task.signals.progress.connect(self._build_progress)
        task.signals.completed.connect(self._build_completed)
        task.signals.failed.connect(self._build_failed)
        self._task = task
        QThreadPool.globalInstance().start(task)

    def snapshot(self):
        if self._error:
            return FailedQuerySource(self._error)
        return self.repository.source(self._fingerprint.source_id)

    def close(self) -> None:
        self._active = False
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()

    @Slot(int, int)
    def _build_progress(self, current: int, total: int) -> None:
        self._progress = (int(current), int(total))
        self.progress_changed.emit(*self._progress)

    @Slot(object)
    def _build_completed(self, fingerprint: object) -> None:
        self._task = None
        if isinstance(fingerprint, SessionSearchFingerprint):
            self._fingerprint = fingerprint
        ready = self.repository.is_current(self._fingerprint)
        self._ready = ready
        self._progress = (
            self._fingerprint.frame_count if ready else self._progress[0],
            self._fingerprint.frame_count,
        )
        self.progress_changed.emit(*self._progress)
        self.ready_changed.emit(ready)
        if not ready:
            self._build_failed("indeks nie osiągnął spójnego stanu gotowości")

    @Slot(str)
    def _build_failed(self, error: str) -> None:
        self._task = None
        self._error = error or "nieznany błąd budowania indeksu"
        # Mark the source as consumable so a pending search can report the error
        # in its normal worker error path instead of waiting indefinitely.
        self._ready = True
        self.failed.emit(self._error)
        self.ready_changed.emit(True)
