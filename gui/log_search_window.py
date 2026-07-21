from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRunnable, QSettings, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
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

from app.search_engine import (
    SearchDocument,
    SearchEngine,
    SearchHit,
    SearchLogic,
    SearchMode,
    SearchQuery,
)


_MODE_LABELS: tuple[tuple[str, SearchMode], ...] = (
    ("Zawiera", SearchMode.CONTAINS),
    ("Równe", SearchMode.EXACT),
    ("Rozpoczyna się od", SearchMode.PREFIX),
    ("Kończy się na", SearchMode.SUFFIX),
    ("Wildcard (*, ?)", SearchMode.WILDCARD),
    ("Regex", SearchMode.REGEX),
)

_LOGIC_LABELS: tuple[tuple[str, SearchLogic], ...] = (
    ("OR", SearchLogic.ANY),
    ("AND", SearchLogic.ALL),
)


class _SearchSignals(QObject):
    finished = Signal(int, object)
    failed = Signal(int, str)


class _SearchTask(QRunnable):
    def __init__(
        self,
        generation: int,
        query: SearchQuery,
        documents: list[SearchDocument],
    ) -> None:
        super().__init__()
        self.generation = generation
        self.query = query
        self.documents = documents
        self.signals = _SearchSignals()

    def run(self) -> None:
        try:
            hits = SearchEngine().search(self.documents, self.query)
            self.signals.finished.emit(self.generation, hits)
        except Exception as exc:  # pragma: no cover
            self.signals.failed.emit(self.generation, str(exc))


