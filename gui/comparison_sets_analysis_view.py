from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from app.project import CrtProject

from .comparison_analysis_dialog import ComparisonAnalysisDialog
from .comparison_sets_view import ComparisonSetsView
from .comparison_visualization_stage2d2 import ComparisonVisualizationDialog
from .window_fullscreen import FullScreenController, enable_full_screen


class AnalysisEnabledComparisonSetsView(ComparisonSetsView):
    """Comparison-set manager extended with registry-driven passive analyses."""

    evidence_open_requested = Signal(str, str, object)
    evidence_source_row_requested = Signal(str, int, str, object)

    def __init__(self, project: CrtProject, parent: QWidget | None = None) -> None:
        super().__init__(project, parent)
        self._analysis_dialogs: dict[str, ComparisonVisualizationDialog] = {}
        self._closing = False

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
            not self._closing and self.selected_comparison_set() is not None
        )

    def _open_analysis(self) -> None:
        comparison_set = self.selected_comparison_set()
        if comparison_set is None or self._closing:
            return
        existing = self._analysis_dialogs.get(comparison_set.id)
        if existing is not None:
            existing.showNormal()
            existing.raise_()
            existing.activateWindow()
            return

        # Keep this window fully independent from the main CRT window. On
        # Windows, a non-modal dialog with an owner is still kept above that
        # owner and can hide the session opened by evidence navigation.
        dialog = ComparisonVisualizationDialog(
            self.project,
            comparison_set.id,
            parent=None,
        )
        dialog.setModal(False)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        configure_comparison_analysis_window(dialog)
        dialog.output_message.connect(self.output_message.emit)
        dialog.evidence_open_requested.connect(self.evidence_open_requested.emit)
        dialog.source_row_open_requested.connect(
            self.evidence_source_row_requested.emit
        )
        dialog.finished.connect(
            lambda _result, set_id=comparison_set.id: self._analysis_finished(set_id)
        )
        self._analysis_dialogs[comparison_set.id] = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _analysis_finished(self, comparison_set_id: str) -> None:
        self._analysis_dialogs.pop(comparison_set_id, None)
        if self._closing:
            return
        self.refresh(comparison_set_id)
        self.changed.emit()

    def _close_analysis_dialogs(self) -> None:
        dialogs = tuple(self._analysis_dialogs.values())
        self._analysis_dialogs.clear()
        for dialog in dialogs:
            try:
                dialog.close_for_project_change()
            except RuntimeError:
                pass

    def closeEvent(self, event) -> None:
        self._closing = True
        self._close_analysis_dialogs()
        super().closeEvent(event)


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
