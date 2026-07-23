from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.logical_records import load_recent_logical_messages


INTERACTIVE_MESSAGE_ROWS = 1_000


class LogicalMessageLoadSignals(QObject):
    loaded = Signal(str, object, int, str)
    failed = Signal(str, str)


class LogicalMessageLoadTask(QRunnable):
    """Read or reconstruct a bounded logical-message window in a worker thread."""

    def __init__(
        self,
        session_path: str | Path,
        *,
        max_rows: int,
        dbc_paths: tuple[Path, ...] = (),
    ) -> None:
        super().__init__()
        self.session_path = Path(session_path)
        # A QTableView with 14 columns becomes expensive under Fusion when tens
        # of thousands of Python-backed rows are exposed at once. Keep the file
        # and total count intact, but render one bounded interactive page.
        self.max_rows = min(max_rows, INTERACTIVE_MESSAGE_ROWS)
        self.dbc_paths = tuple(Path(path) for path in dbc_paths)
        self.signals = LogicalMessageLoadSignals()

    @Slot()
    def run(self) -> None:
        try:
            messages, total, source = load_recent_logical_messages(
                self.session_path,
                max_rows=self.max_rows,
                dbc_paths=self.dbc_paths,
            )
            self.signals.loaded.emit(
                str(self.session_path),
                messages,
                total,
                source,
            )
        except Exception as exc:
            self.signals.failed.emit(str(self.session_path), str(exc))
