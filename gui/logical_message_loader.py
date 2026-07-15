from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.logical_records import load_recent_logical_messages


class LogicalMessageLoadSignals(QObject):
    loaded = Signal(str, object, int, str)
    failed = Signal(str, str)


class LogicalMessageLoadTask(QRunnable):
    """Read or reconstruct a bounded logical-message window in a worker thread."""

    def __init__(self, session_path: str | Path, *, max_rows: int) -> None:
        super().__init__()
        self.session_path = Path(session_path)
        self.max_rows = max_rows
        self.signals = LogicalMessageLoadSignals()

    @Slot()
    def run(self) -> None:
        try:
            messages, total, source = load_recent_logical_messages(
                self.session_path,
                max_rows=self.max_rows,
            )
            self.signals.loaded.emit(
                str(self.session_path),
                messages,
                total,
                source,
            )
        except Exception as exc:
            self.signals.failed.emit(str(self.session_path), str(exc))