class LogSearchWindow(QMainWindow):
    """Independent SearchEngine front-end for the active table."""

    def __init__(self, parent: QMainWindow) -> None:
        super().__init__(parent, Qt.Window)
        self.setObjectName("logSearchWindow")
        self.setWindowTitle("Wyszukiwanie w logach")
        self.setMinimumSize(800, 500)
        self.resize(1000, 660)

        self._generation = 0
        self._target_table: QTableView | None = None
        self._hits: list[SearchHit] = []
        self._tasks: list[_SearchTask] = []
        self._event_filter_installed = False
        self._field_checkboxes: dict[str, QCheckBox] = {}

        root_widget = QWidget(self)
        root = QVBoxLayout(root_widget)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        query_row = QHBoxLayout()
        self.query_edit = QLineEdit(root_widget)
        self.query_edit.setObjectName("logSearchQuery")
        self.query_edit.setPlaceholderText("Szukaj; kilka elementów rozdziel przecinkami")

        self.mode_combo = QComboBox(root_widget)
        self.mode_combo.setObjectName("logSearchMode")
        for label, mode in _MODE_LABELS:
            self.mode_combo.addItem(label, mode.value)
        self.mode_combo.setMinimumWidth(170)

        self.logic_combo = QComboBox(root_widget)
        self.logic_combo.setObjectName("logSearchLogic")
        for label, logic in _LOGIC_LABELS:
            self.logic_combo.addItem(label, logic.value)
        self.logic_combo.setMinimumWidth(75)

        self.search_button = QPushButton("Szukaj", root_widget)
        self.search_button.setObjectName("logSearchStart")
        self.search_button.setDefault(True)

        query_row.addWidget(self.query_edit, 1)
        query_row.addWidget(self.mode_combo)
        query_row.addWidget(self.logic_combo)
        query_row.addWidget(self.search_button)
        root.addLayout(query_row)

        self.fields_group = QGroupBox("Zakres", root_widget)
        self.fields_group.setObjectName("logSearchFieldsGroup")
        fields_root = QVBoxLayout(self.fields_group)

        self.all_fields_check = QCheckBox("Wszystkie kolumny", self.fields_group)
        self.all_fields_check.setObjectName("logSearchAllFields")
        self.all_fields_check.setChecked(True)
        fields_root.addWidget(self.all_fields_check)

        self.fields_widget = QWidget(self.fields_group)
        self.fields_layout = QGridLayout(self.fields_widget)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        self.fields_layout.setHorizontalSpacing(14)
        self.fields_layout.setVerticalSpacing(4)
        fields_root.addWidget(self.fields_widget)
        root.addWidget(self.fields_group)

        nav_row = QHBoxLayout()
        self.previous_button = QPushButton("Poprzedni (V)", root_widget)
        self.previous_button.setObjectName("logSearchPrevious")
        self.next_button = QPushButton("Następny (N)", root_widget)
        self.next_button.setObjectName("logSearchNext")
        self.result_label = QLabel("0 wyników", root_widget)
        self.result_label.setObjectName("logSearchResultCount")
        self.position_label = QLabel("", root_widget)
        self.position_label.setObjectName("logSearchPosition")
        nav_row.addWidget(self.previous_button)
        nav_row.addWidget(self.next_button)
        nav_row.addSpacing(8)
        nav_row.addWidget(self.result_label)
        nav_row.addWidget(self.position_label)
        nav_row.addStretch(1)
        root.addLayout(nav_row)

        self.results = QListWidget(root_widget)
        self.results.setObjectName("logSearchResults")
        self.results.setAlternatingRowColors(True)
        root.addWidget(self.results, 1)
        self.setCentralWidget(root_widget)

        self.search_button.clicked.connect(self.start_search)
        self.query_edit.returnPressed.connect(self.start_search)
        self.next_button.clicked.connect(self.next_result)
        self.previous_button.clicked.connect(self.previous_result)
        self.results.itemActivated.connect(self._activate_item)
        self.results.currentRowChanged.connect(self._result_selection_changed)
        self.all_fields_check.toggled.connect(self._all_fields_toggled)

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._event_filter_installed = True

        settings = QSettings()
        geometry = settings.value("windows/logSearchGeometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

        saved_mode = str(settings.value("windows/logSearchMode", SearchMode.CONTAINS.value))
        mode_index = self.mode_combo.findData(saved_mode)
        if mode_index >= 0:
            self.mode_combo.setCurrentIndex(mode_index)

        saved_logic = str(settings.value("windows/logSearchLogic", SearchLogic.ANY.value))
        logic_index = self.logic_combo.findData(saved_logic)
        if logic_index >= 0:
            self.logic_combo.setCurrentIndex(logic_index)

    def set_target_table(self, table: QTableView | None) -> None:
        self._target_table = table
        self._rebuild_field_choices()

    def start_search(self) -> None:
        query_text = self.query_edit.text().strip()
        table = self._target_table
        model = table.model() if table is not None else None
        if not query_text:
            self.query_edit.setFocus()
            return
        if table is None or model is None:
            QMessageBox.information(self, "Wyszukiwanie", "Brak aktywnej tabeli do przeszukania.")
            return

        selected_fields = self._selected_fields()
        if not self.all_fields_check.isChecked() and not selected_fields:
            QMessageBox.information(
                self,
                "Wyszukiwanie",
                "Wybierz co najmniej jedną kolumnę albo zaznacz wszystkie kolumny.",
            )
            return

        self._generation += 1
        generation = self._generation
        self.results.clear()
        self._hits.clear()
        self.position_label.clear()
        self.result_label.setText("Wyszukiwanie…")
        self.search_button.setEnabled(False)

        headers = self._model_headers(model)
        documents: list[SearchDocument] = []
        for row in range(model.rowCount()):
            fields = {
                headers[column]: str(model.data(model.index(row, column), Qt.DisplayRole) or "")
                for column in range(model.columnCount())
            }
            documents.append(SearchDocument(row=row, fields=fields))

        query = SearchQuery(
            text=query_text,
            mode=SearchMode(str(self.mode_combo.currentData())),
            fields=frozenset(selected_fields),
            logic=SearchLogic(str(self.logic_combo.currentData())),
        )
        task = _SearchTask(generation, query, documents)
        task.signals.finished.connect(self._search_finished)
        task.signals.failed.connect(self._search_failed)
        self._tasks.append(task)
        QThreadPool.globalInstance().start(task)

    def _search_finished(self, generation: int, hits: object) -> None:
        if generation != self._generation:
            return
        self.search_button.setEnabled(True)
        self._hits = list(hits)
        self.results.clear()
        for hit in self._hits:
            fields = ", ".join(hit.matched_fields)
            terms = ", ".join(hit.matched_terms)
            item = QListWidgetItem(f"{hit.row + 1}  [{fields}]  {terms}\n{hit.preview}")
            item.setData(Qt.UserRole, hit.row)
            self.results.addItem(item)
        self.result_label.setText(f"{len(self._hits):,} wyników".replace(",", " "))
        if self._hits:
            self.results.setCurrentRow(0)
            self.results.setFocus(Qt.OtherFocusReason)
        else:
            self.position_label.clear()
        self._tasks = self._tasks[-2:]

    def _search_failed(self, generation: int, error: str) -> None:
        if generation != self._generation:
            return
        self.search_button.setEnabled(True)
        self.result_label.setText("Błąd wyszukiwania")
        self.position_label.clear()
        QMessageBox.critical(self, "Wyszukiwanie", error)

    def next_result(self) -> None:
        if self._hits:
            current = self.results.currentRow()
            self.results.setCurrentRow((current + 1) % len(self._hits))

    def previous_result(self) -> None:
        if self._hits:
            current = self.results.currentRow()
            self.results.setCurrentRow((current - 1) % len(self._hits))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if (
            event.type() == QEvent.Type.KeyPress
            and self.isVisible()
            and QApplication.focusWidget() is not self.query_edit
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
        ):
            if event.key() == Qt.Key.Key_N:
                self.next_result()
                return True
            if event.key() == Qt.Key.Key_V:
                self.previous_result()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.close()
                return True
        return super().eventFilter(watched, event)

    def _activate_item(self, item: QListWidgetItem) -> None:
        self._navigate_to_hit(self.results.row(item))

    def _result_selection_changed(self, index: int) -> None:
        if 0 <= index < len(self._hits):
            self.position_label.setText(f"{index + 1} / {len(self._hits)}")
        else:
            self.position_label.clear()
        self._navigate_to_hit(index)

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

    def _rebuild_field_choices(self) -> None:
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._field_checkboxes.clear()

        table = self._target_table
        model = table.model() if table is not None else None
        if model is None:
            self.fields_widget.setEnabled(False)
            return

        headers = self._model_headers(model)
        for index, header in enumerate(headers):
            checkbox = QCheckBox(header, self.fields_widget)
            checkbox.setObjectName(f"logSearchField{index}")
            checkbox.setChecked(False)
            checkbox.setEnabled(not self.all_fields_check.isChecked())
            self.fields_layout.addWidget(checkbox, index // 4, index % 4)
            self._field_checkboxes[header] = checkbox
        self.fields_widget.setEnabled(True)

    def _all_fields_toggled(self, checked: bool) -> None:
        for checkbox in self._field_checkboxes.values():
            if not checked:
                checkbox.setChecked(False)
            checkbox.setEnabled(not checked)

    def _selected_fields(self) -> set[str]:
        if self.all_fields_check.isChecked():
            return set()
        return {
            name
            for name, checkbox in self._field_checkboxes.items()
            if checkbox.isChecked()
        }

    @staticmethod
    def _model_headers(model) -> list[str]:
        headers: list[str] = []
        used: dict[str, int] = {}
        for column in range(model.columnCount()):
            base = str(model.headerData(column, Qt.Horizontal, Qt.DisplayRole) or f"Kolumna {column + 1}")
            count = used.get(base, 0)
            used[base] = count + 1
            headers.append(base if count == 0 else f"{base} ({count + 1})")
        return headers

    def closeEvent(self, event) -> None:  # noqa: N802
        settings = QSettings()
        settings.setValue("windows/logSearchGeometry", self.saveGeometry())
        settings.setValue("windows/logSearchMode", self.mode_combo.currentData())
        settings.setValue("windows/logSearchLogic", self.logic_combo.currentData())
        super().closeEvent(event)

    def __del__(self) -> None:
        app = QApplication.instance()
        if app is not None and self._event_filter_installed:
            app.removeEventFilter(self)
