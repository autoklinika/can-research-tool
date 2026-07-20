from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from app.filters import ProjectFilterRepository
from app.static_filter_engine import StaticFilterCompiler

from .filter_manager_window import WindowedFilterMainWindow
from .filter_shortcut_support import check_filter_shortcuts


class StaticFilterWindowMainWindow(WindowedFilterMainWindow):
    """Main window using the v2 static compiler for preset activation checks."""

    def _toggle_filter_preset(self, preset_id: str) -> None:
        if self.project is None:
            return

        window = self._filter_window
        if window is not None and window.has_pending_changes:
            self._append_output(
                "Nie przełączono presetu skrótem: najpierw zastosuj albo odrzuć zmiany w edytorze filtrów."
            )
            window.raise_()
            window.activateWindow()
            return

        repository = ProjectFilterRepository(self.project.database_path)
        presets = repository.list_presets()
        selected = next((preset for preset in presets if preset.id == preset_id), None)
        if selected is None:
            self._reload_filter_shortcuts()
            return

        target_enabled = not selected.enabled
        if target_enabled:
            issues = StaticFilterCompiler().validate(selected)
            if issues:
                message = (
                    f"Nie można aktywować filtra „{selected.name}” skrótem: "
                    f"{issues[0].path}: {issues[0].message}"
                )
                self._append_output(message)
                QMessageBox.warning(self, "Nieprawidłowy filtr", message)
                return

        selected.enabled = target_enabled
        check = check_filter_shortcuts(
            presets,
            project=self.project,
            action_root=self,
        )
        if check.messages:
            message = "\n".join(check.messages[:10])
            self._append_output(f"Nie przełączono presetu: {message}")
            QMessageBox.warning(self, "Konflikt skrótów filtrów", message)
            return

        try:
            repository.save_presets(presets)
        except Exception as exc:
            QMessageBox.critical(self, "Nie można przełączyć filtra", str(exc))
            return

        state = "WŁĄCZONY" if selected.enabled else "WYŁĄCZONY"
        self._append_output(
            f"Filtr „{selected.name}”: {state} (skrót {selected.shortcut})"
        )
        self.explorer.refresh()
        if window is not None and hasattr(window.manager, "reload_from_repository"):
            window.manager.reload_from_repository()
        self._reload_filter_shortcuts()
