from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, QSettings, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True, slots=True)
class SearchHit:
    row: int
    preview: str


class _SearchSignals(QObject):
    finished = Signal(int, object)
    failed = Signal(int, str)


class _SearchTask(QRunnable):
    def __init__(self, generation: int, query: str, rows: list[tuple[int, str]]) -> None:
        super().__init__()
        self.generation = generation
        self.query = query.casefold()
        self.rows = rows
        self.signals = _SearchSignals()

    def run(self) -> None:
        try:
            hits = [
                SearchHit(row=row, preview=text[:240])
                for row, text in self.rows
                if self.query in text.casefold()
            ]
            self.signals.finished.emit(self.generation, hits)
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            self.signals.failed.emit(self.generation, str(exc))


class LogSearchWindow(QMainWindow):
    """Independent search window that navigates an existing table model.

    The window never changes source-model visibility. It snapshots display text,
    evaluates the query in a worker and stores stable row references for the
    current model generation.
    """

    def __init__(self, parent: QMainWindow) -> None:
        super().__init__(parent, Qt.Window)
        self.setObjectName("logSearchWindow")
        self.setWindowTitle("Wyszukiwanie w logach")
        self.setMinimumSize(720, 460)
        self.resize(900, 620)

        self._generation = 0
        self._target_table: QTableView | None = None
        self._hits: list[SearchHit] = []
        self._tasks: list[_SearchTask] = []

        root_widget = QWidget(self)
        root = QVBoxLayout(root_widget)
        root.setContentsMargins(10, 10, 10, 10)

        query_row = QHBoxLayout()
        self.query_edit = QLineEdit(root_widget)
        self.query_edit.setObjectName("logSearchQuery")
        self.query_edit.setPlaceholderText("CAN ID, HEX, ASCII, SID, DID, PGN, tekst…")
        self.search_button = QPushButton("Szukaj", root_widget)
        self.search_button.setObjectName("logSearchStart")
        query_row.addWidget(self.query_edit, 1)
        query_row.addWidget(self.search_button)
        root.addLayout(query_row)

        self.scope_label = QLabel("Zakres: aktywna tabela", root_widget)
        self.scope_label.setObjectName("logSearchScope")
        root.addWidget(self.scope_label)

        nav_row = QHBoxLayout()
        self.previous_button = QPushButton("Poprzedni (V)", root_widget)
        self.previous_button.setObjectName("logSearchPrevious")
        self.next_button = QPushButton("Następny (N)", root_widget)
        self.next_button.setObjectName("logSearchNext")
        self.result_label = QLabel("0 wyników", root_widget)
        self.result_label.setObjectName("logSearchResultCount")
        nav_row.addWidget(self.previous_button)
        nav_row.addWidget(self.next_button)
        nav_row.addWidget(self.result_label)
        nav_row.addStretch(1)
        root.addLayout(nav_row)

        self.results = QListWidget(root_widget)
        self.results.setObjectName("logSearchResults")
        root.addWidget(self.results, 1)
        self.setCentralWidget(root_widget)

        self.search_button.clicked.connect(self.start_search)
        self.query_edit.returnPressed.connect(self.start_search)
        self.next_button.clicked.connect(self.next_result)
        self.previous_button.clicked.connect(self.previous_result)
        self.results.itemActivated.connect(self._activate_item)
        self.results.currentRowChanged.connect(self._navigate_to_hit)

        geometry = QSettings().value("windows/logSearchGeometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def set_target_table(self, table: QTableView | None) -> None:
        self._target_table = table
        if table is None:
            self.scope_label.setText("Zakres: brak aktywnej tabeli")
            return
        model = table.model()
        if model is None:
            name = table.objectName() or "tabela"
            rows = 0
        else:
            name = table.objectName() or model.__class__.__name__
            rows = model.rowCount()
        self.scope_label.setText(f"Zakres: {name} ({rows:,} wierszy)".replace(",", " "))

    def start_search(self) -> None:
        query = self.query_edit.text().strip()
        table = self._target_table
        model = table.model() if table is not None else None
        if not query:
            self.query_edit.setFocus()
            return
        if table is None or model is None:
            QMessageBox.information(self, "Wyszukiwanie", "Brak aktywnej tabeli do przeszukania.")
            return

        self._generation += 1
        generation = self._generation
        self.results.clear()
        self._hits.clear()
        self.result_label.setText("Wyszukiwanie…")

        rows: list[tuple[int, str]] = []
        for row in range(model.rowCount()):
            columns = [
                str(model.data(model.index(row, column), Qt.DisplayRole) or "")
                for column in range(model.columnCount())
            ]
            rows.append((row, " | ".join(columns)))

        task = _SearchTask(generation, query, rows)
        task.signals.finished.connect(self._search_finished)
        task.signals.failed.connect(self._search_failed)
        self._tasks.append(task)
        QThreadPool.globalInstance().start(task)

    def _search_finished(self, generation: int, hits: object) -> None:
        if generation != self._generation:
            return
        self._hits = list(hits)
        self.results.clear()
        for hit in self._hits:
            item = QListWidgetItem(f"Wiersz {hit.row + 1}: {hit.preview}")
            item.setData(Qt.UserRole, hit.row)
            self.results.addItem(item)
        self.result_label.setText(f"{len(self._hits):,} wyników".replace(",", " "))
        if self._hits:
            self.results.setCurrentRow(0)
        self._tasks = self._tasks[-2:]

    def _search_failed(self, generation: int, error: str) -> None:
        if generation != self._generation:
            return
        self.result_label.setText("Błąd wyszukiwania")
        QMessageBox.critical(self, "Wyszukiwanie", error)

    def next_result(self) -> None:
        if not self._hits:
            return
        current = self.results.currentRow()
        self.results.setCurrentRow((current + 1) % len(self._hits))

    def previous_result(self) -> None:
        if not self._hits:
            return
        current = self.results.currentRow()
        self.results.setCurrentRow((current - 1) % len(self._hits))

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() == Qt.NoModifier and event.key() == Qt.Key_N:
            self.next_result()
            event.accept()
            return
        if event.modifiers() == Qt.NoModifier and event.key() == Qt.Key_V:
            self.previous_result()
            event.accept()
            return
        super().keyPressEvent(event)

    def _activate_item(self, item: QListWidgetItem) -> None:
        self._navigate_to_hit(self.results.row(item))

    def _navigate_to_hit(self, index: int) -> None:
        table = self._target_table
        if table is None or not 0 <= index < len(self._hits):
            return
        model = table.model()
        if model is None:
            return
        row = self._hits[index].row
        if not 0 <= row < model.rowCount():
            return
        target = model.index(row, 0)
        table.setCurrentIndex(target)
        table.selectRow(row)
        table.scrollTo(target, QTableView.PositionAtCenter)
        table.setFocus(Qt.OtherFocusReason)

    def closeEvent(self, event) -> None:  # noqa: N802
        QSettings().setValue("windows/logSearchGeometry", self.saveGeometry())
        super().closeEvent(event)
