from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidgetItem,
    QWidget,
)

from app.filter_preferences import FilterCombinationMode
from app.filter_tree import node_at, summarize_node
from app.filters import FilterMode

from .enhanced_filter_manager import EnhancedFilterManagerWidget


class CompactFilterManagerWidget(EnhancedFilterManagerWidget):
    """Compact transactional editor for Global Filter Engine presets.

    Every edit remains in the in-memory working copy until the user explicitly
    applies it. Live Capture, stored sessions and global shortcuts continue using
    the last persisted configuration while the editor is dirty.
    """

    def _build_ui(self) -> None:
        super()._build_ui()
        self._install_cursor_safe_value_editor()

        root = self.layout()
        if root is None:
            return

        old_box = self.combination_combo.parentWidget()
        while old_box is not None and not isinstance(old_box, QGroupBox):
            old_box = old_box.parentWidget()

        details = (
            "AND: rekord musi pasować do wszystkich aktywnych presetów Include.\n"
            "OR: rekord może pasować do dowolnego aktywnego presetu Include.\n"
            "Exclude nadal ukrywa po dopasowaniu dowolnego presetu, a Highlight nie zmienia widoczności."
        )

        bar = QWidget(self)
        bar.setObjectName("filterCombinationBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel("Łączenie presetów Include:", bar)
        label.setObjectName("filterCombinationLabel")
        label.setToolTip(details)
        layout.addWidget(label)

        self.combination_combo.setParent(bar)
        self.combination_combo.setToolTip(details)
        self.combination_combo.setMaximumWidth(260)
        and_index = self.combination_combo.findData(FilterCombinationMode.AND.value)
        or_index = self.combination_combo.findData(FilterCombinationMode.OR.value)
        if and_index >= 0:
            self.combination_combo.setItemText(and_index, "AND — wszystkie")
        if or_index >= 0:
            self.combination_combo.setItemText(or_index, "OR — dowolny")
        layout.addWidget(self.combination_combo)
        layout.addStretch(1)

        if old_box is not None:
            root.removeWidget(old_box)
            old_box.hide()
            old_box.deleteLater()

        root.insertWidget(1, bar)
        self._install_transaction_controls()

    def _install_cursor_safe_value_editor(self) -> None:
        """Keep text editing local instead of rebuilding the properties form."""

        try:
            self.condition_values.textEdited.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.condition_values.textEdited.connect(self._condition_values_edited)

    def _condition_values_edited(self, _text: str = "") -> None:
        """Update the working tree without resetting QLineEdit cursor/selection."""

        if self._loading:
            return
        preset = self._current_preset()
        if preset is None:
            return
        try:
            node = node_at(preset.root, self._selected_path)
        except (ValueError, IndexError):
            return
        if node.get("type") != "condition":
            return

        node["operator"] = str(self.condition_operator.currentData())
        node["values"] = [
            part.strip()
            for part in self.condition_values.text().split(",")
            if part.strip()
        ]
        self._mark_dirty()
        self._refresh_edited_condition(preset, node)
        self._update_value_hint(str(node.get("field", "")))

    def _refresh_edited_condition(self, preset, node: dict) -> None:
        """Refresh diagnostics and tree summary without reloading editor widgets."""

        items = self.tree.selectedItems()
        if items:
            item = items[0]
            item.setText(0, summarize_node(node))
            issue_paths = {issue.path for issue in self.compiler.validate(preset)}
            if self._path_has_issue(self._selected_path, issue_paths):
                item.setText(1, "⚠")
                item.setToolTip(1, "Element zawiera błąd walidacji")
            else:
                item.setText(1, "")
                item.setToolTip(1, "")

        self.json_preview.setPlainText(
            json.dumps(preset.root, ensure_ascii=False, indent=2)
        )
        self._show_validation_summary()

    def _install_transaction_controls(self) -> None:
        save_button = next(
            (
                button
                for button in self.findChildren(QPushButton)
                if button.text() == "Zapisz teraz"
            ),
            None,
        )
        if save_button is None:
            return

        parent = save_button.parentWidget()
        parent_layout = parent.layout() if parent is not None else None
        if parent is None or parent_layout is None:
            return

        parent_layout.removeWidget(save_button)
        buttons = QWidget(parent)
        buttons.setObjectName("filterTransactionBar")
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.discard_button = QPushButton("Odrzuć zmiany", buttons)
        self.discard_button.setObjectName("discardFilterChanges")
        self.discard_button.setToolTip(
            "Przywróć ostatnio zastosowany stan filtrów z projektu."
        )
        self.discard_button.clicked.connect(self._discard_changes)
        row.addWidget(self.discard_button)

        self.apply_button = save_button
        self.apply_button.setParent(buttons)
        self.apply_button.setObjectName("applyFilterChanges")
        self.apply_button.setText("Zastosuj zmiany")
        self.apply_button.setToolTip(
            "Zweryfikuj i zapisz wszystkie przygotowane zmiany w filtrach."
        )
        row.addWidget(self.apply_button)

        parent_layout.addWidget(buttons)
        self._update_transaction_controls()

    @property
    def has_pending_changes(self) -> bool:
        return bool(self._dirty)

    def _mark_dirty(self) -> None:
        self._dirty = True
        self.autosave_timer.stop()
        self.save_state_label.setText("Niezastosowane zmiany")
        self._update_transaction_controls()
        self._update_status()

    def _autosave(self) -> None:
        """Compatibility hook: transactional editing deliberately never autosaves."""

        self.autosave_timer.stop()

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
        self._mark_dirty()
        self._selection_changed()
        self._update_status()

    def _preset_editor_changed(self, *_args: object) -> None:
        if self._loading:
            return
        preset = self._current_preset()
        if preset is None:
            return
        preset.name = self.name_edit.text().strip()
        preset.description = self.description_edit.text().strip()
        preset.shortcut = self.shortcut_edit.text().strip()
        preset.mode = FilterMode(str(self.mode_combo.currentData()))
        preset.enabled = self.enabled_check.isChecked()
        row = self._current_row()
        self._loading = True
        try:
            self.table.item(row, 0).setCheckState(
                Qt.CheckState.Checked if preset.enabled else Qt.CheckState.Unchecked
            )
            self.table.item(row, 1).setText(preset.name)
            self.table.item(row, 2).setText(preset.shortcut)
        finally:
            self._loading = False
        self._mark_dirty()
        self._update_status()

    def reload_from_repository(self) -> None:
        """Replace the working copy with the last explicitly applied state."""

        current = self._current_preset()
        selected_id = current.id if current is not None else None
        self.presets = self.repository.list_presets()

        self._loading = True
        try:
            mode = self.preferences.combination_mode()
            self.combination_combo.setCurrentIndex(
                max(0, self.combination_combo.findData(mode.value))
            )
        finally:
            self._loading = False

        selected_row = next(
            (
                index
                for index, preset in enumerate(self.presets)
                if preset.id == selected_id
            ),
            0 if self.presets else -1,
        )
        self._dirty = False
        self.autosave_timer.stop()
        self.save_state_label.setText("Zastosowano")
        self._reload_table(selected_row if selected_row >= 0 else None)
        self._update_transaction_controls()

    def _discard_changes(self, _checked: bool = False) -> None:
        if not self._dirty:
            return
        self.reload_from_repository()
        self.output_message.emit("Odrzucono niezastosowane zmiany filtrów.")

    def _save(self, _checked: bool = False, *, silent: bool = False) -> bool:
        saved = super()._save(_checked, silent=silent)
        if saved:
            self.save_state_label.setText("Zastosowano")
        self._update_transaction_controls()
        return saved

    def _update_transaction_controls(self) -> None:
        pending = bool(self._dirty)
        apply_button = getattr(self, "apply_button", None)
        discard_button = getattr(self, "discard_button", None)
        if apply_button is not None:
            apply_button.setEnabled(pending)
        if discard_button is not None:
            discard_button.setEnabled(pending)

    def _update_status(self) -> None:
        super()._update_status()
        if self._dirty:
            self.status_label.setText(
                f"{self.status_label.text()} | Edycja: oczekuje na zastosowanie"
            )
