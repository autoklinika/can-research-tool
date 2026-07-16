from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.live_filters import ActiveFilterSet
from app.session_filters import load_filtered_session_page


class FilteredSessionLoadSignals(QObject):
    loaded = Signal(str, object)
    failed = Signal(str, str)


class FilteredSessionLoadTask(QRunnable):
    """Evaluate saved-session filters outside the Qt GUI thread."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_rows: int,
        filter_set: ActiveFilterSet,
    ) -> None:
        super().__init__()
        self.path = Path(path)
        self.max_rows = max_rows
        self.filter_set = filter_set
        self.signals = FilteredSessionLoadSignals()

    @Slot()
    def run(self) -> None:
        try:
            page = load_filtered_session_page(
                self.path,
                self.filter_set,
                max_rows=self.max_rows,
            )
            self.signals.loaded.emit(str(self.path), page)
        except Exception as exc:
            self.signals.failed.emit(str(self.path), str(exc))
