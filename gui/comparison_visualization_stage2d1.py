from __future__ import annotations

from PySide6.QtCore import Slot

from .comparison_uds_transaction_explorer_view import (
    ComparisonUdsTransactionExplorerView,
)
from .comparison_visualization_stage2c2 import (
    ComparisonVisualizationDialog as _BaseComparisonVisualizationDialog,
)


class ComparisonVisualizationDialog(_BaseComparisonVisualizationDialog):
    """Comparison dialog extended with artifact-backed UDS transaction explorer."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.uds_explorer = ComparisonUdsTransactionExplorerView(
            self.project,
            self.comparison_set,
            self.result_tabs,
        )
        self.uds_explorer.source_row_requested.connect(
            self._prepare_uds_explorer_evidence
        )
        self.result_tabs.insertTab(4, self.uds_explorer, "Transakcje UDS")

    @Slot(str, int, str)
    def _prepare_uds_latency_evidence(
        self,
        session_id: str,
        source_row: int,
        message_key: str,
    ) -> None:
        super()._prepare_uds_latency_evidence(
            session_id,
            source_row,
            message_key,
        )
        if hasattr(self, "uds_explorer"):
            self.uds_explorer.setEnabled(False)

    @Slot(str, int, str)
    def _prepare_uds_explorer_evidence(
        self,
        session_id: str,
        source_row: int,
        message_key: str,
    ) -> None:
        if self._evidence_pending:
            return
        self.pending_evidence = (session_id, message_key)
        self._evidence_pending = True
        self.timeline.setEnabled(False)
        self.timing.setEnabled(False)
        self.uds_latency.setEnabled(False)
        self.uds_explorer.setEnabled(False)
        self._set_evidence_running(True)
        self.status_label.setText(
            f"Otwieram ramkę {source_row + 1} z eksploratora UDS. "
            "Okno porównania pozostaje otwarte."
        )
        self.source_row_open_requested.emit(
            session_id,
            int(source_row),
            message_key,
            self,
        )

    @Slot()
    def evidence_navigation_succeeded(self) -> None:
        super().evidence_navigation_succeeded()
        self.uds_explorer.setEnabled(True)

    @Slot(str)
    def evidence_navigation_failed(self, error: str) -> None:
        super().evidence_navigation_failed(error)
        self.uds_explorer.setEnabled(True)

    def close_for_project_change(self) -> None:
        self.uds_explorer.cancel_all()
        super().close_for_project_change()

    def closeEvent(self, event) -> None:
        self.uds_explorer.cancel_all()
        super().closeEvent(event)


__all__ = ["ComparisonVisualizationDialog"]
