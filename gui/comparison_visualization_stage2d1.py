from __future__ import annotations

from PySide6.QtCore import Slot

# Import registers feature-owned articles in the legacy shared Help catalog.
from app.help_catalog_experiment_diff import EXPERIMENT_DIFF_HELP_TOPIC as _EXPERIMENT_DIFF_HELP_TOPIC
from app.help_catalog_signal_candidates import SIGNAL_CANDIDATES_HELP_TOPIC as _SIGNAL_CANDIDATES_HELP_TOPIC
from app.help_catalog_signal_hypothesis import SIGNAL_HYPOTHESIS_HELP_TOPIC as _SIGNAL_HYPOTHESIS_HELP_TOPIC

from .comparison_uds_transaction_explorer_source_view import (
    PreferredSourceUdsTransactionExplorerView,
)
from .comparison_visualization_stage2c2 import (
    ComparisonVisualizationDialog as _BaseComparisonVisualizationDialog,
)
from .experiment_diff_view import ExperimentDiffView
from .signal_candidates_view import SignalCandidatesView
from .signal_hypothesis_view import SignalHypothesisView


class _SelectionSafeUdsTransactionExplorerView(
    PreferredSourceUdsTransactionExplorerView
):
    """Clear Qt selection before replacing the filtered transaction model."""

    def _populate_result(self) -> None:
        self.transaction_table.clearSelection()
        super()._populate_result()

    def _clear_result(self) -> None:
        self.transaction_table.clearSelection()
        super()._clear_result()


class ComparisonVisualizationDialog(_BaseComparisonVisualizationDialog):
    """Comparison dialog extended with UDS and signal reverse-engineering workflows."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.uds_explorer = _SelectionSafeUdsTransactionExplorerView(
            self.project,
            self.comparison_set,
            self.result_tabs,
        )
        self.uds_explorer.source_row_requested.connect(
            self._prepare_uds_explorer_evidence
        )
        self.result_tabs.insertTab(4, self.uds_explorer, "Transakcje UDS")

        self.experiment_diff = ExperimentDiffView(
            self.project,
            self.comparison_set,
            self.result_tabs,
        )
        self.experiment_diff.source_row_requested.connect(
            self._prepare_experiment_diff_evidence
        )
        self.experiment_diff.output_message.connect(self.output_message.emit)
        self.result_tabs.insertTab(5, self.experiment_diff, "Experiment Diff")

        self.signal_candidates = SignalCandidatesView(
            self.project,
            self.comparison_set,
            self.result_tabs,
        )
        self.signal_candidates.source_row_requested.connect(
            self._prepare_signal_candidate_evidence
        )
        self.signal_candidates.output_message.connect(self.output_message.emit)
        self.result_tabs.insertTab(6, self.signal_candidates, "Signal Candidates")

        self.signal_hypothesis = SignalHypothesisView(
            self.project,
            self.comparison_set,
            self.result_tabs,
        )
        self.signal_hypothesis.output_message.connect(self.output_message.emit)
        self.result_tabs.insertTab(7, self.signal_hypothesis, "Signal Hypothesis")

    def _set_signal_workspaces_enabled(self, enabled: bool) -> None:
        if hasattr(self, "experiment_diff"):
            self.experiment_diff.setEnabled(enabled)
        if hasattr(self, "signal_candidates"):
            self.signal_candidates.setEnabled(enabled)
        if hasattr(self, "signal_hypothesis"):
            self.signal_hypothesis.setEnabled(enabled)

    @Slot(str, int, str)
    def _prepare_timeline_evidence(
        self,
        session_id: str,
        source_row: int,
        message_key: str,
    ) -> None:
        super()._prepare_timeline_evidence(
            session_id,
            source_row,
            message_key,
        )
        if self._evidence_pending:
            self.timing.setEnabled(False)
            self.uds_latency.setEnabled(False)
            if hasattr(self, "uds_explorer"):
                self.uds_explorer.setEnabled(False)
            self._set_signal_workspaces_enabled(False)

    @Slot(str, int, str)
    def _prepare_timing_evidence(
        self,
        session_id: str,
        source_row: int,
        message_key: str,
    ) -> None:
        super()._prepare_timing_evidence(
            session_id,
            source_row,
            message_key,
        )
        if self._evidence_pending:
            self.uds_latency.setEnabled(False)
            if hasattr(self, "uds_explorer"):
                self.uds_explorer.setEnabled(False)
            self._set_signal_workspaces_enabled(False)

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
        self._set_signal_workspaces_enabled(False)

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
        self._set_signal_workspaces_enabled(False)
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

    @Slot(str, int, str)
    def _prepare_experiment_diff_evidence(
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
        self._set_signal_workspaces_enabled(False)
        self._set_evidence_running(True)
        self.status_label.setText(
            f"Otwieram ramkę {source_row + 1} z Experiment Diff. "
            "Okno porównania pozostaje otwarte."
        )
        self.source_row_open_requested.emit(
            session_id,
            int(source_row),
            message_key,
            self,
        )

    @Slot(str, int, str)
    def _prepare_signal_candidate_evidence(
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
        self._set_signal_workspaces_enabled(False)
        self._set_evidence_running(True)
        self.status_label.setText(
            f"Otwieram ramkę {source_row + 1} z Signal Candidates. "
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
        self.timeline.setEnabled(True)
        self.timing.setEnabled(True)
        self.uds_latency.setEnabled(True)
        self.uds_explorer.setEnabled(True)
        self._set_signal_workspaces_enabled(True)

    @Slot(str)
    def evidence_navigation_failed(self, error: str) -> None:
        super().evidence_navigation_failed(error)
        self.timeline.setEnabled(True)
        self.timing.setEnabled(True)
        self.uds_latency.setEnabled(True)
        self.uds_explorer.setEnabled(True)
        self._set_signal_workspaces_enabled(True)

    def close_for_project_change(self) -> None:
        self.uds_explorer.cancel_all()
        self.experiment_diff.cancel_all()
        self.signal_candidates.cancel_all()
        self.signal_hypothesis.cancel_all()
        super().close_for_project_change()

    def closeEvent(self, event) -> None:
        self.uds_explorer.cancel_all()
        self.experiment_diff.cancel_all()
        self.signal_candidates.cancel_all()
        self.signal_hypothesis.cancel_all()
        super().closeEvent(event)


__all__ = ["ComparisonVisualizationDialog"]
