from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from .comparison_sets_view import ComparisonSetsView
from .project_properties_shell import ProjectPropertiesMainWindow


class ComparisonSetsMainWindow(ProjectPropertiesMainWindow):
    """CRT shell with persistent multi-session comparison-set management."""

    def _build_actions(self) -> None:
        super()._build_actions()
        try:
            self.compare_action.triggered.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.compare_action.setToolTip(
            "Twórz trwałe zestawy wielu zapisanych sesji do przyszłych analiz porównawczych"
        )
        self.compare_action.triggered.connect(
            lambda _checked=False: self._open_comparison_sets()
        )

    def _build_docks(self) -> None:
        super()._build_docks()
        self.explorer.open_comparison_sets.connect(self._open_comparison_sets)

    def _open_comparison_sets(self, comparison_set_id: str = "") -> None:
        project = self.project
        if project is None:
            QMessageBox.information(
                self,
                "CRT",
                "Najpierw otwórz lub utwórz projekt.",
            )
            return

        key = "comparison-sets"
        existing = self.navigator.widget(key)
        if isinstance(existing, ComparisonSetsView):
            existing.refresh(comparison_set_id or None)
            self._activate_tab(key)
            return

        widget = self.services.create_comparison_sets_view(project)
        widget.changed.connect(self.explorer.refresh)
        widget.output_message.connect(self._append_output)
        self._add_tab(key, widget, "Zestawy porównawcze")
        if comparison_set_id:
            widget.select_comparison_set(comparison_set_id)

    def _import_completed(self, source: str, target: str) -> None:
        super()._import_completed(source, target)
        widget = self.navigator.widget("comparison-sets")
        if isinstance(widget, ComparisonSetsView):
            widget.refresh()


__all__ = ["ComparisonSetsMainWindow"]
