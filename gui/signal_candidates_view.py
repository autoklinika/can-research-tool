from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
from app.extensions import CancellationToken, ExtensionCancelled, ProgressUpdate
from app.project import CrtProject
from app.signal_candidate_service import SignalCandidateService


_HEADERS = (
    "#",
    "Klasa",
    "Score",
    "CAN ID",
    "Ch",
    "Format",
    "Byte",
    "Bit",
    "Najlepszy eksperyment",
    "Target",
    "Control",
    "Kierunek",
    "Śr. delay [ms]",
    "Signal Discovery",
)


class _Signals(QObject):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class _Task(QRunnable):
    def __init__(self, service: SignalCandidateService, comparison_set_id: str) -> None:
        super().__init__()
        self.service = service
        self.comparison_set_id = comparison_set_id
        self.cancellation = CancellationToken()
        self.signals = _Signals()

    def cancel(self) -> None:
        self.cancellation.cancel()

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.run(
                self.comparison_set_id,
                cancellation=self.cancellation,
                progress_callback=self._progress,
            )
        except ExtensionCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:  # pragma: no cover - surfaced through GUI
            self.signals.failed.emit(str(exc))
        else:
            self.signals.completed.emit(result)

    def _progress(self, update: ProgressUpdate) -> None:
        self.signals.progress.emit(update.current, update.total, update.message)


