from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.session_stream import SessionPagedReader


class SessionLoadSignals(QObject):
    loaded = Signal(str, object, int, int)
    failed = Signal(str, str)


class SessionLoadTask(QRunnable):
    """Build/load a sparse index and fetch only the newest visible page."""

    def __init__(self, path: str | Path, *, max_rows: int) -> None:
        super().__init__()
        self.path = Path(path)
        self.max_rows = max_rows
        self.signals = SessionLoadSignals()

    @Slot()
    def run(self) -> None:
        try:
            reader = SessionPagedReader(self.path)
            start = max(0, reader.frame_count - self.max_rows)
            frames = reader.read_page(start, self.max_rows)
            self.signals.loaded.emit(
                str(self.path),
                frames,
                reader.frame_count,
                start,
            )
        except Exception as exc:
            self.signals.failed.emit(str(self.path), str(exc))
