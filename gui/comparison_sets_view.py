from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.comparison_sets import ComparisonSetStore
from app.domain import ComparisonSet
from app.project import CrtProject, SessionRecord


_COMPARISON_ID_ROLE = Qt.ItemDataRole.UserRole
_SESSION_ID_ROLE = Qt.ItemDataRole.UserRole
_SYNC_LABELS = {
    "none": "Bez synchronizacji",
    "manual": "Ręczna",
    "marker": "Znacznik",
}


class ComparisonSetDialog(QDialog):
    def __init__(
        self,
        sessions: Sequence[SessionRecord],
        comparison_set: ComparisonSet | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._comparison_set = comparison_set
        self._sessions = _ordered_sessions(sessions, comparison_set)
        self.setWindowTitle(
            "Nowy zestaw porównawczy"
            if comparison_set is None
            else "Edytuj zestaw porównawczy"
        )
        self.resize(720, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        form = QFormLayout()
        self.name_edit = QLineEdit(self)
        self.name_edit.setObjectName("comparisonSetName")
        self.name_edit.setPlaceholderText("Np. ECU przed i po naprawie")
        form.addRow("Nazwa:", self.name_edit)

        self.base_combo = QComboBox(self)
        self.base_combo.setObjectName("comparisonBaseSession")
        form.addRow("Sesja bazowa:", self.base_combo)

        self.sync_combo = QComboBox(self)
        self.sync_combo.setObjectName("comparisonSynchronizationMode")
        self.sync_combo.addItem(_SYNC_LABELS["none"], "none")
        if (
            comparison_set is not None
            and comparison_set.synchronization_mode not in {"", "none"}
        ):
            mode = comparison_set.synchronization_mode
            self.sync_combo.addItem(
                f"Zapisany tryb: {_SYNC_LABELS.get(mode, mode)}",
                mode,
            )
        form.addRow("Synchronizacja:", self.sync_combo)
        root.addLayout(form)

        root.addWidget(QLabel("Sesje należące do zestawu (minimum dwie):"))
        self.sessions_tree = QTreeWidget(self)
        self.sessions_tree.setObjectName("comparisonSessionTree")
        self.sessions_tree.setColumnCount(4)
        self.sessions_tree.setHeaderLabels(["Użyj", "Sesja", "Utworzona", "Ramki"])
        self.sessions_tree.setRootIsDecorated(False)
        self.sessions_tree.setAlternatingRowColors(True)
        self.sessions_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.sessions_tree.header().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.sessions_tree.header().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        self.sessions_tree.header().setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.sessions_tree.header().setSectionResizeMode(
            3,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        root.addWidget(self.sessions_tree, 1)

        self.selection_status = QLabel(self)
        self.selection_status.setObjectName("comparisonSelectionStatus")
        root.addWidget(self.selection_status)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.accepted.connect(self._accept_if_valid)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self._populate()
        self.sessions_tree.itemChanged.connect(self._session_selection_changed)
        self._session_selection_changed()

    def comparison_name(self) -> str:
        return self.name_edit.text().strip()

    def session_ids(self) -> tuple[str, ...]:
        selected: list[str] = []
        for index in range(self.sessions_tree.topLevelItemCount()):
            item = self.sessions_tree.topLevelItem(index)
            if item.checkState(0) == Qt.CheckState.Checked:
                selected.append(str(item.data(0, _SESSION_ID_ROLE)))
        return tuple(selected)

    def base_session_id(self) -> str | None:
        value = self.base_combo.currentData()
        return None if value in (None, "") else str(value)

    def synchronization_mode(self) -> str:
        return str(self.sync_combo.currentData() or "none")

    def _populate(self) -> None:
        selected_ids = (
            set(self._comparison_set.session_ids)
            if self._comparison_set is not None
            else set()
        )
        self.sessions_tree.blockSignals(True)
        try:
            for session in self._sessions:
                item = QTreeWidgetItem(
                    [
                        "",
                        session.name,
                        _display_datetime(session.created_at_utc),
                        f"{session.frame_count:,}".replace(",", " "),
                    ]
                )
                item.setData(0, _SESSION_ID_ROLE, session.id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    0,
                    Qt.CheckState.Checked
                    if session.id in selected_ids
                    else Qt.CheckState.Unchecked,
                )
                item.setToolTip(1, session.relative_path)
                self.sessions_tree.addTopLevelItem(item)
        finally:
            self.sessions_tree.blockSignals(False)

        if self._comparison_set is not None:
            self.name_edit.setText(self._comparison_set.name)
            sync_index = self.sync_combo.findData(
                self._comparison_set.synchronization_mode
            )
            if sync_index >= 0:
                self.sync_combo.setCurrentIndex(sync_index)

    def _session_selection_changed(self, *_args) -> None:
        previous_base = self.base_session_id()
        selected_ids = self.session_ids()
        session_by_id = {session.id: session for session in self._sessions}

        self.base_combo.blockSignals(True)
        try:
            self.base_combo.clear()
            self.base_combo.addItem("Brak sesji bazowej", None)
            for session_id in selected_ids:
                session = session_by_id.get(session_id)
                if session is not None:
                    self.base_combo.addItem(session.name, session.id)
            preferred = previous_base
            if preferred is None and self._comparison_set is not None:
                preferred = self._comparison_set.base_session_id
            index = self.base_combo.findData(preferred)
            self.base_combo.setCurrentIndex(max(0, index))
        finally:
            self.base_combo.blockSignals(False)

        count = len(selected_ids)
        self.selection_status.setText(
            f"Wybrane sesje: {count}"
            if count >= 2
            else f"Wybrane sesje: {count} — wybierz co najmniej dwie"
        )

    def _accept_if_valid(self) -> None:
        if not self.comparison_name():
            QMessageBox.warning(self, "Zestaw porównawczy", "Podaj nazwę zestawu.")
            self.name_edit.setFocus()
            return
        if len(self.session_ids()) < 2:
            QMessageBox.warning(
                self,
                "Zestaw porównawczy",
                "Zestaw porównawczy musi zawierać co najmniej dwie sesje.",
            )
            return
        self.accept()


class ComparisonSetsView(QWidget):
    changed = Signal()
    output_message = Signal(str)

    def __init__(self, project: CrtProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.store = ComparisonSetStore(project)
        self._sets: list[ComparisonSet] = []
        self._sessions: list[SessionRecord] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        heading = QLabel("Zestawy porównawcze", self)
        heading.setObjectName("comparisonSetsTitle")
        font = heading.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 3)
        heading.setFont(font)
        root.addWidget(heading)
        root.addWidget(
            QLabel(
                "Trwałe zestawy wskazują wiele istniejących sesji bez kopiowania "
                "ani modyfikowania ich danych źródłowych.",
                self,
            )
        )

        toolbar = QHBoxLayout()
        self.new_button = QPushButton("Nowy zestaw…", self)
        self.new_button.setObjectName("newComparisonSetButton")
        self.new_button.clicked.connect(self._create_set)
        toolbar.addWidget(self.new_button)

        self.edit_button = QPushButton("Edytuj…", self)
        self.edit_button.setObjectName("editComparisonSetButton")
        self.edit_button.clicked.connect(self._edit_set)
        toolbar.addWidget(self.edit_button)

        self.delete_button = QPushButton("Usuń zestaw", self)
        self.delete_button.setObjectName("deleteComparisonSetButton")
        self.delete_button.clicked.connect(self._delete_set)
        toolbar.addWidget(self.delete_button)

        self.refresh_button = QPushButton("Odśwież", self)
        self.refresh_button.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_button)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        self.table = QTableWidget(0, 6, self)
        self.table.setObjectName("comparisonSetsTable")
        self.table.setHorizontalHeaderLabels(
            [
                "Nazwa",
                "Sesja bazowa",
                "Sesje",
                "Synchronizacja",
                "Stan",
                "Aktualizacja",
            ]
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        for column in range(1, 6):
            self.table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(lambda *_args: self._edit_set())
        root.addWidget(self.table, 1)

        self.details_label = QLabel(self)
        self.details_label.setObjectName("comparisonSetDetails")
        self.details_label.setWordWrap(True)
        root.addWidget(self.details_label)

        self.refresh()

    def refresh(self, selected_id: str | None = None) -> None:
        current_id = selected_id or self.selected_comparison_set_id()
        self._sessions = self.project.list_sessions()
        self._sets = self.store.list()
        session_by_id = {session.id: session for session in self._sessions}

        self.table.setRowCount(0)
        for comparison_set in self._sets:
            row = self.table.rowCount()
            self.table.insertRow(row)
            run_count = self.store.analysis_run_count(comparison_set.id)
            base_session = session_by_id.get(comparison_set.base_session_id or "")
            values = (
                comparison_set.name,
                "—" if base_session is None else base_session.name,
                str(len(comparison_set.session_ids)),
                _SYNC_LABELS.get(
                    comparison_set.synchronization_mode,
                    comparison_set.synchronization_mode,
                ),
                "Z analizami" if run_count else "Edytowalny",
                _display_datetime(comparison_set.updated_at_utc),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(_COMPARISON_ID_ROLE, comparison_set.id)
                    item.setToolTip(comparison_set.id)
                if column == 4 and run_count:
                    item.setToolTip(
                        "Edycja utworzy nową wersję zestawu, a usunięcie zachowa "
                        f"{run_count} uruchomienie/uruchomienia analiz."
                    )
                self.table.setItem(row, column, item)

        if current_id:
            self.select_comparison_set(current_id)
        if self.table.currentRow() < 0 and self.table.rowCount() > 0:
            self.table.selectRow(0)
        self._selection_changed()

        enough_sessions = len(self._sessions) >= 2
        self.new_button.setEnabled(enough_sessions)
        if not enough_sessions:
            self.details_label.setText(
                "Do utworzenia zestawu potrzebne są co najmniej dwie zapisane sesje."
            )
        elif not self._sets:
            self.details_label.setText(
                "Brak zestawów. Utwórz pierwszy zestaw z co najmniej dwóch sesji."
            )

    def select_comparison_set(self, comparison_set_id: str) -> bool:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if (
                item is not None
                and item.data(_COMPARISON_ID_ROLE) == comparison_set_id
            ):
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                return True
        return False

    def selected_comparison_set_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        value = item.data(_COMPARISON_ID_ROLE)
        return None if not value else str(value)

    def selected_comparison_set(self) -> ComparisonSet | None:
        comparison_set_id = self.selected_comparison_set_id()
        if comparison_set_id is None:
            return None
        return next(
            (item for item in self._sets if item.id == comparison_set_id),
            None,
        )

    def _selection_changed(self) -> None:
        comparison_set = self.selected_comparison_set()
        if comparison_set is None:
            self.edit_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            if self._sets:
                self.details_label.clear()
            return

        run_count = self.store.analysis_run_count(comparison_set.id)
        self.edit_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        session_by_id = {session.id: session for session in self._sessions}
        session_names = [
            session_by_id[session_id].name
            for session_id in comparison_set.session_ids
            if session_id in session_by_id
        ]
        history_text = (
            f" Zestaw ma {run_count} zapisane uruchomienie/uruchomienia analiz. "
            "Edycja utworzy nową wersję, a usunięcie zachowa wyniki historyczne."
            if run_count
            else ""
        )
        self.details_label.setText(
            "Sesje: " + ", ".join(session_names) + "." + history_text
        )

    def _create_set(self) -> None:
        if len(self._sessions) < 2:
            QMessageBox.information(
                self,
                "Zestawy porównawcze",
                "Do utworzenia zestawu potrzebne są co najmniej dwie sesje.",
            )
            return
        dialog = ComparisonSetDialog(self._sessions, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            comparison_set = self.store.create(
                name=dialog.comparison_name(),
                session_ids=dialog.session_ids(),
                base_session_id=dialog.base_session_id(),
                synchronization_mode=dialog.synchronization_mode(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Nie można utworzyć zestawu", str(exc))
            return
        self.refresh(comparison_set.id)
        self.changed.emit()
        self.output_message.emit(
            f"Utworzono zestaw porównawczy: {comparison_set.name}"
        )

    def _edit_set(self) -> None:
        comparison_set = self.selected_comparison_set()
        if comparison_set is None:
            return
        has_history = self.store.is_locked(comparison_set.id)
        dialog = ComparisonSetDialog(
            self._sessions,
            comparison_set=comparison_set,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            if has_history:
                updated = self.store.fork(
                    comparison_set.id,
                    name=dialog.comparison_name(),
                    session_ids=dialog.session_ids(),
                    base_session_id=dialog.base_session_id(),
                    synchronization_mode=dialog.synchronization_mode(),
                )
            else:
                updated = self.store.update(
                    comparison_set.id,
                    name=dialog.comparison_name(),
                    session_ids=dialog.session_ids(),
                    base_session_id=dialog.base_session_id(),
                    synchronization_mode=dialog.synchronization_mode(),
                )
        except Exception as exc:
            QMessageBox.critical(self, "Nie można zapisać zestawu", str(exc))
            return
        self.refresh(updated.id)
        self.changed.emit()
        if has_history:
            self.output_message.emit(
                "Utworzono nową wersję zestawu porównawczego: "
                f"{updated.name}. Poprzednią wersję zachowano z analizami."
            )
        else:
            self.output_message.emit(
                f"Zaktualizowano zestaw porównawczy: {updated.name}"
            )

    def _delete_set(self) -> None:
        comparison_set = self.selected_comparison_set()
        if comparison_set is None:
            return
        has_history = self.store.is_locked(comparison_set.id)
        consequence = (
            "Wyniki analiz i ich artefakty pozostaną w projekcie jako historia."
            if has_history
            else "Zapisane sesje i ich surowe ramki nie zostaną usunięte."
        )
        answer = QMessageBox.question(
            self,
            "Usuń zestaw porównawczy",
            f"Usunąć zestaw „{comparison_set.name}”?\n\n{consequence}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            history_preserved = self.store.delete(comparison_set.id)
        except Exception as exc:
            QMessageBox.critical(self, "Nie można usunąć zestawu", str(exc))
            return
        self.refresh()
        self.changed.emit()
        message = f"Usunięto zestaw porównawczy: {comparison_set.name}"
        if history_preserved:
            message += ". Wyniki analiz zachowano w historii projektu."
        self.output_message.emit(message)


def _ordered_sessions(
    sessions: Sequence[SessionRecord],
    comparison_set: ComparisonSet | None,
) -> tuple[SessionRecord, ...]:
    if comparison_set is None:
        return tuple(sessions)
    by_id = {session.id: session for session in sessions}
    ordered = [
        by_id[session_id]
        for session_id in comparison_set.session_ids
        if session_id in by_id
    ]
    used = {session.id for session in ordered}
    ordered.extend(session for session in sessions if session.id not in used)
    return tuple(ordered)


def _display_datetime(value: str) -> str:
    if not value:
        return "—"
    return value.replace("T", " ").replace("+00:00", " UTC")[:23]


__all__ = ["ComparisonSetDialog", "ComparisonSetsView"]
