from __future__ import annotations

import json
from copy import deepcopy

from PySide6.QtCore import QTimer, Qt, Signal
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
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.filter_tree import (
    append_child,
    clone_tree,
    default_condition,
    default_group,
    duplicate_node,
    move_node,
    node_at,
    remove_node,
    summarize_node,
)
from app.filters import (
    CanFrameRecord,
    FilterCompiler,
    FilterField,
    FilterMode,
    FilterOperator,
    FilterPreset,
    LogicalOperator,
    MatchState,
    ProjectFilterRepository,
)
from app.logical_records import LogicalMessageRecord
from app.project import CrtProject

from .filter_field_catalog import (
    FIELD_DEFAULTS,
    FIELD_HINTS,
    FILTER_FIELD_CHOICES,
)


DEFAULT_TREE = {
    "type": "group",
    "operator": "and",
    "children": [default_condition()],
}

OPERATOR_LABELS = {
    FilterOperator.EQ.value: "równa się",
    FilterOperator.NE.value: "różni się",
    FilterOperator.GT.value: "większe niż",
    FilterOperator.GE.value: "większe lub równe",
    FilterOperator.LT.value: "mniejsze niż",
    FilterOperator.LE.value: "mniejsze lub równe",
    FilterOperator.BETWEEN.value: "pomiędzy",
    FilterOperator.OUTSIDE.value: "poza zakresem",
    FilterOperator.IN.value: "w zbiorze",
    FilterOperator.NOT_IN.value: "nie w zbiorze",
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
        self._selected_path: tuple[int, ...] = ()
        self._dirty = False

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(600)
        self.autosave_timer.timeout.connect(self._autosave)

        self._build_ui()
        self._reload_table()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel("Globalne filtry")
        font = title.font()
        font.setPointSize(font.pointSize() + 6)
        font.setBold(True)
        title.setFont(font)
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.save_state_label = QLabel("Zapisano")
        title_row.addWidget(self.save_state_label)
        self.status_label = QLabel("Zapis: wszystkie ramki | Widok: brak aktywnego filtra")
        title_row.addWidget(self.status_label)
        root.addLayout(title_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        splitter.addWidget(self._build_presets_panel())
        splitter.addWidget(self._build_tree_panel())
        splitter.addWidget(self._build_properties_panel())
        splitter.setSizes([320, 560, 390])

    def _build_presets_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        heading = QLabel("Presety projektu")
        heading.setStyleSheet("font-weight: 600;")
        layout.addWidget(heading)

        controls = QHBoxLayout()
        add_button = QPushButton("+ Nowy")
        add_button.clicked.connect(self._add_preset)
        controls.addWidget(add_button)
        duplicate_button = QPushButton("Duplikuj")
        duplicate_button.clicked.connect(self._duplicate_preset)
        controls.addWidget(duplicate_button)
        remove_button = QPushButton("Usuń")
        remove_button.clicked.connect(self._remove_preset)
        controls.addWidget(remove_button)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["✓", "Nazwa", "Skrót"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemChanged.connect(self._table_item_changed)
        layout.addWidget(self.table, 1)

        preset_box = QGroupBox("Ustawienia presetu")
        form = QFormLayout(preset_box)
        self.name_edit = QLineEdit()
        self.name_edit.textEdited.connect(self._preset_editor_changed)
        form.addRow("Nazwa", self.name_edit)
        self.description_edit = QLineEdit()
        self.description_edit.textEdited.connect(self._preset_editor_changed)
        form.addRow("Opis", self.description_edit)
        self.shortcut_edit = QLineEdit()
        self.shortcut_edit.setPlaceholderText("np. Ctrl+1 lub F8")
        self.shortcut_edit.textEdited.connect(self._preset_editor_changed)
        form.addRow("Skrót", self.shortcut_edit)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Include — pokaż pasujące", FilterMode.INCLUDE.value)
        self.mode_combo.addItem("Exclude — ukryj pasujące", FilterMode.EXCLUDE.value)
        self.mode_combo.addItem("Highlight — wyróżnij", FilterMode.HIGHLIGHT.value)
        self.mode_combo.currentIndexChanged.connect(self._preset_editor_changed)
        form.addRow("Tryb", self.mode_combo)
        self.enabled_check = QCheckBox("Aktywny")
        self.enabled_check.toggled.connect(self._preset_editor_changed)
        form.addRow("", self.enabled_check)
        layout.addWidget(preset_box)

        save_button = QPushButton("Zapisz teraz")
        save_button.clicked.connect(self._save)
        layout.addWidget(save_button)
        return panel

    def _build_tree_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        heading_row = QHBoxLayout()
        heading = QLabel("Drzewo filtra")
        heading.setStyleSheet("font-weight: 600;")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        self.validation_label = QLabel()
        heading_row.addWidget(self.validation_label)
        layout.addLayout(heading_row)

        add_row = QHBoxLayout()
        add_condition = QPushButton("+ Warunek")
        add_condition.clicked.connect(self._add_condition)
        add_row.addWidget(add_condition)
        for label, operator in (("+ AND", "and"), ("+ OR", "or"), ("+ NOT", "not")):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, op=operator: self._add_group(op))
            add_row.addWidget(button)
        add_row.addStretch(1)
        layout.addLayout(add_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Warunek / grupa", "Stan"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.itemSelectionChanged.connect(self._tree_selection_changed)
        layout.addWidget(self.tree, 1)

        edit_row = QHBoxLayout()
        duplicate_button = QPushButton("Duplikuj element")
        duplicate_button.clicked.connect(self._duplicate_node)
        edit_row.addWidget(duplicate_button)
        remove_button = QPushButton("Usuń element")
        remove_button.clicked.connect(self._remove_node)
        edit_row.addWidget(remove_button)
        up_button = QPushButton("↑")
        up_button.clicked.connect(lambda: self._move_node(-1))
        edit_row.addWidget(up_button)
        down_button = QPushButton("↓")
        down_button.clicked.connect(lambda: self._move_node(1))
        edit_row.addWidget(down_button)
        edit_row.addStretch(1)
        validate_button = QPushButton("Waliduj")
        validate_button.clicked.connect(self._validate_current)
        edit_row.addWidget(validate_button)
        layout.addLayout(edit_row)

        self.json_box = QGroupBox("JSON diagnostyczny")
        self.json_box.setCheckable(True)
        self.json_box.setChecked(False)
        json_layout = QVBoxLayout(self.json_box)
        self.json_preview = QPlainTextEdit()
        self.json_preview.setReadOnly(True)
        self.json_preview.setMaximumHeight(180)
        json_layout.addWidget(self.json_preview)
        layout.addWidget(self.json_box)
        self.json_box.toggled.connect(self.json_preview.setVisible)
        self.json_preview.setVisible(False)
        return panel

    def _build_properties_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel("Właściwości elementu")
        heading.setStyleSheet("font-weight: 600;")
        layout.addWidget(heading)

        self.properties_stack = QStackedWidget()
        layout.addWidget(self.properties_stack)

        empty = QLabel("Zaznacz grupę lub warunek w drzewie.")
        empty.setWordWrap(True)
        self.properties_stack.addWidget(empty)

        group_widget = QWidget()
        group_form = QFormLayout(group_widget)
        self.group_operator = QComboBox()
        self.group_operator.addItem("AND — wszystkie warunki", LogicalOperator.AND.value)
        self.group_operator.addItem("OR — dowolny warunek", LogicalOperator.OR.value)
        self.group_operator.addItem("NOT — negacja jednego elementu", LogicalOperator.NOT.value)
        self.group_operator.currentIndexChanged.connect(self._group_property_changed)
        group_form.addRow("Operator", self.group_operator)
        self.group_hint = QLabel()
        self.group_hint.setWordWrap(True)
        group_form.addRow("", self.group_hint)
        self.properties_stack.addWidget(group_widget)

        condition_widget = QWidget()
        condition_form = QFormLayout(condition_widget)
        self.condition_field = QComboBox()
        for choice in FILTER_FIELD_CHOICES:
            self.condition_field.addItem(choice.label, choice.field)
        self.condition_field.currentIndexChanged.connect(self._condition_field_changed)
        condition_form.addRow("Pole", self.condition_field)
        self.condition_operator = QComboBox()
        for operator in FilterOperator:
            self.condition_operator.addItem(OPERATOR_LABELS[operator.value], operator.value)
        self.condition_operator.currentIndexChanged.connect(self._condition_property_changed)
        condition_form.addRow("Operator", self.condition_operator)
        self.condition_values = QLineEdit()
        self.condition_values.setPlaceholderText("np. 0x18FEAE30 lub 10, 20")
        self.condition_values.textEdited.connect(self._condition_property_changed)
        condition_form.addRow("Wartość / wartości", self.condition_values)
        self.value_hint = QLabel()
        self.value_hint.setWordWrap(True)
        condition_form.addRow("", self.value_hint)
        self.properties_stack.addWidget(condition_widget)

        layout.addStretch(1)
        layout.addWidget(self._build_test_box())
        return panel

    def _build_test_box(self) -> QGroupBox:
        box = QGroupBox("Test presetu")
        form = QFormLayout(box)
        self.test_context = QComboBox()
        self.test_context.addItem("Surowa ramka CAN", "raw")
        self.test_context.addItem("Wiadomość logiczna", "logical")
        self.test_context.currentIndexChanged.connect(self._test_context_changed)
        form.addRow("Kontekst", self.test_context)

        self.test_can_id = QLineEdit("18FEAE30")
        form.addRow("CAN ID [HEX]", self.test_can_id)
        self.test_format = QComboBox()
        self.test_format.addItems(["EXT", "STD"])
        form.addRow("Format", self.test_format)
        self.test_dlc = QSpinBox()
        self.test_dlc.setRange(0, 64)
        self.test_dlc.setValue(8)
        form.addRow("DLC", self.test_dlc)
        self.test_time = QLineEdit("0")
        form.addRow("Czas [µs]", self.test_time)

        self.test_logical_json = QPlainTextEdit()
        self.test_logical_json.setMaximumHeight(210)
        self.test_logical_json.setPlainText(
            json.dumps(
                {
                    "sequence": 1,
                    "first_timestamp_ns": 0,
                    "last_timestamp_ns": 1000000,
                    "protocol": "uds",
                    "transport": "isotp",
                    "name": "UDS ReadDataByIdentifier",
                    "arbitration_id": "0x7E8",
                    "is_extended_id": False,
                    "pgn": None,
                    "source_address": None,
                    "destination_address": None,
                    "complete": True,
                    "frame_sequences": [1],
                    "payload_hex": "62 F1 90",
                    "error": "",
                    "confidence": 1.0,
                    "fields": {
                        "service_id": "0x62",
                        "base_service_id": "0x22",
                        "direction": "positive-response",
                        "response_type": "positive-response",
                        "service_name": "ReadDataByIdentifier",
                        "did": "0xF190",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        form.addRow("Rekord JSON", self.test_logical_json)

        button = QPushButton("Sprawdź cały preset")
        button.clicked.connect(self._test_current)
        form.addRow("", button)
        self.test_result = QLabel()
        self.test_result.setWordWrap(True)
        form.addRow("Wynik", self.test_result)
        self._test_context_changed()
        return box

    def _current_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _current_preset(self) -> FilterPreset | None:
        row = self._current_row()
        return self.presets[row] if 0 <= row < len(self.presets) else None

    def _reload_table(self, select_row: int | None = None) -> None:
        self._loading = True
        self.table.setRowCount(len(self.presets))
        for row, preset in enumerate(self.presets):
            active = QTableWidgetItem()
            active.setFlags(active.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            active.setCheckState(
                Qt.CheckState.Checked if preset.enabled else Qt.CheckState.Unchecked
            )
            self.table.setItem(row, 0, active)
            self.table.setItem(row, 1, QTableWidgetItem(preset.name))
            self.table.setItem(row, 2, QTableWidgetItem(preset.shortcut))
        self._loading = False
        if self.presets:
            row = 0 if select_row is None else max(0, min(select_row, len(self.presets) - 1))
            self.table.selectRow(row)
        else:
            self._clear_editor()
        self._update_status()

    def _selection_changed(self) -> None:
        preset = self._current_preset()
        if preset is None:
            self._clear_editor()
            return
        self._loading = True
        self.name_edit.setText(preset.name)
        self.description_edit.setText(preset.description)
        self.shortcut_edit.setText(preset.shortcut)
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(preset.mode.value)))
        self.enabled_check.setChecked(preset.enabled)
        self._loading = False
        self._selected_path = ()
        self._reload_tree(())
        self.test_result.clear()

    def _clear_editor(self) -> None:
        self._loading = True
        self.name_edit.clear()
        self.description_edit.clear()
        self.shortcut_edit.clear()
        self.enabled_check.setChecked(False)
        self.tree.clear()
        self.json_preview.clear()
        self.validation_label.clear()
        self.properties_stack.setCurrentIndex(0)
        self._loading = False

    def _reload_tree(self, select_path: tuple[int, ...] | None = None) -> None:
        preset = self._current_preset()
        if preset is None:
            self.tree.clear()
            return
        self._loading = True
        self.tree.clear()
        issue_paths = {issue.path for issue in self.compiler.validate(preset)}

        def add_item(node: dict, path: tuple[int, ...], parent: QTreeWidgetItem | None) -> None:
            item = QTreeWidgetItem([summarize_node(node), ""])
            item.setData(0, Qt.ItemDataRole.UserRole, list(path))
            if self._path_has_issue(path, issue_paths):
                item.setText(1, "⚠")
                item.setToolTip(1, "Element zawiera błąd walidacji")
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            children = node.get("children")
            if node.get("type") == "group" and isinstance(children, list):
                for index, child in enumerate(children):
                    if isinstance(child, dict):
                        add_item(child, path + (index,), item)
            item.setExpanded(True)

        add_item(preset.root, (), None)
        self.json_preview.setPlainText(json.dumps(preset.root, ensure_ascii=False, indent=2))
        self._loading = False
        self._select_tree_path(select_path if select_path is not None else self._selected_path)
        self._show_validation_summary()

    @staticmethod
    def _path_has_issue(path: tuple[int, ...], issue_paths: set[str]) -> bool:
        encoded = "root" + "".join(f".children[{index}]" for index in path)
        return any(issue == encoded or issue.startswith(encoded + ".") for issue in issue_paths)

    def _select_tree_path(self, path: tuple[int, ...]) -> None:
        iterator = self.tree.invisibleRootItem()
        target = iterator.child(0) if iterator.childCount() else None
        for index in path:
            if target is None or index >= target.childCount():
                target = None
                break
            target = target.child(index)
        if target is not None:
            self.tree.setCurrentItem(target)

    def _tree_selection_changed(self) -> None:
        if self._loading:
            return
        items = self.tree.selectedItems()
        if not items:
            self.properties_stack.setCurrentIndex(0)
            return
        raw = items[0].data(0, Qt.ItemDataRole.UserRole) or []
        self._selected_path = tuple(int(value) for value in raw)
        self._load_node_properties()

    def _load_node_properties(self) -> None:
        preset = self._current_preset()
        if preset is None:
            return
        try:
            node = node_at(preset.root, self._selected_path)
        except (ValueError, IndexError):
            self.properties_stack.setCurrentIndex(0)
            return
        self._loading = True
        if node.get("type") == "group":
            self.properties_stack.setCurrentIndex(1)
            operator = str(node.get("operator", "and"))
            self.group_operator.setCurrentIndex(max(0, self.group_operator.findData(operator)))
            self.group_hint.setText(
                "NOT może zawierać dokładnie jeden element. AND i OR mogą zawierać dowolną liczbę warunków i grup."
            )
        else:
            self.properties_stack.setCurrentIndex(2)
            field = str(node.get("field", FilterField.CAN_ID.value))
            operator = str(node.get("operator", FilterOperator.EQ.value))
            self.condition_field.setCurrentIndex(max(0, self.condition_field.findData(field)))
            self.condition_operator.setCurrentIndex(
                max(0, self.condition_operator.findData(operator))
            )
            values = node.get("values", [])
            self.condition_values.setText(", ".join(str(value) for value in values))
            self._update_value_hint(field)
        self._loading = False

    def _target_group_path(self) -> tuple[int, ...] | None:
        preset = self._current_preset()
        if preset is None:
            return None
        path = self._selected_path
        try:
            node = node_at(preset.root, path)
        except (ValueError, IndexError):
            return ()
        if node.get("type") == "group":
            return path
        return path[:-1]

    def _add_condition(self) -> None:
        preset = self._current_preset()
        parent_path = self._target_group_path()
        if preset is None or parent_path is None:
            return
        try:
            path = append_child(preset.root, parent_path, default_condition())
        except ValueError as exc:
            QMessageBox.warning(self, "Filtry", str(exc))
            return
        self._tree_mutated(path)

    def _add_group(self, operator: str) -> None:
        preset = self._current_preset()
        parent_path = self._target_group_path()
        if preset is None or parent_path is None:
            return
        try:
            path = append_child(preset.root, parent_path, default_group(operator))
        except ValueError as exc:
            QMessageBox.warning(self, "Filtry", str(exc))
            return
        self._tree_mutated(path)

    def _remove_node(self) -> None:
        preset = self._current_preset()
        if preset is None:
            return
        if not self._selected_path:
            QMessageBox.information(self, "Filtry", "Nie można usunąć korzenia filtra.")
            return
        parent_path = self._selected_path[:-1]
        try:
            remove_node(preset.root, self._selected_path)
        except (ValueError, IndexError) as exc:
            QMessageBox.warning(self, "Filtry", str(exc))
            return
        self._tree_mutated(parent_path)

    def _duplicate_node(self) -> None:
        preset = self._current_preset()
        if preset is None or not self._selected_path:
            return
        try:
            path = duplicate_node(preset.root, self._selected_path)
        except (ValueError, IndexError) as exc:
            QMessageBox.warning(self, "Filtry", str(exc))
            return
        self._tree_mutated(path)

    def _move_node(self, offset: int) -> None:
        preset = self._current_preset()
        if preset is None or not self._selected_path:
            return
        try:
            path = move_node(preset.root, self._selected_path, offset)
        except (ValueError, IndexError) as exc:
            QMessageBox.warning(self, "Filtry", str(exc))
            return
        self._tree_mutated(path)

    def _group_property_changed(self) -> None:
        if self._loading:
            return
        preset = self._current_preset()
        if preset is None:
            return
        node = node_at(preset.root, self._selected_path)
        operator = str(self.group_operator.currentData())
        children = node.get("children")
        if (
            operator == LogicalOperator.NOT.value
            and isinstance(children, list)
            and len(children) > 1
        ):
            QMessageBox.warning(
                self,
                "Filtry",
                "Grupa NOT może zawierać tylko jeden element. Usuń nadmiarowe elementy przed zmianą operatora.",
            )
            self._load_node_properties()
            return
        node["operator"] = operator
        self._tree_mutated(self._selected_path)

    def _condition_field_changed(self) -> None:
        if self._loading:
            return
        preset = self._current_preset()
        if preset is None:
            return
        node = node_at(preset.root, self._selected_path)
        field = str(self.condition_field.currentData())
        node["field"] = field
        node["operator"] = FilterOperator.EQ.value
        node["values"] = [FIELD_DEFAULTS.get(field, "")]
        self._tree_mutated(self._selected_path)

    def _condition_property_changed(self) -> None:
        if self._loading:
            return
        preset = self._current_preset()
        if preset is None:
            return
        node = node_at(preset.root, self._selected_path)
        node["operator"] = str(self.condition_operator.currentData())
        values = [part.strip() for part in self.condition_values.text().split(",") if part.strip()]
        node["values"] = values
        self._tree_mutated(self._selected_path, restart_editor=False)

    def _update_value_hint(self, field: str) -> None:
        self.value_hint.setText(FIELD_HINTS.get(field, ""))

    def _tree_mutated(self, select_path: tuple[int, ...], *, restart_editor: bool = True) -> None:
        self._selected_path = select_path
        self._mark_dirty()
        self._reload_tree(select_path)
        if restart_editor:
            self._load_node_properties()

    def _add_preset(self) -> None:
        preset = FilterPreset.create()
        preset.root = clone_tree(DEFAULT_TREE)
        self.presets.append(preset)
        self._mark_dirty()
        self._reload_table(len(self.presets) - 1)

    def _duplicate_preset(self) -> None:
        preset = self._current_preset()
        if preset is None:
            return
        duplicate = FilterPreset.create(f"{preset.name} — kopia")
        duplicate.description = preset.description
        duplicate.enabled = False
        duplicate.mode = preset.mode
        duplicate.scope = list(preset.scope)
        duplicate.root = deepcopy(preset.root)
        self.presets.append(duplicate)
        self._mark_dirty()
        self._reload_table(len(self.presets) - 1)

    def _remove_preset(self) -> None:
        row = self._current_row()
        if row < 0:
            return
        del self.presets[row]
        self._mark_dirty()
        self._reload_table(row)

    def _table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        activation_changed = item.column() == 0
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
        self._mark_dirty()
        self._selection_changed()
        self._update_status()
        if activation_changed:
            self._save(silent=True)

    def _preset_editor_changed(self, *_args: object) -> None:
        if self._loading:
            return
        preset = self._current_preset()
        if preset is None:
            return
        previous_enabled = preset.enabled
        preset.name = self.name_edit.text().strip()
        preset.description = self.description_edit.text().strip()
        preset.shortcut = self.shortcut_edit.text().strip()
        preset.mode = FilterMode(str(self.mode_combo.currentData()))
        preset.enabled = self.enabled_check.isChecked()
        row = self._current_row()
        self._loading = True
        self.table.item(row, 0).setCheckState(
            Qt.CheckState.Checked if preset.enabled else Qt.CheckState.Unchecked
        )
        self.table.item(row, 1).setText(preset.name)
        self.table.item(row, 2).setText(preset.shortcut)
        self._loading = False
        self._mark_dirty()
        self._update_status()
        if preset.enabled != previous_enabled:
            self._save(silent=True)

    def _mark_dirty(self) -> None:
        self._dirty = True
        self.save_state_label.setText("Niezapisane zmiany…")
        self.autosave_timer.start()

    def _autosave(self) -> None:
        if self._dirty:
            self._save(silent=True)

    def _validate_current(self) -> bool:
        preset = self._current_preset()
        if preset is None:
            return False
        issues = self.compiler.validate(preset)
        self._reload_tree(self._selected_path)
        if issues:
            self.validation_label.setText(f"⚠ {len(issues)} błędów")
            QMessageBox.warning(
                self,
                "Walidacja filtra",
                "\n".join(f"{issue.path}: {issue.message}" for issue in issues[:10]),
            )
            return False
        self.validation_label.setText("✓ Filtr poprawny")
        return True

    def _show_validation_summary(self) -> None:
        preset = self._current_preset()
        if preset is None:
            self.validation_label.clear()
            return
        issues = self.compiler.validate(preset)
        self.validation_label.setText("✓ poprawny" if not issues else f"⚠ {len(issues)} błędów")

    def _save(self, _checked: bool = False, *, silent: bool = False) -> bool:
        invalid = [
            (preset, self.compiler.validate(preset)) for preset in self.presets if preset.enabled
        ]
        invalid = [(preset, issues) for preset, issues in invalid if issues]
        if invalid:
            preset, issues = invalid[0]
            self.save_state_label.setText("Błąd aktywnego filtra — nie zapisano")
            if not silent:
                QMessageBox.warning(
                    self,
                    "Filtry",
                    f"Aktywny preset „{preset.name}” jest niepoprawny:\n"
                    f"{issues[0].path}: {issues[0].message}",
                )
            return False
        try:
            self.repository.save_presets(self.presets)
        except Exception as exc:
            self.save_state_label.setText("Błąd zapisu")
            if not silent:
                QMessageBox.critical(self, "Nie można zapisać filtrów", str(exc))
            return False
        self._dirty = False
        self.autosave_timer.stop()
        self.save_state_label.setText("Zapisano automatycznie" if silent else "Zapisano")
        self.output_message.emit(f"Zapisano presety filtrów: {len(self.presets)}")
        self.changed.emit()
        self._update_status()
        return True

    def _test_context_changed(self, *_args: object) -> None:
        logical = (
            getattr(self, "test_context", None) is not None
            and self.test_context.currentData() == "logical"
        )
        for widget in (
            getattr(self, "test_can_id", None),
            getattr(self, "test_format", None),
            getattr(self, "test_dlc", None),
            getattr(self, "test_time", None),
        ):
            if widget is not None:
                widget.setVisible(not logical)
        if getattr(self, "test_logical_json", None) is not None:
            self.test_logical_json.setVisible(logical)

    def _test_current(self) -> None:
        preset = self._current_preset()
        if preset is None:
            return
        issues = self.compiler.validate(preset)
        if issues:
            self.test_result.setText(f"UNAVAILABLE — {issues[0].message}")
            return
        try:
            if self.test_context.currentData() == "logical":
                payload = json.loads(self.test_logical_json.toPlainText())
                record = _logical_record_from_test_payload(payload)
                result = self.compiler.evaluate_logical_message(
                    preset,
                    record,
                    relative_time_us=int(payload.get("relative_time_us", 0)),
                )
            else:
                text = self.test_can_id.text().strip().lower()
                frame = CanFrameRecord(
                    can_id=int(text, 16),
                    extended=self.test_format.currentText() == "EXT",
                    dlc=self.test_dlc.value(),
                    relative_time_us=int(self.test_time.text().strip()),
                )
                result = self.compiler.evaluate(preset, frame)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self.test_result.setText(f"Błąd danych testowych: {exc}")
            return
        labels = {
            MatchState.MATCH: "MATCH",
            MatchState.NO_MATCH: "NO MATCH",
            MatchState.UNAVAILABLE: "UNAVAILABLE",
        }
        self.test_result.setText(
            labels[result.state] + (f" — {result.reason}" if result.reason else "")
        )

    def _update_status(self) -> None:
        active = [preset.name for preset in self.presets if preset.enabled]
        if active:
            names = ", ".join(active[:2]) + ("…" if len(active) > 2 else "")
            self.status_label.setText(
                f"Zapis: wszystkie ramki | Widok: aktywne filtry ({len(active)}) — {names}"
            )
        else:
            self.status_label.setText("Zapis: wszystkie ramki | Widok: brak aktywnego filtra")


def _logical_record_from_test_payload(payload: dict[str, object]) -> LogicalMessageRecord:
    fields = payload.get("fields")
    if fields is not None and not isinstance(fields, dict):
        raise ValueError("fields musi być obiektem JSON")
    frame_sequences = payload.get("frame_sequences", [1])
    if not isinstance(frame_sequences, list):
        raise ValueError("frame_sequences musi być listą")
    return LogicalMessageRecord(
        sequence=int(payload.get("sequence", 0)),
        first_timestamp_ns=int(payload.get("first_timestamp_ns", 0)),
        last_timestamp_ns=int(payload.get("last_timestamp_ns", 0)),
        protocol=str(payload.get("protocol", "unknown")),
        transport=str(payload.get("transport", "raw")),
        name=str(payload.get("name", "")),
        arbitration_id=_optional_int(payload.get("arbitration_id")),
        is_extended_id=bool(payload.get("is_extended_id", False)),
        pgn=_optional_int(payload.get("pgn")),
        source_address=_optional_int(payload.get("source_address")),
        destination_address=_optional_int(payload.get("destination_address")),
        complete=bool(payload.get("complete", True)),
        frame_sequences=tuple(int(value) for value in frame_sequences),
        payload=bytes.fromhex(str(payload.get("payload_hex", ""))),
        error=str(payload.get("error", "")),
        confidence=float(payload.get("confidence", 1.0)),
        fields=dict(fields or {}),
    )


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        text = value.strip().lower().replace("_", "")
        return int(text, 16) if text.startswith("0x") else int(text, 10)
    return int(value)
