from __future__ import annotations

from threading import Event

from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QObject,
    QRunnable,
    QSettings,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.query_engine import QueryEngine
from app.search_engine import SearchHit, SearchLogic, SearchMode, SearchQuery

from .search_index_registry import QtTableSearchIndex


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


class _SearchResultModel(QAbstractListModel):
    """Virtual result list exposing every hit without QListWidgetItem allocation."""

    SourceRowRole = Qt.UserRole + 1
    HitRole = Qt.UserRole + 2

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._hits: list[SearchHit] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802, B008
        return 0 if parent.isValid() else len(self._hits)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._hits):
            return None
        hit = self._hits[index.row()]
        if role == Qt.DisplayRole:
            fields = ", ".join(hit.matched_fields)
            terms = ", ".join(hit.matched_terms)
            return f"{hit.row + 1}  [{fields}]  {terms}\n{hit.preview}"
        if role == self.SourceRowRole:
            return hit.row
        if role == self.HitRole:
            return hit
        return None

    def roleNames(self) -> dict[int, bytes]:  # noqa: N802
        roles = super().roleNames()
        roles[self.SourceRowRole] = b"sourceRow"
        roles[self.HitRole] = b"searchHit"
        return roles

    def set_hits(self, hits: list[SearchHit]) -> None:
        self.beginResetModel()
        self._hits = hits
        self.endResetModel()

    def clear(self) -> None:
        if self._hits:
            self.set_hits([])


class _SearchSignals(QObject):
    finished = Signal(int, object)
    failed = Signal(int, str)


class _SearchTask(QRunnable):
    def __init__(self, generation: int, query: SearchQuery, source: QtTableSearchIndex) -> None:
        super().__init__()
        self.generation = generation
        self.query = query
        self.documents = source.snapshot()
        self.cancel_event = Event()
        self.signals = _SearchSignals()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            result = QueryEngine().search(
                self.documents,
                self.query,
                result_limit=None,
                should_cancel=self.cancel_event.is_set,
            )
            if not self.cancel_event.is_set():
                self.signals.finished.emit(self.generation, result.hits)
        except Exception as exc:  # pragma: no cover
            if not self.cancel_event.is_set():
                self.signals.failed.emit(self.generation, str(exc))


