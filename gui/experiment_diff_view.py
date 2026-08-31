from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.comparison_analysis_service import ComparisonAnalysisExecutionResult
from app.experiment_diff_service import ExperimentDiffService
from app.extensions import CancellationToken, ExtensionCancelled, ProgressUpdate
from app.project import CrtProject


_HEADERS = (
    "Score",
    "CAN ID",
    "Ch",
    "Format",
    "Byte",
    "Bit",
    "Target",
    "Control",
    "Kierunek",
    "Spójność",
    "Śr. delay [ms]",
    "Mediana [ms]",
)


class _Signals(QObject):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class _Task(QRunnable):
    def __init__(
        self,
        service: ExperimentDiffService,
        comparison_set_id: str,
        *,
        target_selector: str,
        control_selector: str | None,
        pre_window_ms: float,
        post_window_ms: float,
    ) -> None:
        super().__init__()
        self.service = service
        self.comparison_set_id = comparison_set_id
        self.target_selector = target_selector
        self.control_selector = control_selector
        self.pre_window_ms = pre_window_ms
        self.post_window_ms = post_window_ms
        self.cancellation = CancellationToken()
        self.signals = _Signals()

    def cancel(self) -> None:
        self.cancellation.cancel()

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.run(
                self.comparison_set_id,
                target_selector=self.target_selector,
                control_selector=self.control_selector,
                pre_window_ms=self.pre_window_ms,
                post_window_ms=self.post_window_ms,
                cancellation=self.cancellation,
                progress_callback=self._progress,
            )
        except ExtensionCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        else:
            self.signals.completed.emit(result)

    def _progress(self, update: ProgressUpdate) -> None:
        self.signals.progress.emit(update.current, update.total, update.message)


