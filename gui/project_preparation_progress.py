from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget


@dataclass(slots=True)
class _PreparationTask:
    key: str
    label: str
    current: int
    total: int
    stage_index: int | None
    stage_count: int | None
    detail: str
    priority: int
    sequence: int


@dataclass(frozen=True, slots=True)
class PreparationProgressSnapshot:
    key: str
    label: str
    current: int
    total: int
    stage_index: int | None
    stage_count: int | None
    detail: str
    active_count: int
    state: str

    @property
    def display_label(self) -> str:
        prefix = ""
        if self.stage_index is not None and self.stage_count is not None:
            prefix = f"{self.stage_index}/{self.stage_count}  "
        suffix = f"  (+{self.active_count - 1})" if self.active_count > 1 else ""
        return f"{prefix}{self.label}{suffix}"


class ProjectPreparationProgress(QObject):
    """Aggregates project preparation tasks for the main-window status bar.

    Producers such as search indexing, protocol analysis and logical-message
    generation report their own task keys. The tracker presents the highest
    priority active task while retaining the remaining tasks in its queue.
    """

    changed = Signal(object)
    cleared = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tasks: OrderedDict[str, _PreparationTask] = OrderedDict()
        self._sequence = 0

    def begin_task(
        self,
        key: str,
        label: str,
        *,
        current: int = 0,
        total: int = 0,
        stage_index: int | None = None,
        stage_count: int | None = None,
        detail: str = "",
        priority: int = 100,
    ) -> None:
        task = self._tasks.get(key)
        if task is None:
            self._sequence += 1
            task = _PreparationTask(
                key=key,
                label=label,
                current=0,
                total=0,
                stage_index=stage_index,
                stage_count=stage_count,
                detail=detail,
                priority=priority,
                sequence=self._sequence,
            )
            self._tasks[key] = task

        task.label = label
        task.stage_index = stage_index
        task.stage_count = stage_count
        task.detail = detail
        task.priority = priority
        task.total = max(0, int(total))
        task.current = self._bounded_current(current, task.total)
        self._publish_running()

    def update_task(
        self,
        key: str,
        *,
        current: int,
        total: int | None = None,
        label: str | None = None,
        detail: str | None = None,
    ) -> None:
        task = self._tasks.get(key)
        if task is None:
            self.begin_task(
                key,
                label or key,
                current=current,
                total=0 if total is None else total,
                detail=detail or "",
            )
            return

        if label is not None:
            task.label = label
        if detail is not None:
            task.detail = detail
        if total is not None:
            task.total = max(0, int(total))
        task.current = self._bounded_current(current, task.total)
        self._publish_running()

    def complete_task(self, key: str, *, detail: str = "") -> None:
        task = self._tasks.pop(key, None)
        if task is None:
            return
        if self._tasks:
            self._publish_running()
            return

        total = task.total if task.total > 0 else 1
        self.changed.emit(
            PreparationProgressSnapshot(
                key=task.key,
                label=task.label,
                current=total,
                total=total,
                stage_index=task.stage_index,
                stage_count=task.stage_count,
                detail=detail or task.detail,
                active_count=0,
                state="completed",
            )
        )

    def fail_task(self, key: str, message: str) -> None:
        task = self._tasks.pop(key, None)
        if task is None:
            return
        self.changed.emit(
            PreparationProgressSnapshot(
                key=task.key,
                label=task.label,
                current=task.current,
                total=task.total,
                stage_index=task.stage_index,
                stage_count=task.stage_count,
                detail=message,
                active_count=len(self._tasks),
                state="failed",
            )
        )
        if self._tasks:
            QTimer.singleShot(0, self._publish_running)

    def clear(self) -> None:
        self._tasks.clear()
        self.cleared.emit()

    def _publish_running(self) -> None:
        if not self._tasks:
            self.cleared.emit()
            return
        task = min(
            self._tasks.values(),
            key=lambda item: (item.priority, item.sequence),
        )
        self.changed.emit(
            PreparationProgressSnapshot(
                key=task.key,
                label=task.label,
                current=task.current,
                total=task.total,
                stage_index=task.stage_index,
                stage_count=task.stage_count,
                detail=task.detail,
                active_count=len(self._tasks),
                state="running",
            )
        )

    @staticmethod
    def _bounded_current(current: int, total: int) -> int:
        value = max(0, int(current))
        return min(value, total) if total > 0 else value


class ProjectPreparationStatusWidget(QWidget):
    """Compact status-bar view for project preparation progress."""

    def __init__(
        self,
        progress: ProjectPreparationProgress,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("projectPreparationStatus")
        self.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(8)

        self.label = QLabel("", self)
        self.label.setObjectName("projectPreparationLabel")
        self.label.setMinimumWidth(220)
        layout.addWidget(self.label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setObjectName("projectPreparationProgress")
        self.progress_bar.setMinimumWidth(150)
        self.progress_bar.setMaximumWidth(220)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(2_000)
        self._hide_timer.timeout.connect(self.hide)

        progress.changed.connect(self._apply_snapshot)
        progress.cleared.connect(self._clear)

    def _apply_snapshot(self, snapshot: PreparationProgressSnapshot) -> None:
        self._hide_timer.stop()
        self.setVisible(True)
        self.setProperty("state", snapshot.state)

        if snapshot.state == "running":
            self.label.setText(snapshot.display_label)
            self.label.setToolTip(snapshot.detail)
            if snapshot.total > 0:
                self.progress_bar.setRange(0, snapshot.total)
                self.progress_bar.setValue(snapshot.current)
                self.progress_bar.setFormat("%p%")
            else:
                self.progress_bar.setRange(0, 0)
                self.progress_bar.setFormat("")
        elif snapshot.state == "completed":
            self.label.setText(f"Projekt gotowy — {snapshot.label}")
            self.label.setToolTip(snapshot.detail)
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)
            self.progress_bar.setFormat("100%")
            self._hide_timer.start()
        else:
            self.label.setText(f"Błąd przygotowania — {snapshot.label}")
            self.label.setToolTip(snapshot.detail)
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Błąd")

        style = self.style()
        style.unpolish(self)
        style.polish(self)

    def _clear(self) -> None:
        self._hide_timer.stop()
        self.label.clear()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.hide()
