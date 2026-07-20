from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
)

from app.filter_preferences import FilterCombinationMode, ProjectFilterPreferences
from app.filter_tree import node_at
from app.filters import FilterField, FilterOperator, MatchState
from app.project import CrtProject
from app.static_filter_engine import (
    StaticCanFrameRecord,
    StaticFilterCompiler,
)

from .filter_field_catalog import FIELD_DEFAULTS, FIELD_HINTS
from .filter_manager import (
    OPERATOR_LABELS,
    FilterManagerWidget,
    _logical_record_from_test_payload,
)
from .filter_shortcut_support import FilterShortcutCheck, check_filter_shortcuts
from .static_filter_editor_support import (
    STATIC_FIELD_DEFAULTS,
    STATIC_FIELD_HINTS,
    STATIC_FILTER_FIELD_CHOICES,
    STATIC_OPERATOR_LABELS,
    default_operator_for_field,
    is_static_condition,
    operator_hint,
    operators_for_field,
    summarize_static_condition,
)


class EnhancedFilterManagerWidget(FilterManagerWidget):
    """Global Filter Engine editor with v1 and advanced static v2 conditions."""

    def __init__(self, project: CrtProject, parent=None) -> None:
        self.preferences = ProjectFilterPreferences(project.database_path)
        super().__init__(project, parent)
        self.compiler = StaticFilterCompiler()
        self._reload_tree(self._selected_path)

    def _build_ui(self) -> None:
        super()._build_ui()

        for choice in STATIC_FILTER_FIELD_CHOICES:
            if self.condition_field.findData(choice.field) < 0:
                self.condition_field.addItem(choice.label, choice.field)
        self._refresh_operator_combo(FilterField.CAN_ID.value, FilterOperator.EQ.value)

        test_box = self.test_context.parentWidget()
        test_form = test_box.layout() if test_box is not None else None
        if isinstance(test_form, QFormLayout):
            self.test_channel = QSpinBox()
            self.test_channel.setObjectName("staticFilterTestChannel")
            self.test_channel.setRange(0, 65535)
            test_form.insertRow(4, "Kanał", self.test_channel)

            self.test_rtr = QCheckBox("RTR")
            self.test_rtr.setObjectName("staticFilterTestRtr")
            test_form.insertRow(5, "", self.test_rtr)

            self.test_error_frame = QCheckBox("Error frame")
            self.test_error_frame.setObjectName("staticFilterTestErrorFrame")
            test_form.insertRow(6, "", self.test_error_frame)

            self.test_payload = QLineEdit("62 F1 90")
            self.test_payload.setObjectName("staticFilterTestPayload")
            self.test_payload.setPlaceholderText("np. 62 F1 90")
            test_form.insertRow(7, "Payload [HEX]", self.test_payload)

        box = QGroupBox("Łączenie wielu presetów Include")
        form = QFormLayout(box)
        self.combination_combo = QComboBox()
        self.combination_combo.setObjectName("filterCombinationMode")
        self.combination_combo.addItem(
            "AND — rekord musi pasować do wszystkich presetów Include",
            FilterCombinationMode.AND.value,
        )
        self.combination_combo.addItem(
            "OR — rekord może pasować do dowolnego presetu Include",
            FilterCombinationMode.OR.value,
        )
        current = self.preferences.combination_mode()
        self.combination_combo.setCurrentIndex(
            max(0, self.combination_combo.findData(current.value))
        )
        self.combination_combo.currentIndexChanged.connect(self._combination_changed)
        form.addRow("Tryb", self.combination_combo)

        note = QLabel(
            "Exclude nadal ukrywa rekord po dopasowaniu dowolnego aktywnego presetu. "
            "Highlight nigdy nie wpływa na widoczność."
        )
        note.setWordWrap(True)
        form.addRow("", note)

        root = self.layout()
        if root is not None:
            root.insertWidget(1, box)
        self._test_context_changed()

    @property
    def combination_mode(self) -> FilterCombinationMode:
        return FilterCombinationMode(str(self.combination_combo.currentData()))

    def reload_from_repository(self) -> None:
        """Refresh the editor after a preset shortcut toggled outside this window."""

        selected = self._current_row()
        self.presets = self.repository.list_presets()
        self._dirty = False
        self.autosave_timer.stop()
        self.save_state_label.setText("Zapisano")
        self._reload_table(selected if selected >= 0 else None)

    def _refresh_operator_combo(self, field_name: str, selected: str | None = None) -> None:
        allowed = list(operators_for_field(field_name))
        if selected and selected not in allowed:
            allowed.append(selected)
        previous_loading = self._loading
        self._loading = True
        try:
            self.condition_operator.clear()
            labels = {**OPERATOR_LABELS, **STATIC_OPERATOR_LABELS}
            for operator_name in allowed:
                self.condition_operator.addItem(labels.get(operator_name, operator_name), operator_name)
            target = selected or default_operator_for_field(field_name)
            self.condition_operator.setCurrentIndex(
                max(0, self.condition_operator.findData(target))
            )
        finally:
            self._loading = previous_loading

    def _reload_tree(self, select_path: tuple[int, ...] | None = None) -> None:
        super()._reload_tree(select_path)
        preset = self._current_preset()
        if preset is None:
            return

        def update_item(item) -> None:
            raw_path = item.data(0, Qt.ItemDataRole.UserRole) or []
            try:
                node = node_at(preset.root, tuple(int(value) for value in raw_path))
            except (ValueError, IndexError):
                node = None
            if isinstance(node, dict):
                summary = summarize_static_condition(node)
                if summary:
                    item.setText(0, summary)
            for child_index in range(item.childCount()):
                update_item(item.child(child_index))

        root = self.tree.invisibleRootItem()
        for index in range(root.childCount()):
            update_item(root.child(index))

    def _load_node_properties(self) -> None:
        super()._load_node_properties()
        preset = self._current_preset()
        if preset is None:
            return
        try:
            node = node_at(preset.root, self._selected_path)
        except (ValueError, IndexError):
            return
        if node.get("type") != "condition":
            return
        field_name = str(node.get("field", FilterField.CAN_ID.value))
        operator_name = str(node.get("operator", FilterOperator.EQ.value))
        self._refresh_operator_combo(field_name, operator_name)
        self._update_value_hint(field_name)

    def _condition_field_changed(self, *_args: object) -> None:
        if self._loading:
            return
        preset = self._current_preset()
        if preset is None:
            return
        node = node_at(preset.root, self._selected_path)
        field_name = str(self.condition_field.currentData())
        operator_name = default_operator_for_field(field_name)
        default_value = STATIC_FIELD_DEFAULTS.get(
            field_name,
            FIELD_DEFAULTS.get(field_name, ""),
        )
        node["field"] = field_name
        node["operator"] = operator_name
        node["values"] = [default_value]
        self._refresh_operator_combo(field_name, operator_name)
        self._tree_mutated(self._selected_path)

    def _condition_property_changed(self, *_args: object) -> None:
        if self._loading:
            return
        super()._condition_property_changed()
        field_name = str(self.condition_field.currentData())
        self._update_value_hint(field_name)

    def _update_value_hint(self, field: str) -> None:
        base_hint = STATIC_FIELD_HINTS.get(field, FIELD_HINTS.get(field, ""))
        selected_operator = ""
        if hasattr(self, "condition_operator"):
            selected_operator = str(self.condition_operator.currentData() or "")
        extra = operator_hint(selected_operator)
        self.value_hint.setText(" ".join(part for part in (base_hint, extra) if part))

    def _test_context_changed(self, *_args: object) -> None:
        super()._test_context_changed(*_args)
        logical = self.test_context.currentData() == "logical"
        for name in (
            "test_channel",
            "test_rtr",
            "test_error_frame",
            "test_payload",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setVisible(not logical)

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
                if is_static_condition(preset.root):
                    self.test_result.setText(
                        "UNAVAILABLE — warunki kanału, RTR, error frame, maski CAN ID i payloadu "
                        "są oceniane w kontekście surowej ramki CAN."
                    )
                    return
                payload = json.loads(self.test_logical_json.toPlainText())
                record = _logical_record_from_test_payload(payload)
                result = self.compiler.legacy.evaluate_logical_message(
                    preset,
                    record,
                    relative_time_us=int(payload.get("relative_time_us", 0)),
                )
            else:
                text = self.test_can_id.text().strip().lower()
                frame = StaticCanFrameRecord(
                    can_id=int(text, 16),
                    extended=self.test_format.currentText() == "EXT",
                    dlc=self.test_dlc.value(),
                    relative_time_us=int(self.test_time.text().strip()),
                    channel=self.test_channel.value(),
                    rtr=self.test_rtr.isChecked(),
                    error_frame=self.test_error_frame.isChecked(),
                    payload=bytes.fromhex(self.test_payload.text().strip()),
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

    def _combination_changed(self, *_args: object) -> None:
        self._mark_dirty()
        self._update_status()

    def _save(self, _checked: bool = False, *, silent: bool = False) -> bool:
        shortcut_check = self._shortcut_check()
        if shortcut_check.messages:
            self.save_state_label.setText("Konflikt skrótu — nie zapisano")
            message = "\n".join(shortcut_check.messages[:10])
            if not silent:
                QMessageBox.warning(self, "Konflikt skrótów filtrów", message)
            self.output_message.emit(f"Nie zapisano filtrów: {message}")
            return False

        self._apply_canonical_shortcuts(shortcut_check)
        previous_mode = self.preferences.combination_mode()
        if not super()._save(_checked, silent=silent):
            return False

        selected_mode = self.combination_mode
        self.preferences.set_combination_mode(selected_mode)
        if selected_mode is not previous_mode:
            self.output_message.emit(
                f"Łączenie presetów Include: {selected_mode.value.upper()}"
            )
            self.changed.emit()
        self._update_status()
        return True

    def _shortcut_check(self) -> FilterShortcutCheck:
        window = self.window()
        action_root = window.parentWidget() if window is not None else None
        return check_filter_shortcuts(
            self.presets,
            project=self.project,
            action_root=action_root,
        )

    def _apply_canonical_shortcuts(self, check: FilterShortcutCheck) -> None:
        self._loading = True
        try:
            for row, preset in enumerate(self.presets):
                canonical = check.canonical_by_id.get(preset.id, "")
                preset.shortcut = canonical
                item = self.table.item(row, 2)
                if item is not None:
                    item.setText(canonical)
            current = self._current_preset()
            if current is not None:
                self.shortcut_edit.setText(current.shortcut)
        finally:
            self._loading = False

    def _update_status(self) -> None:
        super()._update_status()
        if not hasattr(self, "combination_combo"):
            return
        self.status_label.setText(
            f"{self.status_label.text()} | Include: {self.combination_mode.value.upper()}"
        )