class LogSearchWindow(QMainWindow):
    """Non-modal front-end using the shared prebuilt CRT QueryEngine index."""

    def __init__(self, parent: QMainWindow) -> None:
        super().__init__(parent, Qt.Window)
        self.setObjectName("logSearchWindow")
        self.setWindowTitle("Wyszukiwanie w logach")
        self.setMinimumSize(800, 500)
        self.resize(1000, 660)

        self._generation = 0
        self._target_table: QTableView | None = None
        self._index: QtTableSearchIndex | None = None
        self._owned_index: QtTableSearchIndex | None = None
        self._hits: list[SearchHit] = []
        self._tasks: list[_SearchTask] = []
        self._event_filter_installed = False
        self._field_checkboxes: dict[str, QCheckBox] = {}
        self._pending_search = False

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

        self._result_model = _SearchResultModel(self)
        self.results = QListView(root_widget)
        self.results.setObjectName("logSearchResults")
        self.results.setAlternatingRowColors(True)
        self.results.setUniformItemSizes(True)
        self.results.setWordWrap(False)
        self.results.setModel(self._result_model)
        root.addWidget(self.results, 1)
        self.setCentralWidget(root_widget)

        self.search_button.clicked.connect(self.start_search)
        self.query_edit.returnPressed.connect(self.start_search)
        self.next_button.clicked.connect(self.next_result)
        self.previous_button.clicked.connect(self.previous_result)
        self.results.activated.connect(self._activate_index)
        self.results.selectionModel().currentChanged.connect(self._result_selection_changed)
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
        """Compatibility fallback used by older smoke tests and callers."""
        if self._owned_index is not None:
            self._owned_index.close()
            self._owned_index = None
        if table is None or table.model() is None:
            self.set_target_index(None, None)
            return
        self._owned_index = QtTableSearchIndex(table.model(), self)
        self.set_target_index(table, self._owned_index)

    def set_target_index(
        self,
        table: QTableView | None,
        index: QtTableSearchIndex | None,
    ) -> None:
        self._disconnect_index()
        self._target_table = table
        self._index = index
        self._cancel_tasks()
        self._pending_search = False
        if index is not None:
            index.progress_changed.connect(self._index_progress_changed)
            index.ready_changed.connect(self._index_ready_changed)
            index.start()
        self._rebuild_field_choices()

    def _disconnect_index(self) -> None:
        index = self._index
        if index is None:
            return
        for signal, slot in (
            (index.progress_changed, self._index_progress_changed),
            (index.ready_changed, self._index_ready_changed),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._index = None

    def _index_progress_changed(self, current: int, total: int) -> None:
        if self._pending_search:
            self.result_label.setText(f"Przygotowywanie… {current:,}/{total:,}".replace(",", " "))

    def _index_ready_changed(self, ready: bool) -> None:
        if ready and self._pending_search:
            self._pending_search = False
            self.start_search()

    def start_search(self) -> None:
        query_text = self.query_edit.text().strip()
        table = self._target_table
        index = self._index
        if not query_text:
            self.query_edit.setFocus()
            return
        if table is None or table.model() is None or index is None:
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

        if not index.is_ready:
            self._pending_search = True
            current, total = index.progress
            self.result_label.setText(f"Przygotowywanie… {current:,}/{total:,}".replace(",", " "))
            index.start()
            return

        self._cancel_tasks()
        self._generation += 1
        generation = self._generation
        self._hits = []
        self._result_model.clear()
        self.position_label.clear()
        self.result_label.setText("Wyszukiwanie…")

        query = SearchQuery(
            text=query_text,
            mode=SearchMode(str(self.mode_combo.currentData())),
            fields=frozenset(selected_fields),
            logic=SearchLogic(str(self.logic_combo.currentData())),
        )
        task = _SearchTask(generation, query, index)
        task.signals.finished.connect(self._search_finished)
        task.signals.failed.connect(self._search_failed)
        self._tasks.append(task)
        QThreadPool.globalInstance().start(task)

    def _cancel_tasks(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    def _search_finished(self, generation: int, hits: object) -> None:
        if generation != self._generation:
            return
        self._hits = list(hits)
        self._result_model.set_hits(self._hits)
        self.result_label.setText(f"{len(self._hits):,} wyników".replace(",", " "))
        if self._hits:
            first = self._result_model.index(0, 0)
            self.results.setCurrentIndex(first)
            self.results.scrollTo(first, QListView.PositionAtTop)
            self.results.setFocus(Qt.OtherFocusReason)
        else:
            self.position_label.clear()
        self._tasks.clear()

    def _search_failed(self, generation: int, error: str) -> None:
        if generation != self._generation:
            return
        self.result_label.setText("Błąd wyszukiwania")
        self.position_label.clear()
        self._tasks.clear()
        QMessageBox.critical(self, "Wyszukiwanie", error)

    def next_result(self) -> None:
        if not self._hits:
            return
        current = self.results.currentIndex().row()
        self._select_result(0 if current < 0 else (current + 1) % len(self._hits))

    def previous_result(self) -> None:
        if not self._hits:
            return
        current = self.results.currentIndex().row()
        self._select_result(len(self._hits) - 1 if current < 0 else (current - 1) % len(self._hits))

    def _select_result(self, row: int) -> None:
        index = self._result_model.index(row, 0)
        if index.isValid():
            self.results.setCurrentIndex(index)
            self.results.scrollTo(index, QListView.PositionAtCenter)

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

    def _activate_index(self, index: QModelIndex) -> None:
        self._navigate_to_hit(index.row())

    def _result_selection_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        position = current.row()
        if 0 <= position < len(self._hits):
            self.position_label.setText(f"{position + 1} / {len(self._hits)}")
        else:
            self.position_label.clear()
        self._navigate_to_hit(position)

    def _navigate_to_hit(self, position: int) -> None:
        table = self._target_table
        if table is None or not 0 <= position < len(self._hits):
            return
        model = table.model()
        if model is None:
            return
        row = self._hits[position].row
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

        headers = self._index.headers if self._index is not None else []
        if not headers:
            self.fields_widget.setEnabled(False)
            return
        for position, header in enumerate(headers):
            checkbox = QCheckBox(header, self.fields_widget)
            checkbox.setObjectName(f"logSearchField{position}")
            checkbox.setChecked(False)
            checkbox.setEnabled(not self.all_fields_check.isChecked())
            self.fields_layout.addWidget(checkbox, position // 4, position % 4)
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

    def closeEvent(self, event) -> None:  # noqa: N802
        self._pending_search = False
        self._cancel_tasks()
        settings = QSettings()
        settings.setValue("windows/logSearchGeometry", self.saveGeometry())
        settings.setValue("windows/logSearchMode", self.mode_combo.currentData())
        settings.setValue("windows/logSearchLogic", self.logic_combo.currentData())
        super().closeEvent(event)

    def __del__(self) -> None:
        app = QApplication.instance()
        if app is not None and self._event_filter_installed:
            app.removeEventFilter(self)
