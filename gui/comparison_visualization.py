from __future__ import annotations

from collections.abc import Callable
from threading import Event
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.artifact_catalog import ArtifactIntegrityError
from app.extensions import ExtensionCancelled

from .comparison_analysis_dialog import ComparisonAnalysisDialog
from .comparison_interframe_timing_view import ComparisonInterFrameTimingView
from .comparison_timeline_view import ComparisonTimelineView
from .comparison_uds_latency_view import ComparisonUdsLatencyView
from .comparison_uds_transaction_explorer_view import (
    ComparisonUdsTransactionExplorerView,
)
from .comparison_visualization_dashboard import ComparisonVisualizationWidget
from .comparison_visualization_model import (
    SCHEMA_PAYLOAD,
    SCHEMA_SEQUENCE,
    SCHEMA_STATISTICS,
    ComparisonDashboardData,
    ComparisonVisualRow,
    build_dashboard_data,
)
from .experiment_diff_view import ExperimentDiffView
from .signal_candidates_view import SignalCandidatesView

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
_MAXIMUM_DASHBOARD_ARTIFACT_BYTES = 256 * 1024 * 1024


class _DashboardSignals(QObject):
    completed = Signal(int, object, object)
    failed = Signal(int, str)
    finished = Signal(int)


class _DashboardLoadTask(QRunnable):
    def __init__(
        self,
        generation: int,
        comparison_name: str,
        catalog,
        artifacts: tuple,
        cancel_event: Event,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.generation = generation
        self.comparison_name = comparison_name
        self.catalog = catalog
        self.artifacts = artifacts
        self.cancel_event = cancel_event
        self.signals = _DashboardSignals()

    @Slot()
    def run(self) -> None:
        try:
            payloads: dict[str, dict[str, Any]] = {}
            errors: list[str] = []
            for artifact in self.artifacts:
                if self.cancel_event.is_set():
                    raise ExtensionCancelled("dashboard loading cancelled")
                try:
                    payload = self.catalog.read_json(
                        artifact,
                        maximum_bytes=_MAXIMUM_DASHBOARD_ARTIFACT_BYTES,
                    )
                except (ArtifactIntegrityError, OSError, ValueError) as exc:
                    errors.append(f"{artifact.artifact_type}: {exc}")
                    continue
                if not isinstance(payload, dict):
                    errors.append(
                        f"{artifact.artifact_type}: korzeń JSON nie jest obiektem"
                    )
                    continue
                schema = str(payload.get("schema") or "")
                if schema not in _SUPPORTED_SCHEMAS:
                    errors.append(
                        f"{artifact.artifact_type}: "
                        f"nieobsługiwany schemat {schema or 'brak'}"
                    )
                    continue
                payloads[schema] = payload
            if self.cancel_event.is_set():
                raise ExtensionCancelled("dashboard loading cancelled")
            data = build_dashboard_data(self.comparison_name, payloads)
            if not self.cancel_event.is_set():
                self.signals.completed.emit(self.generation, data, errors)
        except ExtensionCancelled:
            return
        except Exception as exc:  # pragma: no cover - surfaced through GUI
            if not self.cancel_event.is_set():
                self.signals.failed.emit(self.generation, str(exc))
        finally:
            self.signals.finished.emit(self.generation)


class ComparisonVisualizationDialog(ComparisonAnalysisDialog):
    """Passive comparison workspace: dashboard, timing, UDS and signal analyses.

    Every analysis tab is a self-contained view. The dialog only places them,
    routes their ``source_row_requested`` signal to evidence navigation and
    cancels their background work when it closes.
    """

    evidence_open_requested = Signal(str, str, object)
    source_row_open_requested = Signal(str, int, str, object)

    def __init__(
        self,
        project,
        comparison_set_id: str,
        parent: QWidget | None = None,
    ) -> None:
        self.dashboard: ComparisonVisualizationWidget | None = None
        self.pending_evidence: tuple[str, str] | None = None
        self._evidence_pending = False
        self._evidence_views: list[QWidget] = []
        self._batch_provider_ids: list[str] = []
        self._batch_total = 0
        self._batch_completed = 0
        self._dashboard_generation = 0
        self._dashboard_tasks: dict[int, _DashboardLoadTask] = {}
        self._close_when_idle = False
        super().__init__(project, comparison_set_id, parent)
        self.setObjectName("comparisonVisualizationDialog")
        self.setWindowTitle(f"Porównanie logów — {self.comparison_set.name}")
        self.resize(1480, 920)
        self.setMinimumSize(1180, 720)
        self.progress.setVisible(False)
        self._apply_visual_style()

    # ----------------------------------------------------------------- layout

    def _build_layout(self) -> None:
        self.title_label.setText(f"Porównanie logów · {self.comparison_set.name}")
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

        self.advanced_panel = QWidget(self)
        self.advanced_panel.setObjectName("comparisonAdvancedPanel")
        advanced_layout = QVBoxLayout(self.advanced_panel)
        advanced_layout.setContentsMargins(8, 6, 8, 6)
        advanced_layout.addLayout(self._provider_row(include_secondary_buttons=False))
        self.advanced_panel.setVisible(False)

        self.result_tabs = self._build_result_tabs()

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)
        root.addWidget(self.title_label)
        root.addLayout(actions)
        root.addWidget(self.advanced_panel)
        root.addWidget(self.progress)
        root.addWidget(self.status_label)
        root.addWidget(self.result_tabs, 1)
        root.addWidget(self.buttons)

    def _build_result_tabs(self) -> QTabWidget:
        tabs = QTabWidget(self)
        tabs.setObjectName("comparisonResultTabs")

        self.dashboard = ComparisonVisualizationWidget(self.comparison_set.name, tabs)
        self.dashboard.evidence_requested.connect(self._prepare_evidence)
        tabs.addTab(self.dashboard, "Przegląd graficzny")

        self.timeline = self._add_evidence_view(
            tabs,
            ComparisonTimelineView,
            "Oś czasu",
            "z osi czasu",
        )
        self.timing = self._add_evidence_view(
            tabs,
            ComparisonInterFrameTimingView,
            "Timing i jitter",
            "z dowodu timingowego",
        )
        self.uds_latency = self._add_evidence_view(
            tabs,
            ComparisonUdsLatencyView,
            "Latencja UDS",
            "z transakcji UDS",
        )
        self.uds_explorer = self._add_evidence_view(
            tabs,
            ComparisonUdsTransactionExplorerView,
            "Transakcje UDS",
            "z eksploratora UDS",
        )
        self.experiment_diff = self._add_evidence_view(
            tabs,
            ExperimentDiffView,
            "Experiment Diff",
            "z Experiment Diff",
        )
        self.experiment_diff.output_message.connect(self.output_message.emit)
        self.signal_candidates = self._add_evidence_view(
            tabs,
            SignalCandidatesView,
            "Signal Candidates",
            "z Signal Candidates",
        )
        self.signal_candidates.output_message.connect(self.output_message.emit)

        data_page = QWidget(tabs)
        data_page.setObjectName("comparisonArtifactDataPage")
        data_layout = QVBoxLayout(data_page)
        data_layout.setContentsMargins(8, 8, 8, 8)
        data_layout.setSpacing(8)
        data_layout.addLayout(self._artifact_row())
        data_layout.addWidget(self.artifact_info)
        data_layout.addWidget(self.summary_label)
        data_layout.addWidget(self.results_splitter, 1)
        tabs.addTab(data_page, "Dane artefaktu")
        return tabs

    def _add_evidence_view(
        self,
        tabs: QTabWidget,
        factory: Callable[..., QWidget],
        title: str,
        origin: str,
    ):
        view = factory(self.project, self.comparison_set, tabs)
        view.source_row_requested.connect(
            lambda session_id, source_row, message_key, origin=origin: (
                self._request_source_row(origin, session_id, source_row, message_key)
            )
        )
        tabs.addTab(view, title)
        self._evidence_views.append(view)
        return view

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

    def _toggle_advanced(self, checked: bool) -> None:
        self.advanced_panel.setVisible(checked)
        self.advanced_button.setText(
            "Zaawansowane ▾" if checked else "Zaawansowane ▸"
        )

    # --------------------------------------------------------------- evidence

    def _prepare_evidence(self, session_id: str, message_key: str) -> None:
        if self._evidence_pending:
            return
        self.pending_evidence = (session_id, message_key)
        self._evidence_pending = True
        self._set_evidence_running(True)
        self.status_label.setText(
            f"Szukam dowodów dla {message_key}. Okno porównania pozostaje otwarte."
        )
        self.evidence_open_requested.emit(session_id, message_key, self)

    def _request_source_row(
        self,
        origin: str,
        session_id: str,
        source_row: int,
        message_key: str,
    ) -> None:
        if self._evidence_pending:
            return
        self.pending_evidence = (session_id, message_key)
        self._evidence_pending = True
        self._set_evidence_running(True)
        self.status_label.setText(
            f"Otwieram ramkę {source_row + 1} {origin}. "
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
        if not self._evidence_pending:
            return
        self.pending_evidence = None
        self._evidence_pending = False
        self._set_evidence_running(False)
        self.status_label.setText(
            "Dowód został otwarty w zapisanej sesji. "
            "Okno porównania pozostaje dostępne."
        )

    @Slot(str)
    def evidence_navigation_failed(self, error: str) -> None:
        self.pending_evidence = None
        self._evidence_pending = False
        self._set_evidence_running(False)
        self.status_label.setText(f"Nie udało się otworzyć dowodów: {error}")

    def _set_evidence_running(self, running: bool) -> None:
        if self.dashboard is not None:
            self.dashboard.setEnabled(not running)
        for view in self._evidence_views:
            view.setEnabled(not running)
        idle = not running and self._task is None
        has_providers = self.provider_combo.count() > 0
        self.run_all_button.setEnabled(idle and has_providers)
        self.advanced_button.setEnabled(idle)
        self.refresh_button.setEnabled(idle)
        self.run_button.setEnabled(idle and has_providers)

    # --------------------------------------------------------------- analyses

    def _start_all_analyses(self) -> None:
        if self._task is not None or self._evidence_pending:
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
        self._start_analysis()

    def _analysis_done(self, value: object) -> None:
        batch_active = self._batch_total > 0
        super()._analysis_done(value)
        if batch_active:
            self._batch_completed += 1
            QTimer.singleShot(0, self._start_next_batch_analysis)
        self._close_if_requested()

    def _analysis_failed(self, error: str) -> None:
        self._clear_batch()
        super()._analysis_failed(error)
        self._close_if_requested()

    def _analysis_cancelled(self) -> None:
        self._clear_batch()
        super()._analysis_cancelled()
        self._close_if_requested()

    def _cancel_analysis(self) -> None:
        self._batch_provider_ids.clear()
        super()._cancel_analysis()

    def _set_running(self, running: bool) -> None:
        super()._set_running(running)
        self.progress.setVisible(running)
        self.run_all_button.setEnabled(
            not running
            and not self._evidence_pending
            and self._batch_total == 0
            and self.provider_combo.count() > 0
        )
        self.advanced_button.setEnabled(not running and not self._evidence_pending)

    def _clear_batch(self) -> None:
        self._batch_provider_ids.clear()
        self._batch_total = 0
        self._batch_completed = 0

    # -------------------------------------------------------------- dashboard

    def _load_artifacts(self, preferred_artifact_id: str = "") -> None:
        super()._load_artifacts(preferred_artifact_id)
        self._refresh_dashboard()

    def _refresh_dashboard(self) -> None:
        if self.dashboard is None:
            return
        self._dashboard_generation += 1
        generation = self._dashboard_generation
        for task in self._dashboard_tasks.values():
            task.cancel_event.set()

        latest: dict[str, Any] = {}
        for artifact in self._artifacts:
            if artifact.artifact_type not in _ARTIFACT_TYPES:
                continue
            current = latest.get(artifact.artifact_type)
            if current is None or artifact.created_at_utc > current.created_at_utc:
                latest[artifact.artifact_type] = artifact

        if not latest:
            self.dashboard.clear()
            return

        cancel_event = Event()
        task = _DashboardLoadTask(
            generation,
            self.comparison_set.name,
            self.service.artifacts,
            tuple(latest.values()),
            cancel_event,
        )
        task.signals.completed.connect(self._dashboard_ready)
        task.signals.failed.connect(self._dashboard_failed)
        task.signals.finished.connect(self._dashboard_finished)
        self._dashboard_tasks[generation] = task
        QThreadPool.globalInstance().start(task)

    @Slot(int, object, object)
    def _dashboard_ready(
        self,
        generation: int,
        value: object,
        errors_value: object,
    ) -> None:
        if generation != self._dashboard_generation:
            return
        if not isinstance(value, ComparisonDashboardData):
            self._dashboard_failed(
                generation,
                "Nie udało się zbudować modelu dashboardu.",
            )
            return
        dashboard = self.dashboard
        if dashboard is None:
            return

        dashboard.set_data(value)
        errors = (
            [str(item) for item in errors_value if str(item)]
            if isinstance(errors_value, list)
            else []
        )
        if errors:
            self.status_label.setText(
                "Nie udało się odczytać części artefaktów porównania: "
                + "; ".join(errors)
            )
        elif not value.artifact_schemas:
            dashboard.clear()

    @Slot(int, str)
    def _dashboard_failed(self, generation: int, error: str) -> None:
        if generation != self._dashboard_generation:
            return
        if self.dashboard is not None:
            self.dashboard.clear()
        self.status_label.setText(
            f"Nie udało się odświeżyć dashboardu porównania: {error}"
        )

    @Slot(int)
    def _dashboard_finished(self, generation: int) -> None:
        self._dashboard_tasks.pop(generation, None)

    def _cancel_dashboard_loads(self) -> None:
        self._dashboard_generation += 1
        for task in self._dashboard_tasks.values():
            task.cancel_event.set()

    # ------------------------------------------------------------------ close

    def _cancel_background_work(self) -> None:
        for view in self._evidence_views:
            view.cancel_all()
        self._cancel_dashboard_loads()

    def close_for_project_change(self) -> None:
        self._close_when_idle = True
        self._cancel_background_work()
        if self._task is not None:
            self._cancel_analysis()
            self.hide()
            return
        self.close()

    def _close_if_requested(self) -> None:
        if self._close_when_idle and self._task is None:
            self.close()

    def closeEvent(self, event) -> None:
        self._cancel_background_work()
        super().closeEvent(event)


__all__ = [
    "ComparisonDashboardData",
    "ComparisonVisualizationDialog",
    "ComparisonVisualizationWidget",
    "ComparisonVisualRow",
    "build_dashboard_data",
]
