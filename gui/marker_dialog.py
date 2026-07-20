from __future__ import annotations

from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QKeySequenceEdit,
)

from app.markers import MarkerPreset


class MarkerPresetDialog(QDialog):
    def __init__(
        self,
        *,
        existing: MarkerPreset | None = None,
        areas: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._existing = existing
        self._color = existing.color if existing else "#3B82F6"
        self.setWindowTitle("Znacznik sesji")
        self.setModal(True)
        self.resize(430, 230)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(existing.name if existing else "")
        self.name_edit.setPlaceholderText("np. EGR odłączony")
        form.addRow("Nazwa:", self.name_edit)

        self.shortcut_edit = QKeySequenceEdit()
        if existing:
            self.shortcut_edit.setKeySequence(QKeySequence(existing.shortcut))
        form.addRow("Skrót:", self.shortcut_edit)

        self.area_combo = QComboBox()
        self.area_combo.setEditable(True)
        self.area_combo.addItem("")
        for area in areas or []:
            self.area_combo.addItem(area)
        if existing and existing.area:
            index = self.area_combo.findText(existing.area)
            if index < 0:
                self.area_combo.addItem(existing.area)
                index = self.area_combo.count() - 1
            self.area_combo.setCurrentIndex(index)
        form.addRow("Obszar:", self.area_combo)

        color_row = QHBoxLayout()
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(34, 22)
        self._update_color_preview()
        color_button = QPushButton("Wybierz kolor")
        color_button.clicked.connect(self._choose_color)
        color_row.addWidget(self.color_preview)
        color_row.addWidget(color_button)
        color_row.addStretch(1)
        color_container = QWidget()
        color_container.setLayout(color_row)
        form.addRow("Kolor:", color_container)

        self.enabled_check = QCheckBox("Aktywny w następnym logowaniu")
        self.enabled_check.setChecked(existing.enabled if existing else True)
        form.addRow("", self.enabled_check)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def preset(self, sort_order: int = 0) -> MarkerPreset:
        shortcut = self.shortcut_edit.keySequence().toString(QKeySequence.PortableText)
        if self._existing is None:
            return MarkerPreset.create(
                self.name_edit.text(),
                shortcut,
                color=self._color,
                area=self.area_combo.currentText(),
                enabled=self.enabled_check.isChecked(),
                sort_order=sort_order,
            )
        return MarkerPreset(
            id=self._existing.id,
            name=self.name_edit.text().strip(),
            shortcut=shortcut,
            color=self._color,
            area=self.area_combo.currentText().strip(),
            enabled=self.enabled_check.isChecked(),
            sort_order=sort_order,
        )

    def _choose_color(self) -> None:
        selected = QColorDialog.getColor(QColor(self._color), self, "Kolor znacznika")
        if selected.isValid():
            self._color = selected.name(QColor.HexRgb)
            self._update_color_preview()

    def _update_color_preview(self) -> None:
        self.color_preview.setStyleSheet(
            f"background: {self._color}; border: 1px solid palette(mid); border-radius: 3px;"
        )
        self.color_preview.setToolTip(self._color)

    def _validate_and_accept(self) -> None:
        name = self.name_edit.text().strip()
        shortcut = self.shortcut_edit.keySequence().toString(QKeySequence.PortableText)
        if not name:
            QMessageBox.warning(self, "CRT", "Podaj nazwę znacznika.")
            self.name_edit.setFocus()
            return
        if not shortcut:
            QMessageBox.warning(self, "CRT", "Przypisz skrót klawiszowy.")
            self.shortcut_edit.setFocus()
            return
        self.accept()
