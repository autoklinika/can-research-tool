from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from .comparison_evidence_navigation import ComparisonEvidenceCoordinator
from .comparison_sets_analysis_view import AnalysisEnabledComparisonSetsView
from .comparison_sets_view import ComparisonSetsView
from .project_properties_shell import ProjectPropertiesMainWindow


class ComparisonSetsMainWindow(ProjectPropertiesMainWindow):
    """CRT shell with persistent comparison sets and passive comparison analyses."""

    def _build_actions(self) -> None:
        super()._build_actions()
        try:
            self.compare_action.triggered.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.compare_action.setToolTip(
            "Twórz trwałe zestawy sesji i uruchamiaj pasywne analizy porównawcze"
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
            self._bind_comparison_evidence(existing)
            existing.refresh(comparison_set_id or None)
            self._activate_tab(key)
            return

        widget = self.services.create_comparison_sets_view(project)
        widget.changed.connect(self.explorer.refresh)
        widget.output_message.connect(self._append_output)
        self._bind_comparison_evidence(widget)
        self._add_tab(key, widget, "Zestawy porównawcze")
        if comparison_set_id:
            widget.select_comparison_set(comparison_set_id)

    def _bind_comparison_evidence(self, widget: ComparisonSetsView) -> None:
        if not isinstance(widget, AnalysisEnabledComparisonSetsView):
            return
        if bool(widget.property("comparisonEvidenceBound")):
            return
        widget.evidence_open_requested.connect(self._open_comparison_evidence)
        widget.setProperty("comparisonEvidenceBound", True)

    def _open_comparison_evidence(
        self,
        session_id: str,
        message_key: str,
    ) -> None:
        coordinator = getattr(self, "_comparison_evidence_coordinator", None)
        if not isinstance(coordinator, ComparisonEvidenceCoordinator):
            coordinator = ComparisonEvidenceCoordinator(self)
            self._comparison_evidence_coordinator = coordinator
        coordinator.open_evidence(session_id, message_key)

    def _import_completed(self, source: str, target: str) -> None:
        super()._import_completed(source, target)
        widget = self.navigator.widget("comparison-sets")
        if isinstance(widget, ComparisonSetsView):
            widget.refresh()


__all__ = ["ComparisonSetsMainWindow"]
