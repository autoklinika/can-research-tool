from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from app.project import CrtProject

from .comparison_analysis_dialog import ComparisonAnalysisDialog
from .comparison_sets_view import ComparisonSetsView


_FULL_SCREEN_STATE_PROPERTY = "comparisonAnalysisWasMaximized"


class AnalysisEnabledComparisonSetsView(ComparisonSetsView):
    """Comparison-set manager extended with registry-driven passive analyses."""

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
        self.table.itemSelectionChanged.connect(self._analysis_selection_changed)
        self._analysis_selection_changed()

    def refresh(self, selected_id: str | None = None) -> None:
        super().refresh(selected_id)
        if hasattr(self, "analyze_button"):
            self._analysis_selection_changed()

    def _analysis_selection_changed(self) -> None:
        self.analyze_button.setEnabled(self.selected_comparison_set() is not None)

    def _open_analysis(self) -> None:
        comparison_set = self.selected_comparison_set()
        if comparison_set is None:
            return
        dialog = ComparisonAnalysisDialog(
            self.project,
            comparison_set.id,
            parent=self,
        )
        configure_comparison_analysis_window(dialog)
        dialog.output_message.connect(self.output_message.emit)
        dialog.exec()
        self.refresh(comparison_set.id)
        self.changed.emit()


def configure_comparison_analysis_window(dialog: ComparisonAnalysisDialog) -> None:
    """Enable native maximization and an F11 full-screen toggle."""

    dialog.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
    shortcut = QShortcut(QKeySequence("F11"), dialog)
    shortcut.setObjectName("comparisonAnalysisFullScreenShortcut")
    shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
    shortcut.activated.connect(lambda: _toggle_full_screen(dialog))


def _toggle_full_screen(dialog: ComparisonAnalysisDialog) -> None:
    if dialog.isFullScreen():
        if bool(dialog.property(_FULL_SCREEN_STATE_PROPERTY)):
            dialog.showMaximized()
        else:
            dialog.showNormal()
        return

    dialog.setProperty(_FULL_SCREEN_STATE_PROPERTY, dialog.isMaximized())
    dialog.showFullScreen()


__all__ = [
    "AnalysisEnabledComparisonSetsView",
    "configure_comparison_analysis_window",
]