class SignalCandidatesView(QWidget):
    """Artifact-backed deterministic Signal Candidate Engine workspace."""

    source_row_requested = Signal(str, int, str)
    output_message = Signal(str)

    def __init__(
        self,
        project: CrtProject,
        comparison_set: object,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("signalCandidatesWorkspace")
        self.project = project
        self.comparison_set = comparison_set
        self.comparison_set_id = str(getattr(comparison_set, "id", ""))
        self.service = SignalCandidateService(project)
        self._task: _Task | None = None
        self._candidates: list[dict[str, Any]] = []
        self._supports: list[dict[str, Any]] = []
        self._evidence: list[dict[str, Any]] = []
        self._input_available = False
        self._build_ui()
        self.refresh_inputs()
        self._load_artifacts()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        intro = QLabel(
            "Signal Candidate Engine scala trwałe wyniki Experiment Diff i opcjonalnie "
            "waliduje aktywność przez Signal Discovery. Nie skanuje ponownie RAW i nie "
            "korzysta z AI; ranking pozostaje deterministyczny i audytowalny.",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        actions = QHBoxLayout()
        self.run_button = QPushButton("Zbuduj kandydatów", self)
        self.run_button.setObjectName("runSignalCandidateEngine")
        self.run_button.clicked.connect(self._start)
        actions.addWidget(self.run_button)
        self.cancel_button = QPushButton("Anuluj", self)
        self.cancel_button.setObjectName("cancelSignalCandidateEngine")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.setEnabled(False)
        actions.addWidget(self.cancel_button)
        self.refresh_inputs_button = QPushButton("Odśwież źródła", self)
        self.refresh_inputs_button.setObjectName("refreshSignalCandidateInputs")
        self.refresh_inputs_button.clicked.connect(self.refresh_inputs)
        actions.addWidget(self.refresh_inputs_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.input_label = QLabel("Sprawdzam artefakty źródłowe…", self)
        self.input_label.setObjectName("signalCandidateInputsSummary")
        self.input_label.setWordWrap(True)
        root.addWidget(self.input_label)

        self.progress = QProgressBar(self)
        self.progress.setObjectName("signalCandidateProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Oczekiwanie")
        root.addWidget(self.progress)

        self.status_label = QLabel("Gotowe.", self)
        self.status_label.setObjectName("signalCandidateStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.status_label)

        artifact_row = QHBoxLayout()
        artifact_row.addWidget(QLabel("Zapisany wynik:", self))
        self.artifact_combo = QComboBox(self)
        self.artifact_combo.setObjectName("signalCandidateArtifactSelector")
        self.artifact_combo.currentIndexChanged.connect(self._show_selected_artifact)
        artifact_row.addWidget(self.artifact_combo, 1)
        self.refresh_artifacts_button = QPushButton("Odśwież wyniki", self)
        self.refresh_artifacts_button.setObjectName("refreshSignalCandidateArtifacts")
        self.refresh_artifacts_button.clicked.connect(self._load_artifacts)
        artifact_row.addWidget(self.refresh_artifacts_button)
        root.addLayout(artifact_row)

        self.summary_label = QLabel("Brak wyniku Signal Candidate Engine.", self)
        self.summary_label.setObjectName("signalCandidateSummary")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        self.table = QTableWidget(0, len(_HEADERS), self)
        self.table.setObjectName("signalCandidateTable")
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._candidate_selected)
        root.addWidget(self.table, 1)

        support_row = QHBoxLayout()
        support_row.addWidget(QLabel("Wsparcie eksperymentalne:", self))
        self.support_combo = QComboBox(self)
        self.support_combo.setObjectName("signalCandidateSupportSelector")
        self.support_combo.currentIndexChanged.connect(self._support_selected)
        support_row.addWidget(self.support_combo, 1)
        root.addLayout(support_row)

        self.support_label = QLabel("Wybierz kandydata, aby zobaczyć źródła rankingu.", self)
        self.support_label.setObjectName("signalCandidateSupportSummary")
        self.support_label.setWordWrap(True)
        root.addWidget(self.support_label)

        evidence_row = QHBoxLayout()
        evidence_row.addWidget(QLabel("Exact evidence:", self))
        self.evidence_combo = QComboBox(self)
        self.evidence_combo.setObjectName("signalCandidateEvidenceSelector")
        self.evidence_combo.currentIndexChanged.connect(self._evidence_selected)
        evidence_row.addWidget(self.evidence_combo, 1)
        self.open_before_button = QPushButton("Otwórz stan PRZED", self)
        self.open_before_button.setObjectName("signalCandidateOpenBefore")
        self.open_before_button.clicked.connect(lambda: self._open_evidence("before"))
        evidence_row.addWidget(self.open_before_button)
        self.open_after_button = QPushButton("Otwórz stan PO", self)
        self.open_after_button.setObjectName("signalCandidateOpenAfter")
        self.open_after_button.clicked.connect(lambda: self._open_evidence("after"))
        evidence_row.addWidget(self.open_after_button)
        root.addLayout(evidence_row)

        self.evidence_label = QLabel("Brak wybranego dowodu.", self)
        self.evidence_label.setObjectName("signalCandidateEvidenceSummary")
        self.evidence_label.setWordWrap(True)
        root.addWidget(self.evidence_label)
        self._refresh_evidence_buttons()

    @Slot()
    def refresh_inputs(self) -> None:
        try:
            selection = self.service.select_inputs(self.comparison_set_id)
        except Exception as exc:
            self._input_available = False
            self.input_label.setText(f"Brak gotowych źródeł: {exc}")
        else:
            self._input_available = bool(selection.experiment_artifacts)
            self.input_label.setText(
                f"Experiment Diff: {len(selection.experiment_artifacts)} unikalnych eksperymentów | "
                f"Signal Discovery: {len(selection.signal_discovery_artifacts)} pasujących artefaktów | "
                f"klucze CAN kandydatów: {len(selection.candidate_message_keys)}."
            )
        self.run_button.setEnabled(self._input_available and self._task is None)

    @Slot()
    def _start(self) -> None:
        if self._task is not None or not self._input_available:
            return
        task = _Task(self.service, self.comparison_set_id)
        task.signals.progress.connect(self._progress)
        task.signals.completed.connect(self._completed)
        task.signals.failed.connect(self._failed)
        task.signals.cancelled.connect(self._cancelled)
        self._task = task
        self._set_running(True)
        self.progress.setRange(0, 0)
        self.progress.setFormat("Uruchamianie…")
        self.status_label.setText("Scalam deterministyczne artefakty w tle…")
        QThreadPool.globalInstance().start(task)

    @Slot()
    def _cancel(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Anulowanie Signal Candidate Engine…")

    @Slot(int, int, str)
    def _progress(self, current: int, total: int, message: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
            self.progress.setFormat(f"{current}/{total}")
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
        self.status_label.setText(
            "Signal Candidate Engine zakończony. Ranking i exact evidence zapisano w projekcie."
        )
        self.output_message.emit(
            f"Signal Candidate Engine zakończony: {len(result.artifacts)} artefakt(ów)"
        )
        self._load_artifacts(result.artifacts[0].id)
        self.refresh_inputs()

    @Slot(str)
    def _failed(self, error: str) -> None:
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Błąd")
        self.status_label.setText(f"Signal Candidate Engine: {error}")

    @Slot()
    def _cancelled(self) -> None:
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Anulowano")
        self.status_label.setText(
            "Analiza anulowana; artefakty i sesje źródłowe pozostały niezmienione."
        )

    def _set_running(self, running: bool) -> None:
        if not running:
            self._task = None
        self.run_button.setEnabled(self._input_available and not running)
        self.cancel_button.setEnabled(running)
        self.refresh_inputs_button.setEnabled(not running)
        self.refresh_artifacts_button.setEnabled(not running)
        self.artifact_combo.setEnabled(not running and self.artifact_combo.count() > 0)

    @Slot()
    @Slot(str)
    def _load_artifacts(self, preferred_artifact_id: str = "") -> None:
        current = preferred_artifact_id or str(self.artifact_combo.currentData() or "")
        try:
            artifacts = self.service.list_artifacts(self.comparison_set_id)
        except Exception as exc:
            artifacts = ()
            self.status_label.setText(f"Nie można odczytać artefaktów Signal Candidates: {exc}")
        self.artifact_combo.blockSignals(True)
        self.artifact_combo.clear()
        selected = -1
        for index, artifact in enumerate(artifacts):
            self.artifact_combo.addItem(
                f"{artifact.created_at_utc or 'bez daty'} — {artifact.provider_version} — "
                f"{artifact.sha256[:12] if artifact.sha256 else 'bez SHA'}",
                artifact.id,
            )
            if artifact.id == current:
                selected = index
        if artifacts:
            self.artifact_combo.setCurrentIndex(selected if selected >= 0 else 0)
        self.artifact_combo.blockSignals(False)
        self.artifact_combo.setEnabled(bool(artifacts) and self._task is None)
        self._show_selected_artifact()

    @Slot()
    @Slot(int)
    def _show_selected_artifact(self, _index: int = -1) -> None:
        artifact_id = str(self.artifact_combo.currentData() or "")
        artifact = next(
            (
                item
                for item in self.service.list_artifacts(self.comparison_set_id)
                if item.id == artifact_id
            ),
            None,
        )
        if artifact is None:
            self._render({})
            return
        try:
            payload = self.service.read_artifact(artifact)
        except Exception as exc:
            self.status_label.setText(f"Nie można odczytać artefaktu: {exc}")
            return
        self._render(payload)

    def _render(self, payload: Mapping[str, Any]) -> None:
        summary = _mapping(payload.get("summary"))
        if payload:
            self.summary_label.setText(
                f"Kandydaci: {summary.get('candidate_count', 0)} | "
                f"strong: {summary.get('strong_count', 0)} | "
                f"medium: {summary.get('medium_count', 0)} | "
                f"weak: {summary.get('weak_count', 0)} | "
                f"Experiment Diff: {summary.get('experiment_artifact_count', 0)} | "
                f"Signal Discovery: {summary.get('signal_discovery_artifact_count', 0)}. "
                "AI: nieużywane."
            )
        else:
            self.summary_label.setText("Brak zapisanego wyniku Signal Candidate Engine.")

        rows = payload.get("candidates")
        self._candidates = [dict(item) for item in rows if isinstance(item, Mapping)] if isinstance(rows, list) else []
        self.table.setRowCount(len(self._candidates))
        for row, candidate in enumerate(self._candidates):
            best = _mapping(candidate.get("best_support"))
            experiment = _mapping(best.get("experiment"))
            target_selection = _mapping(experiment.get("target"))
            target = _mapping(best.get("target"))
            control = _mapping(best.get("control"))
            direction = _mapping(best.get("direction"))
            timing = _mapping(best.get("timing"))
            activity = _mapping(candidate.get("activity_validation"))
            values = (
                candidate.get("rank", "—"),
                candidate.get("strength", "—"),
                f"{float(candidate.get('candidate_score', 0.0)):.3f}",
                candidate.get("arbitration_id_hex", "—"),
                candidate.get("channel", "—"),
                "EXT" if candidate.get("is_extended_id") else "STD",
                candidate.get("byte_index", "—"),
                candidate.get("bit_index", "—"),
                target_selection.get("label", target_selection.get("name", "—")),
                _ratio(target.get("changed_event_count"), target.get("eligible_event_count")),
                _ratio(control.get("changed_event_count"), control.get("eligible_event_count")),
                direction.get("dominant", "—"),
                _ms(timing.get("mean_delay_ns")),
                _activity_text(activity),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in {0, 2, 4, 6, 7, 9, 10, 12}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column, item)
        if self._candidates:
            self.table.selectRow(0)
        else:
            self._clear_candidate_details()

    @Slot()
    def _candidate_selected(self) -> None:
        candidate = self._selected_candidate()
        self.support_combo.blockSignals(True)
        self.support_combo.clear()
        self._supports = []
        self.evidence_combo.blockSignals(True)
        self.evidence_combo.clear()
        self._evidence = []
        if candidate is not None:
            supports = candidate.get("supports")
            self._supports = [dict(item) for item in supports if isinstance(item, Mapping)] if isinstance(supports, list) else []
            for index, support in enumerate(self._supports):
                experiment = _mapping(support.get("experiment"))
                target = _mapping(experiment.get("target"))
                control = _mapping(experiment.get("control"))
                label = target.get("label", target.get("name", "eksperyment"))
                if control:
                    label += f" | CTRL: {control.get('label', control.get('name', 'control'))}"
                self.support_combo.addItem(
                    f"{label} | score={float(support.get('score', 0.0)):.3f}",
                    index,
                )
            evidence = candidate.get("evidence")
            self._evidence = [dict(item) for item in evidence if isinstance(item, Mapping)] if isinstance(evidence, list) else []
            for index, item in enumerate(self._evidence):
                target = _mapping(item.get("experiment_target"))
                marker = _mapping(item.get("marker"))
                group = "TEST" if item.get("group") == "target" else "CTRL"
                self.evidence_combo.addItem(
                    f"{group} | {target.get('label', target.get('name', 'experiment'))} | "
                    f"{item.get('session_name', item.get('session_id', '—'))} | "
                    f"{marker.get('name', 'marker')} | Δt={_ms(item.get('delay_ns'))} ms",
                    index,
                )
        self.support_combo.blockSignals(False)
        self.evidence_combo.blockSignals(False)
        if self._supports:
            self.support_combo.setCurrentIndex(0)
        if self._evidence:
            self.evidence_combo.setCurrentIndex(0)
        self._support_selected()
        self._evidence_selected()

    @Slot()
    @Slot(int)
    def _support_selected(self, _index: int = -1) -> None:
        index = self.support_combo.currentIndex()
        support = self._supports[index] if 0 <= index < len(self._supports) else None
        candidate = self._selected_candidate()
        if support is None or candidate is None:
            self.support_label.setText("Brak wsparcia eksperymentalnego.")
            return
        target = _mapping(support.get("target"))
        control = _mapping(support.get("control"))
        direction = _mapping(support.get("direction"))
        timing = _mapping(support.get("timing"))
        activity = _mapping(candidate.get("activity_validation"))
        self.support_label.setText(
            f"{candidate.get('candidate_key', '—')} | klasa={candidate.get('strength', '—')} | "
            f"Target {_ratio(target.get('changed_event_count'), target.get('eligible_event_count'))} | "
            f"Control {_ratio(control.get('changed_event_count'), control.get('eligible_event_count'))} | "
            f"kierunek={direction.get('dominant', '—')} ({_percent(direction.get('consistency_ratio'))}) | "
            f"mean={_ms(timing.get('mean_delay_ns'))} ms | "
            f"Signal Discovery={_activity_text(activity)}."
        )

    @Slot()
    @Slot(int)
    def _evidence_selected(self, _index: int = -1) -> None:
        evidence = self._selected_evidence()
        if evidence is None:
            self.evidence_label.setText("Brak zachowanego exact evidence dla kandydata.")
            self._refresh_evidence_buttons()
            return
        before = _mapping(evidence.get("before"))
        after = _mapping(evidence.get("after"))
        self.evidence_label.setText(
            f"session={evidence.get('session_name', evidence.get('session_id', '—'))} | "
            f"stan {evidence.get('before_state')}→{evidence.get('after_state')} | "
            f"before source_row={before.get('source_row', '—')} | "
            f"after source_row={after.get('source_row', '—')} | "
            f"delay={_ms(evidence.get('delay_ns'))} ms"
        )
        self._refresh_evidence_buttons()

    def _selected_candidate(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        return self._candidates[row] if 0 <= row < len(self._candidates) else None

    def _selected_evidence(self) -> dict[str, Any] | None:
        index = self.evidence_combo.currentIndex()
        return self._evidence[index] if 0 <= index < len(self._evidence) else None

    def _open_evidence(self, which: str) -> None:
        evidence = self._selected_evidence()
        candidate = self._selected_candidate()
        if evidence is None or candidate is None:
            return
        reference = _mapping(evidence.get(which))
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
        before = _mapping(evidence.get("before")) if evidence else {}
        after = _mapping(evidence.get("after")) if evidence else {}
        self.open_before_button.setEnabled(isinstance(before.get("source_row"), int))
        self.open_after_button.setEnabled(isinstance(after.get("source_row"), int))

    def _clear_candidate_details(self) -> None:
        self.support_combo.clear()
        self.evidence_combo.clear()
        self._supports = []
        self._evidence = []
        self.support_label.setText("Brak kandydatów w zapisanym artefakcie.")
        self.evidence_label.setText("Brak exact evidence.")
        self._refresh_evidence_buttons()

    def cancel_all(self) -> None:
        if self._task is not None:
            self._task.cancel()


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _ratio(numerator: object, denominator: object) -> str:
    try:
        return f"{int(numerator)}/{int(denominator)}"
    except (TypeError, ValueError):
        return "—"


def _percent(value: object) -> str:
    return f"{float(value) * 100.0:.1f}%" if isinstance(value, (int, float)) else "—"


def _ms(value: object) -> str:
    return f"{float(value) / 1_000_000.0:.3f}" if isinstance(value, (int, float)) else "—"


def _activity_text(activity: Mapping[str, Any]) -> str:
    status = str(activity.get("status", "unavailable"))
    if status == "unavailable":
        return "brak artefaktu"
    sessions = activity.get("session_count", 0)
    total = activity.get("comparison_session_count", 0)
    return f"{status} {sessions}/{total}"


__all__ = ["SignalCandidatesView"]
