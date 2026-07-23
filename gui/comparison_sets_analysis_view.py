from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from app.project import CrtProject

from .comparison_analysis_dialog import ComparisonAnalysisDialog
from .comparison_sets_view import ComparisonSetsView
from .comparison_visualization import ComparisonVisualizationDialog
from .window_fullscreen import FullScreenController, enable_full_screen


class AnalysisEnabledComparisonSetsView(ComparisonSetsView):
    """Comparison-set manager extended with registry-driven passive analyses."""

    evidence_open_requested = Signal(str, str, object)

    def __init__(self, project: CrtProject, parent: QWidget | None = None) -> None:
        super().__init__(project, parent)
        analysis_toolbar = QHBoxLayout()
        self.analyze_button = QPushButton("Analizuj wybrany zestaw…", self)
        self.analyze_button.setObjectName("analyzeComparisonSetButton")
        self.analyze_button.clicked.connect(self._open_analysis)
        analysis_toolbar.addWidget(self.analyze_button)
        analysis_toolbar.addStretch(1)

        root = self.layout()
        if root is None:
            raise RuntimeError("comparison sets view has no root layout")
        root.insertLayout(3, analysis_toolbar)
        self.table.itemSelectionChanged.connect(
            self._analysis_selection_changed
        )
        self._analysis_selection_changed()

    def refresh(self, selected_id: str | None = None) -> None:
        super().refresh(selected_id)
        if hasattr(self, "analyze_button"):
            self._analysis_selection_changed()

    def _analysis_selection_changed(self) -> None:
        self.analyze_button.setEnabled(
            self.selected_comparison_set() is not None
        )

    def _open_analysis(self) -> None:
        comparison_set = self.selected_comparison_set()
        if comparison_set is None:
            return
        dialog = ComparisonVisualizationDialog(
            self.project,
            comparison_set.id,
            parent=self,
        )
        configure_comparison_analysis_window(dialog)
        dialog.output_message.connect(self.output_message.emit)
        dialog.evidence_open_requested.connect(self.evidence_open_requested.emit)
        dialog.exec()
        self.refresh(comparison_set.id)
        self.changed.emit()


def configure_comparison_analysis_window(
    dialog: ComparisonAnalysisDialog,
) -> FullScreenController:
    """Enable native maximization and the shared F11 full-screen toggle."""

    controller = enable_full_screen(
        dialog,
        action_object_name="comparisonAnalysisFullScreenAction",
        maximize_button=True,
    )
    dialog.full_screen_controller = controller
    return controller


__all__ = [
    "AnalysisEnabledComparisonSetsView",
    "configure_comparison_analysis_window",
]
