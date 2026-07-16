from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from .filter_manager import FilterManagerWidget


_installed = False
_original_table_item_changed = FilterManagerWidget._table_item_changed
_original_preset_editor_changed = FilterManagerWidget._preset_editor_changed


def install_filter_state_fix() -> None:
    """Persist activation changes immediately and allow invalid inactive drafts.

    A disabled preset must stop affecting every open view even when its unfinished
    tree is temporarily invalid. Only enabled presets are therefore required to
    pass validation before the complete preset set is stored.
    """

    global _installed
    if _installed:
        return
    _installed = True

    def integrated_save(
        self: FilterManagerWidget,
        _checked: bool = False,
        *,
        silent: bool = False,
    ) -> bool:
        invalid = [
            (preset, self.compiler.validate(preset))
            for preset in self.presets
            if preset.enabled
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

    def integrated_table_item_changed(self: FilterManagerWidget, item) -> None:
        if self._loading:
            return
        activation_changed = item.column() == 0
        _original_table_item_changed(self, item)
        if activation_changed:
            self._save(silent=True)

    def integrated_preset_editor_changed(self: FilterManagerWidget, *args: object) -> None:
        preset = self._current_preset()
        previous_enabled = preset.enabled if preset is not None else None
        _original_preset_editor_changed(self, *args)
        preset = self._current_preset()
        if (
            preset is not None
            and previous_enabled is not None
            and preset.enabled != previous_enabled
        ):
            self._save(silent=True)

    FilterManagerWidget._save = integrated_save
    FilterManagerWidget._table_item_changed = integrated_table_item_changed
    FilterManagerWidget._preset_editor_changed = integrated_preset_editor_changed
