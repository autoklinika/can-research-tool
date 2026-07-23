from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QTabWidget, QWidget

from .comparison_visualization_dashboard import ComparisonVisualizationWidget
from .comparison_visualization_model import (
    SCHEMA_PAYLOAD,
    SCHEMA_SEQUENCE,
    SCHEMA_STATISTICS,
    ComparisonDashboardData,
    ComparisonVisualRow,
    build_dashboard_data,
)
from .message_sequence_analysis_dialog import (
    MessageSequenceComparisonAnalysisDialog,
)

_ARTIFACT_TYPES = {
    "comparison_statistics",
    "payload_differences",
    "message_sequence_differences",
}
_SUPPORTED_SCHEMAS = {
    SCHEMA_STATISTICS,
    SCHEMA_PAYLOAD,
    SCHEMA_SEQUENCE,
}


class ComparisonVisualizationDialog(MessageSequenceComparisonAnalysisDialog):
    """Existing passive comparison workflow with an artifact-backed dashboard."""

    def __init__(
        self,
        project,
        comparison_set_id: str,
        parent: QWidget | None = None,
    ) -> None:
        self.dashboard: ComparisonVisualizationWidget | None = None
        super().__init__(project, comparison_set_id, parent)
        self.setWindowTitle(f"Porównanie logów — {self.comparison_set.name}")
        self.resize(1480, 920)
        splitter = self.sessions_table.parentWidget()
        root = self.layout()
        if splitter is None or root is None:
            raise RuntimeError("comparison dialog layout is incomplete")
        root.removeWidget(splitter)
        tabs = QTabWidget(self)
        tabs.setObjectName("comparisonResultTabs")
        self.dashboard = ComparisonVisualizationWidget(
            self.comparison_set.name,
            tabs,
        )
        tabs.addTab(self.dashboard, "Przegląd graficzny")
        tabs.addTab(splitter, "Dane artefaktu")
        root.insertWidget(root.count() - 1, tabs, 1)
        self.result_tabs = tabs
        self._refresh_dashboard()

    def _load_artifacts(self, preferred_artifact_id: str = "") -> None:
        super()._load_artifacts(preferred_artifact_id)
        if self.dashboard is not None:
            self._refresh_dashboard()

    def _refresh_dashboard(self) -> None:
        if self.dashboard is None:
            return
        latest = {}
        for artifact in self._artifacts:
            if artifact.artifact_type not in _ARTIFACT_TYPES:
                continue
            current = latest.get(artifact.artifact_type)
            if current is None or artifact.created_at_utc > current.created_at_utc:
                latest[artifact.artifact_type] = artifact
        payloads: dict[str, dict[str, Any]] = {}
        for artifact in latest.values():
            try:
                payload = self.service.artifacts.read_json(artifact)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            schema = str(payload.get("schema") or "")
            if schema in _SUPPORTED_SCHEMAS:
                payloads[schema] = payload
        if payloads:
            self.dashboard.set_payloads(payloads)
        else:
            self.dashboard.clear()


__all__ = [
    "ComparisonDashboardData",
    "ComparisonVisualizationDialog",
    "ComparisonVisualizationWidget",
    "ComparisonVisualRow",
    "build_dashboard_data",
]
