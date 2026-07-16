from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.filters import (
    CanFrameRecord,
    FilterCompiler,
    FilterMode,
    FilterPreset,
    MatchState,
    ProjectFilterRepository,
)
from app.project import CrtProject


DEFAULT_TREE = {
    "type": "group",
    "operator": "and",
    "children": [
        {
            "type": "condition",
            "field": "can_id",
            "operator": "eq",
            "values": ["0x18FEAE30"],
        }
    ],
}


class FilterManagerWidget(QWidget):
    output_message = Signal(str)
    changed = Signal()

    def __init__(self, project: CrtProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.repository = ProjectFilterRepository(project.database_path)
        self.compiler = FilterCompiler()
        self.presets = self.repository.list_presets()
        self._loading = False
        self._build_ui()
        self._reload_table()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        title_row = QHBoxLayout()
        title = QLabel("Globalne filtry")
        font = title.font()
        font.setPointSize(font.pointSize() + 6)
        font.setBold(True)
        title.setFont(font)
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.status_label = QLabel("Zapis: wszystkie ramki | Widok: brak aktywnego filtra")
        title_row.addWidget(self.status_label)
        root.addLayout(title_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        controls = QHBoxLayout()
        add_button = QPushButton("Dodaj")
        add_button.clicked.connect(self._add_preset)
        controls.addWidget(add_button)
        remove_button = QPushButton("Usuń")
        remove_button.clicked.connect(self._remove_preset)
        controls.addWidget(remove_button)
        save_button = QPushButton("Zapisz")
        save_button.clicked.connect(self._save)
        controls.addWidget(save_button)
        controls.addStretch(1)
        left_layout.addLayout(controls)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Aktywny", "Nazwa", "Skrót", "Tryb"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemChanged.connect(self._table_item_changed)
        left_layout.addWidget(self.table, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)

        preset_box = QGroupBox("Preset")
        preset_form = QFormLayout(preset_box)
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._editor_changed)
        preset_form.addRow("Nazwa", self.name_edit)
        self.description_edit = QLineEdit()
        self.description_edit.editingFinished.connect(self._editor_changed)
        preset_form.addRow("Opis", self.description_edit)
        self.shortcut_edit = QLineEdit()
        self.shortcut_edit.setPlaceholderText("np. Ctrl+1 lub F8")
        self.shortcut_edit.editingFinished.connect(self._editor_changed)
        preset_form.addRow("Skrót", self.shortcut_edit)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([mode.value for mode in FilterMode])
        self.mode_combo.currentTextChanged.connect(self._editor_changed)
        preset_form.addRow("Tryb", self.mode_combo)
        self.enabled_check = QCheckBox("Aktywny")
        self.enabled_check.toggled.connect(self._editor_changed)
        preset_form.addRow("", self.enabled_check)
        right_layout.addWidget(preset_box)

        tree_box = QGroupBox("Drzewo warunków — wersjonowany JSON")
        tree_layout = QVBoxLayout(tree_box)
        self.tree_edit = QPlainTextEdit()
        self.tree_edit.setPlaceholderText("Drzewo AND / OR / NOT")
        tree_layout.addWidget(self.tree_edit, 1)
        validate_button = QPushButton("Waliduj")
        validate_button.clicked.connect(self._validate_current)
        tree_layout.addWidget(validate_button)
        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        tree_layout.addWidget(self.validation_label)
        right_layout.addWidget(tree_box, 1)

        test_box = QGroupBox("Test na ramce")
        test_form = QFormLayout(test_box)
        self.test_can_id = QLineEdit("18FEAE30")
        test_form.addRow("CAN ID [HEX]", self.test_can_id)
        self.test_format = QComboBox()
        self.test_format.addItems(["EXT", "STD"])
        test_form.addRow("Format", self.test_format)
        self.test_dlc = QSpinBox()
        self.test_dlc.setRange(0, 64)
        self.test_dlc.setValue(8)
        test_form.addRow("DLC", self.test_dlc)
        self.test_time = QLineEdit("0")
        test_form.addRow("Czas względny [µs]", self.test_time)
        test_button = QPushButton("Sprawdź")
        test_button.clicked.connect(self._test_current)
        test_form.addRow("", test_button)
        self.test_result = QLabel()
        test_form.addRow("Wynik", self.test_result)
        right_layout.addWidget(test_box)

        splitter.addWidget(right)
        splitter.setSizes([420, 780])

    def _reload_table(self, select_row: int | None = None) -> None:
        self._loading = True
        self.table.setRowCount(len(self.presets))
        for row, preset in enumerate(self.presets):
            active = QTableWidgetItem()
            active.setFlags(active.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            active.setCheckState(Qt.CheckState.Checked if preset.enabled else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, active)
            self.table.setItem(row, 1, QTableWidgetItem(preset.name))
            self.table.setItem(row, 2, QTableWidgetItem(preset.shortcut))
            self.table.setItem(row, 3, QTableWidgetItem(preset.mode.value))
        self._loading = False
        if self.presets:
            row = 0 if select_row is None else max(0, min(select_row, len(self.presets) - 1))
            self.table.selectRow(row)
        else:
            self._clear_editor()
        self._update_status()

    def _current_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _selection_changed(self) -> None:
        row = self._current_row()
        if row < 0 or row >= len(self.presets):
            self._clear_editor()
            return
        preset = self.presets[row]
        self._loading = True
        self.name_edit.setText(preset.name)
        self.description_edit.setText(preset.description)
        self.shortcut_edit.setText(preset.shortcut)
        self.mode_combo.setCurrentText(preset.mode.value)
        self.enabled_check.setChecked(preset.enabled)
        self.tree_edit.setPlainText(json.dumps(preset.root, ensure_ascii=False, indent=2))
        self.validation_label.clear()
        self.test_result.clear()
        self._loading = False

    def _clear_editor(self) -> None:
        self._loading = True
        self.name_edit.clear()
        self.description_edit.clear()
        self.shortcut_edit.clear()
        self.tree_edit.clear()
        self.validation_label.clear()
        self.test_result.clear()
        self._loading = False

    def _add_preset(self) -> None:
        preset = FilterPreset.create()
        preset.root = json.loads(json.dumps(DEFAULT_TREE))
        self.presets.append(preset)
        self._reload_table(len(self.presets) - 1)

    def _remove_preset(self) -> None:
        row = self._current_row()
        if row < 0:
            return
        del self.presets[row]
        self._reload_table(row)

    def _table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        row = item.row()
        if not 0 <= row < len(self.presets):
            return
        preset = self.presets[row]
        if item.column() == 0:
            preset.enabled = item.checkState() == Qt.CheckState.Checked
        elif item.column() == 1:
            preset.name = item.text().strip()
        elif item.column() == 2:
            preset.shortcut = item.text().strip()
        elif item.column() == 3:
            try:
                preset.mode = FilterMode(item.text().strip())
            except ValueError:
                item.setText(preset.mode.value)
        self._selection_changed()
        self._update_status()

    def _editor_changed(self, *_args: object) -> None:
        if self._loading:
            return
        row = self._current_row()
        if row < 0:
            return
        preset = self.presets[row]
        preset.name = self.name_edit.text().strip()
        preset.description = self.description_edit.text().strip()
        preset.shortcut = self.shortcut_edit.text().strip()
        preset.mode = FilterMode(self.mode_combo.currentText())
        preset.enabled = self.enabled_check.isChecked()
        self._reload_table(row)

    def _apply_tree_text(self, preset: FilterPreset) -> None:
        payload = json.loads(self.tree_edit.toPlainText())
        if not isinstance(payload, dict):
            raise ValueError("Korzeń filtra musi być obiektem JSON.")
        preset.root = payload

    def _validate_current(self) -> bool:
        row = self._current_row()
        if row < 0:
            return False
        preset = self.presets[row]
        try:
            self._apply_tree_text(preset)
        except (json.JSONDecodeError, ValueError) as exc:
            self.validation_label.setText(f"Błąd JSON: {exc}")
            return False
        issues = self.compiler.validate(preset)
        if issues:
            self.validation_label.setText("\n".join(f"{item.path}: {item.message}" for item in issues))
            return False
        self.validation_label.setText("Filtr poprawny.")
        return True

    def _save(self) -> None:
        row = self._current_row()
        if row >= 0 and not self._validate_current():
            return
        all_issues = [
            (preset.name, self.compiler.validate(preset))
            for preset in self.presets
        ]
        invalid = [(name, issues) for name, issues in all_issues if issues]
        if invalid:
            name, issues = invalid[0]
            QMessageBox.warning(self, "Filtry", f"Preset {name} jest niepoprawny:\n{issues[0].message}")
            return
        try:
            self.repository.save_presets(self.presets)
        except Exception as exc:
            QMessageBox.critical(self, "Nie można zapisać filtrów", str(exc))
            return
        self.output_message.emit(f"Zapisano presety filtrów: {len(self.presets)}")
        self.changed.emit()
        self._update_status()

    def _test_current(self) -> None:
        row = self._current_row()
        if row < 0 or not self._validate_current():
            return
        try:
            frame = CanFrameRecord(
                can_id=int(self.test_can_id.text().strip().removeprefix("0x"), 16),
                extended=self.test_format.currentText() == "EXT",
                dlc=self.test_dlc.value(),
                relative_time_us=int(self.test_time.text().strip()),
            )
        except ValueError as exc:
            self.test_result.setText(f"Błąd danych ramki: {exc}")
            return
        result = self.compiler.evaluate(self.presets[row], frame)
        labels = {
            MatchState.MATCH: "MATCH",
            MatchState.NO_MATCH: "NO MATCH",
            MatchState.UNAVAILABLE: "UNAVAILABLE",
        }
        self.test_result.setText(labels[result.state] + (f" — {result.reason}" if result.reason else ""))

    def _update_status(self) -> None:
        active = [preset.name for preset in self.presets if preset.enabled]
        if active:
            self.status_label.setText(f"Zapis: wszystkie ramki | Widok: aktywne filtry ({len(active)})")
        else:
            self.status_label.setText("Zapis: wszystkie ramki | Widok: brak aktywnego filtra")
