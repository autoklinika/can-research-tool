from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.project import CrtProject


class ImportSignals(QObject):
    completed = Signal(str, str)
    failed = Signal(str, str)


class ProjectImportTask(QRunnable):
    def __init__(self, project: CrtProject, source_path: str | Path) -> None:
        super().__init__()
        self.project = project
        self.source_path = Path(source_path)
        self.signals = ImportSignals()

    @Slot()
    def run(self) -> None:
        try:
            record = self.project.import_log(self.source_path)
            target = self.project.absolute_path(record.relative_path)
            self.signals.completed.emit(str(self.source_path), str(target))
        except Exception as exc:
            self.signals.failed.emit(str(self.source_path), str(exc))
