from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.project import CrtProject

from .marker_dialog import MarkerPresetDialog
from .marker_model import MarkerPresetTableModel


class MarkerManagerDialog(QDialog):
    """Edit the marker set before a capture without occupying the live workspace."""

    def __init__(self, project: CrtProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Znaczniki sesji")
        self.setModal(True)
        self.resize(760, 430)

        self.model = MarkerPresetTableModel(project.list_marker_presets(), self)
        root = QVBoxLayout(self)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._edit)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        add_button = QPushButton("Dodaj")
        add_button.clicked.connect(self._add)
        actions.addWidget(add_button)
        edit_button = QPushButton("Edytuj")
        edit_button.clicked.connect(self._edit)
        actions.addWidget(edit_button)
        remove_button = QPushButton("Usuń")
        remove_button.clicked.connect(self._remove)
        actions.addWidget(remove_button)
        actions.addStretch(1)
        root.addLayout(actions)

        save_button = QDialogButtonBox.StandardButton.Save
        cancel_button = QDialogButtonBox.StandardButton.Cancel
        buttons = QDialogButtonBox(save_button | cancel_button)
        buttons.button(save_button).setText("Zapisz")
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _add(self) -> None:
        dialog = MarkerPresetDialog(
            areas=[area.name for area in self.project.list_study_areas()],
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        preset = dialog.preset(self.model.rowCount())
        if self._shortcut_conflicts(preset.shortcut):
            QMessageBox.warning(
                self,
                "CRT",
                "Ten skrót jest już przypisany do innego znacznika.",
            )
            return
        self.model.add_preset(preset)

    def _edit(self, *_args) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "CRT", "Zaznacz znacznik do edycji.")
            return
        row = rows[0].row()
        existing = self.model.preset_at(row)
        if existing is None:
            return
        dialog = MarkerPresetDialog(
            existing=existing,
            areas=[area.name for area in self.project.list_study_areas()],
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.preset(row)
        if self._shortcut_conflicts(updated.shortcut, excluding_id=existing.id):
            QMessageBox.warning(
                self,
                "CRT",
                "Ten skrót jest już przypisany do innego znacznika.",
            )
            return
        self.model.replace_preset(row, updated)

    def _remove(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.model.remove_row(rows[0].row())

    def _save_and_accept(self) -> None:
        presets = self.model.presets()
        active_shortcuts = [
            preset.shortcut.strip().lower()
            for preset in presets
            if preset.enabled
        ]
        if len(active_shortcuts) != len(set(active_shortcuts)):
            QMessageBox.warning(
                self,
                "CRT",
                "Aktywne znaczniki mają zduplikowane skróty.",
            )
            return
        try:
            self.project.save_marker_presets(presets)
        except Exception as exc:
            QMessageBox.critical(self, "Błąd zapisu znaczników", str(exc))
            return
        self.accept()

    def _shortcut_conflicts(self, shortcut: str, *, excluding_id: str = "") -> bool:
        normalized = shortcut.strip().lower()
        return any(
            preset.id != excluding_id
            and preset.shortcut.strip().lower() == normalized
            for preset in self.model.presets()
        )
