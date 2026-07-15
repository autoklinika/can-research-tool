from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.dbc import DbcFileRecord
from app.project import CrtProject
from app.project_dbc import (
    import_project_dbc,
    list_project_dbc,
    remove_project_dbc,
    set_project_dbc_enabled,
)


class DbcTableModel(QAbstractTableModel):
    project_changed = Signal()
    _HEADERS = ("Aktywny", "Nazwa", "Plik projektu", "Wiadomości", "SHA-256")

    def __init__(self, project: CrtProject, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self._records: list[DbcFileRecord] = []
        self.refresh()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._records)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):  # noqa: N802,E501
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self._HEADERS):
            return self._HEADERS[section]
        return section + 1

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._records):
            return None
        record = self._records[index.row()]
        if index.column() == 0 and role == Qt.CheckStateRole:
            return Qt.Checked if record.enabled else Qt.Unchecked
        if role == Qt.DisplayRole:
            values = (
                "",
                record.name,
                record.relative_path,
                str(record.message_count),
                record.sha256[:16],
            )
            return values[index.column()]
        if role == Qt.TextAlignmentRole and index.column() in (0, 3):
            return int(Qt.AlignCenter)
        if role == Qt.ToolTipRole:
            return (
                f"{record.relative_path}\n"
                f"Wiadomości: {record.message_count}\n"
                f"SHA-256: {record.sha256}"
            )
        return None

    def flags(self, index: QModelIndex):
        flags = super().flags(index)
        if index.isValid() and index.column() == 0:
            flags |= Qt.ItemIsUserCheckable
        return flags

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:  # noqa: N802
        if (
            not index.isValid()
            or index.column() != 0
            or role != Qt.CheckStateRole
            or not 0 <= index.row() < len(self._records)
        ):
            return False
        record = self._records[index.row()]
        set_project_dbc_enabled(self.project, record.id, value == Qt.Checked)
        self.refresh()
        self.project_changed.emit()
        return True

    def refresh(self) -> None:
        self.beginResetModel()
        self._records = list_project_dbc(self.project)
        self.endResetModel()

    def record_at(self, row: int) -> DbcFileRecord | None:
        return self._records[row] if 0 <= row < len(self._records) else None

    @property
    def total_count(self) -> int:
        return len(self._records)

    @property
    def active_count(self) -> int:
        return sum(record.enabled for record in self._records)


class DbcManagerWidget(QWidget):
    changed = Signal()
    output_message = Signal(str)
    inspector_text = Signal(str)

    def __init__(self, project: CrtProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.model = DbcTableModel(project, self)
        self.model.project_changed.connect(self._project_changed)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        heading = QLabel("Dekodery DBC projektu")
        font = heading.font()
        font.setPointSize(font.pointSize() + 5)
        font.setBold(True)
        heading.setFont(font)
        root.addWidget(heading)
        root.addWidget(
            QLabel(
                "Pliki są kopiowane do folderu decoders/dbc projektu. "
                "Odznaczenie pola wyłącza interpretację bez usuwania pliku."
            )
        )

        actions = QHBoxLayout()
        self.import_button = QPushButton("Importuj DBC…")
        self.import_button.clicked.connect(self._import_dbc)
        actions.addWidget(self.import_button)
        self.remove_button = QPushButton("Usuń z projektu")
        self.remove_button.clicked.connect(self._remove_selected)
        actions.addWidget(self.remove_button)
        self.refresh_button = QPushButton("Odśwież")
        self.refresh_button.clicked.connect(self._refresh)
        actions.addWidget(self.refresh_button)
        actions.addStretch(1)
        self.summary = QLabel()
        actions.addWidget(self.summary)
        root.addLayout(actions)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 75)
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(2, 380)
        self.table.setColumnWidth(3, 95)
        self.table.selectionModel().selectionChanged.connect(self._selected)
        root.addWidget(self.table, 1)

        note = QLabel(
            "Zmiana aktywności obowiązuje dla następnego logowania i powoduje ponowne "
            "zinterpretowanie otwartych zapisanych sesji. Aktywnej rejestracji nie zmieniamy w locie."
        )
        note.setWordWrap(True)
        root.addWidget(note)
        self._update_summary()

    def _import_dbc(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Importuj pliki DBC do projektu",
            str(Path.home()),
            "CAN database (*.dbc);;Wszystkie pliki (*)",
        )
        changed = False
        for path in paths:
            try:
                record = import_project_dbc(self.project, path)
            except Exception as exc:
                QMessageBox.critical(self, "Nie można zaimportować DBC", f"{path}\n\n{exc}")
                continue
            changed = True
            self.output_message.emit(
                f"Zaimportowano DBC: {record.name} | wiadomości={record.message_count}"
            )
        if changed:
            self.model.refresh()
            self._project_changed()

    def _remove_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "CRT", "Zaznacz plik DBC do usunięcia.")
            return
        record = self.model.record_at(rows[0].row())
        if record is None:
            return
        answer = QMessageBox.question(
            self,
            "Usuń DBC",
            f"Usunąć {record.name} z projektu?\n\nPlik w decoders/dbc również zostanie usunięty.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            remove_project_dbc(self.project, record.id)
        except Exception as exc:
            QMessageBox.critical(self, "Nie można usunąć DBC", str(exc))
            return
        self.model.refresh()
        self.output_message.emit(f"Usunięto DBC: {record.name}")
        self._project_changed()

    def _refresh(self) -> None:
        self.model.refresh()
        self._update_summary()

    def _project_changed(self) -> None:
        self._update_summary()
        self.changed.emit()

    def _update_summary(self) -> None:
        self.summary.setText(
            f"Aktywne: {self.model.active_count} / {self.model.total_count}"
        )

    def _selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        record = self.model.record_at(rows[0].row())
        if record is None:
            return
        self.inspector_text.emit(
            "\n".join(
                (
                    "PLIK DBC",
                    "",
                    f"Nazwa: {record.name}",
                    f"Stan: {'AKTYWNY' if record.enabled else 'WYŁĄCZONY'}",
                    f"Plik: {record.relative_path}",
                    f"Wiadomości: {record.message_count}",
                    f"SHA-256: {record.sha256}",
                    f"Dodano: {record.added_at_utc}",
                )
            )
        )
