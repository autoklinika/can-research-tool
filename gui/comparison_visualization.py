from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .comparison_visualization_filtered import (
    FilteredComparisonVisualizationWidget as ComparisonVisualizationWidget,
)
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
    """Passive comparison workflow with an artifact-backed visual dashboard."""

    def __init__(
        self,
        project,
        comparison_set_id: str,
        parent: QWidget | None = None,
    ) -> None:
        self.dashboard: ComparisonVisualizationWidget | None = None
        self.pending_evidence: tuple[str, str] | None = None
        self._batch_provider_ids: list[str] = []
        self._batch_total = 0
        self._batch_completed = 0
        super().__init__(project, comparison_set_id, parent)
        self.setObjectName("comparisonVisualizationDialog")
        self.setWindowTitle(f"Porównanie logów — {self.comparison_set.name}")
        self.resize(1480, 920)
        self.setMinimumSize(1180, 720)

        root = self.layout()
        splitter = self.sessions_table.parentWidget()
        if root is None or splitter is None:
            raise RuntimeError("comparison dialog layout is incomplete")

        title = self.findChild(QLabel, "comparisonAnalysisTitle")
        if title is not None:
            title.setText(f"Porównanie logów · {self.comparison_set.name}")

        controls = _take_layout_containing_widget(root, self.run_button)
        if controls is None:
            raise RuntimeError("comparison controls layout is missing")
        controls.removeWidget(self.cancel_button)
        controls.removeWidget(self.refresh_button)
        self.run_button.setText("Uruchom wybraną")
        self.refresh_button.setText("Odśwież")

        self.run_all_button = QPushButton("Uruchom komplet analiz", self)
        self.run_all_button.setObjectName("runAllComparisonAnalyses")
        self.run_all_button.clicked.connect(self._start_all_analyses)
        self.advanced_button = QPushButton("Zaawansowane ▸", self)
        self.advanced_button.setObjectName("comparisonAdvancedToggle")
        self.advanced_button.setCheckable(True)
        self.advanced_button.toggled.connect(self._toggle_advanced)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addWidget(self.run_all_button)
        actions.addWidget(self.advanced_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.refresh_button)
        actions.addStretch(1)
        root.insertLayout(1, actions)

        self.advanced_panel = QWidget(self)
        self.advanced_panel.setObjectName("comparisonAdvancedPanel")
        advanced_layout = QVBoxLayout(self.advanced_panel)
        advanced_layout.setContentsMargins(8, 6, 8, 6)
        advanced_layout.addLayout(controls)
        self.advanced_panel.setVisible(False)
        root.insertWidget(2, self.advanced_panel)

        tabs = QTabWidget(self)
        tabs.setObjectName("comparisonResultTabs")
        self.dashboard = ComparisonVisualizationWidget(
            self.comparison_set.name,
            tabs,
        )
        self.dashboard.evidence_requested.connect(self._prepare_evidence)
        tabs.addTab(self.dashboard, "Przegląd graficzny")

        data_page = QWidget(tabs)
        data_page.setObjectName("comparisonArtifactDataPage")
        data_layout = QVBoxLayout(data_page)
        data_layout.setContentsMargins(8, 8, 8, 8)
        data_layout.setSpacing(8)

        artifact_row = _take_layout_containing_widget(root, self.artifact_combo)
        if artifact_row is not None:
            data_layout.addLayout(artifact_row)
        root.removeWidget(self.artifact_info)
        root.removeWidget(self.summary_label)
        root.removeWidget(splitter)
        data_layout.addWidget(self.artifact_info)
        data_layout.addWidget(self.summary_label)
        data_layout.addWidget(splitter, 1)
        tabs.addTab(data_page, "Dane artefaktu")

        root.insertWidget(root.count() - 1, tabs, 1)
        self.result_tabs = tabs
        self.progress.setVisible(False)
        self._apply_visual_style()
        self._refresh_dashboard()

    def _apply_visual_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog#comparisonVisualizationDialog {
                background: #0f1419;
                color: #dce6ef;
            }
            QLabel#comparisonAnalysisTitle {
                font-size: 18px;
                font-weight: 700;
                color: #f2f7fb;
                padding: 3px 0 5px 0;
            }
            QPushButton#runAllComparisonAnalyses {
                min-height: 30px;
                padding: 0 16px;
                border: 1px solid #2e8cff;
                border-radius: 5px;
                background: #1565c0;
                color: white;
                font-weight: 700;
            }
            QPushButton#runAllComparisonAnalyses:hover {
                background: #1976d2;
            }
            QPushButton#comparisonAdvancedToggle {
                min-height: 30px;
                padding: 0 12px;
            }
            QWidget#comparisonAdvancedPanel {
                background: #151d25;
                border: 1px solid #2a3743;
                border-radius: 5px;
            }
            QTabWidget#comparisonResultTabs::pane {
                border: 1px solid #26333f;
                border-radius: 6px;
                background: #111820;
                top: -1px;
            }
            QTabWidget#comparisonResultTabs QTabBar::tab {
                min-height: 30px;
                padding: 0 16px;
            }
            """
        )

    def _load_artifacts(self, preferred_artifact_id: str = "") -> None:
        super()._load_artifacts(preferred_artifact_id)
        if self.dashboard is not None:
            self._refresh_dashboard()

    def _toggle_advanced(self, checked: bool) -> None:
        self.advanced_panel.setVisible(checked)
        self.advanced_button.setText(
            "Zaawansowane ▾" if checked else "Zaawansowane ▸"
        )

    def _prepare_evidence(self, session_id: str, message_key: str) -> None:
        self.pending_evidence = (session_id, message_key)
        self.accept()

    def _start_all_analyses(self) -> None:
        if self._task is not None:
            return
        provider_ids = [
            str(self.provider_combo.itemData(index) or "")
            for index in range(self.provider_combo.count())
        ]
        self._batch_provider_ids = [value for value in provider_ids if value]
        if not self._batch_provider_ids:
            return
        self._batch_total = len(self._batch_provider_ids)
        self._batch_completed = 0
        self._start_next_batch_analysis()

    def _start_next_batch_analysis(self) -> None:
        if not self._batch_provider_ids:
            self.status_label.setText(
                f"Komplet analiz zakończony: {self._batch_completed}/{self._batch_total}."
            )
            self._batch_total = 0
            self._batch_completed = 0
            self.run_all_button.setEnabled(self.provider_combo.count() > 0)
            self._refresh_dashboard()
            return
        provider_id = self._batch_provider_ids.pop(0)
        index = self.provider_combo.findData(provider_id)
        if index < 0:
            self._start_next_batch_analysis()
            return
        step = self._batch_completed + 1
        self.provider_combo.setCurrentIndex(index)
        self.status_label.setText(
            f"Komplet analiz: etap {step}/{self._batch_total} — {provider_id}"
        )
        super()._start_analysis()

    def _analysis_done(self, value: object) -> None:
        batch_active = self._batch_total > 0
        super()._analysis_done(value)
        if not batch_active:
            return
        self._batch_completed += 1
        QTimer.singleShot(0, self._start_next_batch_analysis)

    def _analysis_failed(self, error: str) -> None:
        self._clear_batch()
        super()._analysis_failed(error)

    def _analysis_cancelled(self) -> None:
        self._clear_batch()
        super()._analysis_cancelled()

    def _cancel_analysis(self) -> None:
        self._batch_provider_ids.clear()
        super()._cancel_analysis()

    def _set_running(self, running: bool) -> None:
        super()._set_running(running)
        self.progress.setVisible(running)
        if hasattr(self, "run_all_button"):
            self.run_all_button.setEnabled(
                not running
                and self._batch_total == 0
                and self.provider_combo.count() > 0
            )
        if hasattr(self, "advanced_button"):
            self.advanced_button.setEnabled(not running)

    def _clear_batch(self) -> None:
        self._batch_provider_ids.clear()
        self._batch_total = 0
        self._batch_completed = 0

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


def _take_layout_containing_widget(
    root: QLayout,
    widget: QWidget,
) -> QLayout | None:
    for index in range(root.count()):
        child = root.itemAt(index)
        layout = child.layout()
        if layout is not None and layout.indexOf(widget) >= 0:
            root.removeItem(layout)
            return layout
    return None


__all__ = [
    "ComparisonDashboardData",
    "ComparisonVisualizationDialog",
    "ComparisonVisualizationWidget",
    "ComparisonVisualRow",
    "build_dashboard_data",
]