class ExperimentDiffView(QWidget):
    """Passive marker-correlated bit-diff workspace for a comparison set."""

    source_row_requested = Signal(str, int, str)
    output_message = Signal(str)

    def __init__(
        self,
        project: CrtProject,
        comparison_set: object,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("experimentDiffWorkspace")
        self.project = project
        self.comparison_set = comparison_set
        self.comparison_set_id = str(getattr(comparison_set, "id", ""))
        self.service = ExperimentDiffService(project)
        self._task: _Task | None = None
        self._candidates: list[dict[str, Any]] = []
        self._evidence: list[dict[str, Any]] = []
        self._build_ui()
        self.refresh_markers()
        self._load_artifacts()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        intro = QLabel(
            "Deterministyczna korelacja bitów ze znacznikami eksperymentu. "
            "Dla każdego zdarzenia CRT bierze ostatni stan przed markerem i pierwszą "
            "zmianę po markerze; wynik zachowuje exact source_row obu ramek.",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        marker_row = QHBoxLayout()
        marker_row.addWidget(QLabel("Marker testowy:", self))
        self.target_combo = QComboBox(self)
        self.target_combo.setObjectName("experimentDiffTargetMarker")
        self.target_combo.setMinimumWidth(280)
        marker_row.addWidget(self.target_combo, 1)

        marker_row.addWidget(QLabel("Marker kontrolny:", self))
        self.control_combo = QComboBox(self)
        self.control_combo.setObjectName("experimentDiffControlMarker")
        self.control_combo.setMinimumWidth(260)
        marker_row.addWidget(self.control_combo, 1)

        self.refresh_markers_button = QPushButton("Odśwież markery", self)
        self.refresh_markers_button.setObjectName("experimentDiffRefreshMarkers")
        self.refresh_markers_button.clicked.connect(self.refresh_markers)
        marker_row.addWidget(self.refresh_markers_button)
        root.addLayout(marker_row)

        window_row = QHBoxLayout()
        window_row.addWidget(QLabel("Okno przed [ms]:", self))
        self.pre_spin = QDoubleSpinBox(self)
        self.pre_spin.setObjectName("experimentDiffPreWindow")
        self.pre_spin.setDecimals(1)
        self.pre_spin.setRange(0.1, 60_000.0)
        self.pre_spin.setValue(250.0)
        window_row.addWidget(self.pre_spin)

        window_row.addWidget(QLabel("Okno po [ms]:", self))
        self.post_spin = QDoubleSpinBox(self)
        self.post_spin.setObjectName("experimentDiffPostWindow")
        self.post_spin.setDecimals(1)
        self.post_spin.setRange(0.1, 60_000.0)
        self.post_spin.setValue(500.0)
        window_row.addWidget(self.post_spin)

        self.run_button = QPushButton("Koreluj z markerem", self)
        self.run_button.setObjectName("runExperimentDiff")
        self.run_button.clicked.connect(self._start)
        window_row.addWidget(self.run_button)
        self.cancel_button = QPushButton("Anuluj", self)
        self.cancel_button.setObjectName("cancelExperimentDiff")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.setEnabled(False)
        window_row.addWidget(self.cancel_button)
        window_row.addStretch(1)
        root.addLayout(window_row)

        self.progress = QProgressBar(self)
        self.progress.setObjectName("experimentDiffProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Oczekiwanie")
        root.addWidget(self.progress)

        self.status_label = QLabel("Gotowe.", self)
        self.status_label.setObjectName("experimentDiffStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.status_label)

        artifact_row = QHBoxLayout()
        artifact_row.addWidget(QLabel("Zapisany wynik:", self))
        self.artifact_combo = QComboBox(self)
        self.artifact_combo.setObjectName("experimentDiffArtifactSelector")
        self.artifact_combo.currentIndexChanged.connect(self._show_selected_artifact)
        artifact_row.addWidget(self.artifact_combo, 1)
        self.refresh_artifacts_button = QPushButton("Odśwież wyniki", self)
        self.refresh_artifacts_button.clicked.connect(self._load_artifacts)
        artifact_row.addWidget(self.refresh_artifacts_button)
        root.addLayout(artifact_row)

        self.summary_label = QLabel("Brak wyniku Experiment Diff.", self)
        self.summary_label.setObjectName("experimentDiffSummary")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        self.table = QTableWidget(0, len(_HEADERS), self)
        self.table.setObjectName("experimentDiffCandidates")
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._candidate_selected)
        root.addWidget(self.table, 1)

        evidence_row = QHBoxLayout()
        evidence_row.addWidget(QLabel("Dowód:", self))
        self.evidence_combo = QComboBox(self)
        self.evidence_combo.setObjectName("experimentDiffEvidenceSelector")
        self.evidence_combo.currentIndexChanged.connect(self._evidence_selected)
        evidence_row.addWidget(self.evidence_combo, 1)
        self.open_before_button = QPushButton("Otwórz stan PRZED", self)
        self.open_before_button.setObjectName("experimentDiffOpenBefore")
        self.open_before_button.clicked.connect(lambda: self._open_evidence("before"))
        evidence_row.addWidget(self.open_before_button)
        self.open_after_button = QPushButton("Otwórz pierwszą ZMIANĘ", self)
        self.open_after_button.setObjectName("experimentDiffOpenAfter")
        self.open_after_button.clicked.connect(lambda: self._open_evidence("after"))
        evidence_row.addWidget(self.open_after_button)
        root.addLayout(evidence_row)

        self.evidence_label = QLabel("Wybierz kandydata, aby zobaczyć powtórzenia eksperymentu.", self)
        self.evidence_label.setObjectName("experimentDiffEvidenceSummary")
        self.evidence_label.setWordWrap(True)
        root.addWidget(self.evidence_label)
        self._refresh_evidence_buttons()

    @Slot()
    def refresh_markers(self) -> None:
        current_target = str(self.target_combo.currentData() or "")
        current_control = str(self.control_combo.currentData() or "")
        try:
            options = self.service.marker_options(self.comparison_set_id)
        except Exception as exc:
            options = ()
            self.status_label.setText(f"Nie można odczytać markerów: {exc}")
        self.target_combo.clear()
        self.control_combo.clear()
        self.control_combo.addItem("— brak kontroli —", "")
        target_index = -1
        control_index = 0
        for option in options:
            self.target_combo.addItem(option.label, option.selector)
            self.control_combo.addItem(option.label, option.selector)
            if option.selector == current_target:
                target_index = self.target_combo.count() - 1
            if option.selector == current_control:
                control_index = self.control_combo.count() - 1
        if self.target_combo.count():
            self.target_combo.setCurrentIndex(target_index if target_index >= 0 else 0)
        self.control_combo.setCurrentIndex(control_index)
        available = self.target_combo.count() > 0
        self.run_button.setEnabled(available and self._task is None)
        if available:
            self.status_label.setText(
                f"Markery dostępne: {len(options)} typów. Analiza pozostaje całkowicie pasywna."
            )
        else:
            self.status_label.setText(
                "Brak markerów w sesjach tego zestawu. Experiment Diff wymaga co najmniej jednego markera testowego."
            )

    @Slot()
    def _start(self) -> None:
        if self._task is not None:
            return
        target = str(self.target_combo.currentData() or "")
        control = str(self.control_combo.currentData() or "") or None
        if not target:
            return
        if control == target:
            self.status_label.setText("Marker kontrolny musi być inny niż marker testowy.")
            return
        task = _Task(
            self.service,
            self.comparison_set_id,
            target_selector=target,
            control_selector=control,
            pre_window_ms=self.pre_spin.value(),
            post_window_ms=self.post_spin.value(),
        )
        task.signals.progress.connect(self._progress)
        task.signals.completed.connect(self._completed)
        task.signals.failed.connect(self._failed)
        task.signals.cancelled.connect(self._cancelled)
        self._task = task
        self._set_running(True)
        self.progress.setRange(0, 0)
        self.progress.setFormat("Uruchamianie…")
        self.status_label.setText("Koreluję markery z ramkami w tle…")
        QThreadPool.globalInstance().start(task)

    @Slot()
    def _cancel(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Anulowanie Experiment Diff…")

    @Slot(int, int, str)
    def _progress(self, current: int, total: int, message: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
            self.progress.setFormat(f"{current:,}/{total:,}".replace(",", " "))
        else:
            self.progress.setRange(0, 0)
        self.status_label.setText(message or "Analiza w toku…")

    @Slot(object)
    def _completed(self, value: object) -> None:
        result = value if isinstance(value, ComparisonAnalysisExecutionResult) else None
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("Gotowe — 100%")
        if result is None or not result.artifacts:
            self._failed("provider nie zwrócił artefaktu")
            return
        self.status_label.setText("Experiment Diff zakończony. Artefakt i exact evidence zapisano w projekcie.")
        self.output_message.emit(
            f"Experiment Diff zakończony: {len(result.artifacts)} artefakt(ów)"
        )
        self._load_artifacts(result.artifacts[0].id)

    @Slot(str)
    def _failed(self, error: str) -> None:
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Błąd")
        self.status_label.setText(f"Experiment Diff: {error}")

    @Slot()
    def _cancelled(self) -> None:
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Anulowano")
        self.status_label.setText("Analiza anulowana; sesje źródłowe pozostały niezmienione.")

    def _set_running(self, running: bool) -> None:
        if not running:
            self._task = None
        available = self.target_combo.count() > 0
        for widget in (
            self.target_combo,
            self.control_combo,
            self.pre_spin,
            self.post_spin,
            self.refresh_markers_button,
            self.refresh_artifacts_button,
        ):
            widget.setEnabled(not running)
        self.run_button.setEnabled(available and not running)
        self.cancel_button.setEnabled(running)

    @Slot()
    @Slot(str)
    def _load_artifacts(self, preferred_artifact_id: str = "") -> None:
        current = preferred_artifact_id or str(self.artifact_combo.currentData() or "")
        try:
            artifacts = self.service.list_artifacts(self.comparison_set_id)
        except Exception as exc:
            artifacts = ()
            self.status_label.setText(f"Nie można odczytać artefaktów Experiment Diff: {exc}")
        self.artifact_combo.blockSignals(True)
        self.artifact_combo.clear()
        selected = -1
        for index, artifact in enumerate(artifacts):
            self.artifact_combo.addItem(
                f"{artifact.created_at_utc or 'bez daty'} — {artifact.provider_version} — {artifact.sha256[:12] if artifact.sha256 else 'bez SHA'}",
                artifact.id,
            )
            if artifact.id == current:
                selected = index
        if artifacts:
            self.artifact_combo.setCurrentIndex(selected if selected >= 0 else 0)
        self.artifact_combo.blockSignals(False)
        self.artifact_combo.setEnabled(bool(artifacts))
        self._show_selected_artifact()

    @Slot()
    @Slot(int)
    def _show_selected_artifact(self, _index: int = -1) -> None:
        artifact_id = str(self.artifact_combo.currentData() or "")
        artifact = next(
            (item for item in self.service.list_artifacts(self.comparison_set_id) if item.id == artifact_id),
            None,
        )
        if artifact is None:
            self._render({})
            return
        try:
            payload = self.service.analysis.artifacts.read_json(artifact)
        except Exception as exc:
            self.status_label.setText(f"Nie można odczytać artefaktu: {exc}")
            return
        self._render(payload if isinstance(payload, dict) else {})

    def _render(self, payload: Mapping[str, Any]) -> None:
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        selection = payload.get("marker_selection") if isinstance(payload.get("marker_selection"), dict) else {}
        target = selection.get("target") if isinstance(selection.get("target"), dict) else {}
        control = selection.get("control") if isinstance(selection.get("control"), dict) else {}
        if payload:
            self.summary_label.setText(
                f"Target: {target.get('label', target.get('name', '—'))} — {selection.get('target_event_count', 0)} zdarzeń. "
                f"Control: {control.get('label', control.get('name', 'brak')) if control else 'brak'} — {selection.get('control_event_count', 0)} zdarzeń. "
                f"Okno: -{selection.get('pre_window_ms', '—')} / +{selection.get('post_window_ms', '—')} ms. "
                f"Kandydaci: {summary.get('candidate_count', 0)}."
            )
        else:
            self.summary_label.setText("Brak zapisanego wyniku Experiment Diff.")

        rows = payload.get("ranked_candidates") if isinstance(payload.get("ranked_candidates"), list) else []
        self._candidates = [item for item in rows if isinstance(item, dict)]
        self.table.setRowCount(len(self._candidates))
        for row, candidate in enumerate(self._candidates):
            target_stats = candidate.get("target") if isinstance(candidate.get("target"), dict) else {}
            control_stats = candidate.get("control") if isinstance(candidate.get("control"), dict) else {}
            direction = candidate.get("direction") if isinstance(candidate.get("direction"), dict) else {}
            timing = candidate.get("timing") if isinstance(candidate.get("timing"), dict) else {}
            values = (
                f"{float(candidate.get('score', 0.0)):.3f}",
                candidate.get("arbitration_id_hex", "—"),
                candidate.get("channel", "—"),
                "EXT" if candidate.get("is_extended_id") else "STD",
                candidate.get("byte_index", "—"),
                candidate.get("bit_index", "—"),
                _ratio(target_stats.get("changed_event_count"), target_stats.get("eligible_event_count")),
                _ratio(control_stats.get("changed_event_count"), control_stats.get("eligible_event_count")),
                direction.get("dominant", "—"),
                _percent(direction.get("consistency_ratio")),
                _ms(timing.get("mean_delay_ns")),
                _ms(timing.get("median_delay_ns")),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in {0, 2, 4, 5, 9, 10, 11}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, item)
        if self._candidates:
            self.table.selectRow(0)
        else:
            self.evidence_combo.clear()
            self._evidence = []
            self.evidence_label.setText("Brak bitów zmieniających się po wybranym markerze w zadanym oknie.")
            self._refresh_evidence_buttons()

    @Slot()
    def _candidate_selected(self) -> None:
        row = self.table.currentRow()
        candidate = self._candidates[row] if 0 <= row < len(self._candidates) else None
        self.evidence_combo.blockSignals(True)
        self.evidence_combo.clear()
        self._evidence = []
        if candidate is not None:
            evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), list) else []
            self._evidence = [item for item in evidence if isinstance(item, dict)]
            for index, item in enumerate(self._evidence):
                marker = item.get("marker") if isinstance(item.get("marker"), dict) else {}
                delay = item.get("delay_ns")
                group = "TEST" if item.get("group") == "target" else "CTRL"
                self.evidence_combo.addItem(
                    f"{group} | {item.get('session_name', item.get('session_id', '—'))} | "
                    f"{marker.get('name', 'marker')} | Δt={_ms(delay)} ms",
                    index,
                )
        self.evidence_combo.blockSignals(False)
        if self._evidence:
            self.evidence_combo.setCurrentIndex(0)
        self._evidence_selected()

    @Slot()
    @Slot(int)
    def _evidence_selected(self, _index: int = -1) -> None:
        evidence = self._selected_evidence()
        if evidence is None:
            self.evidence_label.setText("Brak zachowanego dowodu dla wybranego kandydata.")
            self._refresh_evidence_buttons()
            return
        before = evidence.get("before") if isinstance(evidence.get("before"), dict) else {}
        after = evidence.get("after") if isinstance(evidence.get("after"), dict) else {}
        self.evidence_label.setText(
            f"session={evidence.get('session_name', evidence.get('session_id', '—'))} | "
            f"stan {evidence.get('before_state')}→{evidence.get('after_state')} | "
            f"before source_row={before.get('source_row', '—')} | "
            f"after source_row={after.get('source_row', '—')} | "
            f"delay={_ms(evidence.get('delay_ns'))} ms"
        )
        self._refresh_evidence_buttons()

    def _selected_evidence(self) -> dict[str, Any] | None:
        index = self.evidence_combo.currentIndex()
        return self._evidence[index] if 0 <= index < len(self._evidence) else None

    def _open_evidence(self, which: str) -> None:
        evidence = self._selected_evidence()
        row = self.table.currentRow()
        candidate = self._candidates[row] if 0 <= row < len(self._candidates) else None
        if evidence is None or candidate is None:
            return
        reference = evidence.get(which) if isinstance(evidence.get(which), dict) else {}
        source_row = reference.get("source_row")
        session_id = evidence.get("session_id")
        if isinstance(source_row, int) and isinstance(session_id, str) and session_id:
            self.source_row_requested.emit(
                session_id,
                source_row,
                str(candidate.get("message_key", "")),
            )

    def _refresh_evidence_buttons(self) -> None:
        evidence = self._selected_evidence()
        self.open_before_button.setEnabled(
            bool(evidence and isinstance(evidence.get("before"), dict) and isinstance(evidence["before"].get("source_row"), int))
        )
        self.open_after_button.setEnabled(
            bool(evidence and isinstance(evidence.get("after"), dict) and isinstance(evidence["after"].get("source_row"), int))
        )

    def cancel_all(self) -> None:
        if self._task is not None:
            self._task.cancel()


def _ratio(numerator: object, denominator: object) -> str:
    try:
        return f"{int(numerator)}/{int(denominator)}"
    except (TypeError, ValueError):
        return "—"


def _percent(value: object) -> str:
    return f"{float(value) * 100.0:.1f}%" if isinstance(value, (int, float)) else "—"


def _ms(value: object) -> str:
    return f"{float(value) / 1_000_000.0:.3f}" if isinstance(value, (int, float)) else "—"


__all__ = ["ExperimentDiffView"]
