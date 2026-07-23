from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .logical_message_loader import LogicalMessageLoadTask
from .logical_message_model import LogicalMessageTableModel
from .protocol_summary import attach_protocol_summary
from .table_hover import enable_fast_cell_hover


class LogicalMessageViewerWindow(QMainWindow):
    """Standalone, bounded viewer for a session's logical-message sidecar."""

    MAX_ROWS = 1_000

    def __init__(
        self,
        session_path: str | Path,
        *,
        dbc_paths: tuple[Path, ...] = (),
    ) -> None:
        super().__init__()
        self.session_path = Path(session_path)
        self.dbc_paths = tuple(Path(path) for path in dbc_paths)
        self._tasks: list[LogicalMessageLoadTask] = []

        self.setWindowTitle(f"CRT — Wiadomości logiczne — {self.session_path.name}")
        self.resize(1500, 850)
        self.setMinimumSize(900, 550)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)

        self.status = QLabel(
            f"Ładowanie ostatnich {self.MAX_ROWS} wiadomości z {self.session_path.name}…"
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.model = LogicalMessageTableModel(capacity=self.MAX_ROWS, parent=self)
        self.table = QTableView(central)
        self.table.setModel(self.model)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.horizontalHeader().setStretchLastSection(True)
        enable_fast_cell_hover(self.table)
        layout.addWidget(self.table, 1)
        attach_protocol_summary(self.table, self.model)

        self.setCentralWidget(central)
        self._start_load()

    def _start_load(self) -> None:
        task = LogicalMessageLoadTask(
            self.session_path,
            max_rows=self.MAX_ROWS,
            dbc_paths=self.dbc_paths,
        )
        task.signals.loaded.connect(self._loaded)
        task.signals.failed.connect(self._failed)
        self._tasks.append(task)
        QThreadPool.globalInstance().start(task)

    def _loaded(
        self,
        path: str,
        messages: object,
        total_messages: int,
        source: str,
    ) -> None:
        loaded = list(messages)
        self.model.replace_messages(loaded)
        source_text = "messages.csv" if source.startswith("messages-csv") else source
        if source.endswith("+dbc"):
            source_text += " + DBC"
        self.status.setText(
            (
                f"Sesja: {path} | pokazano {len(loaded):,} ostatnich z "
                f"{total_messages:,} wiadomości | źródło: {source_text}"
            ).replace(",", " ")
        )
        self._tasks.clear()

    def _failed(self, path: str, error: str) -> None:
        self.status.setText(f"Nie udało się odczytać wiadomości z {path}:\n{error}")
        self._tasks.clear()
