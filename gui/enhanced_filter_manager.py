from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel, QMessageBox

from app.filter_preferences import FilterCombinationMode, ProjectFilterPreferences
from app.project import CrtProject

from .filter_manager import FilterManagerWidget
from .filter_shortcut_support import FilterShortcutCheck, check_filter_shortcuts


class EnhancedFilterManagerWidget(FilterManagerWidget):
    """Final Global Filter Engine editor features for the v1 scope."""

    def __init__(self, project: CrtProject, parent=None) -> None:
        self.preferences = ProjectFilterPreferences(project.database_path)
        super().__init__(project, parent)

    def _build_ui(self) -> None:
        super()._build_ui()

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
            # The base save already emitted once for preset changes. Emit again after
            # storing the preference so Live/stored views reload the final signature.
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
