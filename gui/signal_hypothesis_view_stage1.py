from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QSettings, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.comparison_analysis_service import ComparisonAnalysisExecutionResult
from app.extensions import CancellationToken, ExtensionCancelled, ProgressUpdate
from app.local_ai import LocalAIConfig
from app.project import CrtProject
from app.signal_hypothesis_service import SignalHypothesisService


_HEADERS = (
    "#",
    "Klasa",
    "Score",
    "CAN ID",
    "Byte",
    "Bit",
    "Target",
    "Control",
    "Najlepszy eksperyment",
)
_SETTINGS_BASE_URL = "ai/localBaseUrl"
_SETTINGS_MODEL = "ai/localModel"
_SETTINGS_TIMEOUT = "ai/localTimeoutSeconds"


class _Signals(QObject):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class _Task(QRunnable):
    def __init__(
        self,
        service: SignalHypothesisService,
        comparison_set_id: str,
        candidate_artifact_id: str,
        candidate_key: str,
        user_context: str,
    ) -> None:
        super().__init__()
        self.service = service
        self.comparison_set_id = comparison_set_id
        self.candidate_artifact_id = candidate_artifact_id
        self.candidate_key = candidate_key
        self.user_context = user_context
        self.cancellation = CancellationToken()
        self.signals = _Signals()

    def cancel(self) -> None:
        self.cancellation.cancel()

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.run(
                self.comparison_set_id,
                candidate_artifact_id=self.candidate_artifact_id,
                candidate_key=self.candidate_key,
                user_context=self.user_context,
                cancellation=self.cancellation,
                progress_callback=self._progress,
            )
        except ExtensionCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:  # pragma: no cover - displayed through GUI
            self.signals.failed.emit(str(exc))
        else:
            self.signals.completed.emit(result)

    def _progress(self, update: ProgressUpdate) -> None:
        self.signals.progress.emit(update.current, update.total, update.message)


class SignalHypothesisView(QWidget):
    """Optional local-AI interpretation of deterministic signal candidates."""

    output_message = Signal(str)

    def __init__(
        self,
        project: CrtProject,
        comparison_set: object,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("signalHypothesisWorkspace")
        self.project = project
        self.comparison_set = comparison_set
        self.comparison_set_id = str(getattr(comparison_set, "id", ""))
        self.catalog = SignalHypothesisService(project)
        self._task: _Task | None = None
        self._candidates: list[dict[str, Any]] = []
        self._build_ui()
        self._load_settings()
        self._load_candidate_artifacts()
        self._load_hypothesis_artifacts()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        intro = QLabel(
            "Signal Hypothesis używa lokalnego AI wyłącznie do interpretacji gotowego "
            "artefaktu Signal Candidates. AI nie zmienia score, klasy ani evidence, nie "
            "czyta RAW CAN i nie jest wymagane do normalnej pracy CRT.",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        config_row = QHBoxLayout()
        config_row.addWidget(QLabel("Local AI URL:", self))
        self.base_url_edit = QLineEdit(self)
        self.base_url_edit.setObjectName("signalHypothesisBaseUrl")
        self.base_url_edit.setPlaceholderText("http://192.168.x.x:11434/v1")
        config_row.addWidget(self.base_url_edit, 2)
        config_row.addWidget(QLabel("Model:", self))
        self.model_edit = QLineEdit(self)
        self.model_edit.setObjectName("signalHypothesisModel")
        self.model_edit.setPlaceholderText("qwen3.6:35b-hermes64k")
        config_row.addWidget(self.model_edit, 1)
        config_row.addWidget(QLabel("Timeout [s]:", self))
        self.timeout_spin = QSpinBox(self)
        self.timeout_spin.setObjectName("signalHypothesisTimeout")
        self.timeout_spin.setRange(1, 120)
        self.timeout_spin.setValue(30)
        config_row.addWidget(self.timeout_spin)
        root.addLayout(config_row)

        self.ai_status = QLabel(
            "AI jest opcjonalne. Niedostępny endpoint spowoduje błąd tylko tej operacji.",
            self,
        )
        self.ai_status.setObjectName("signalHypothesisAIStatus")
        self.ai_status.setWordWrap(True)
        root.addWidget(self.ai_status)

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Signal Candidates:", self))
        self.candidate_artifact_combo = QComboBox(self)
        self.candidate_artifact_combo.setObjectName("signalHypothesisCandidateArtifact")
        self.candidate_artifact_combo.currentIndexChanged.connect(self._candidate_artifact_changed)
        source_row.addWidget(self.candidate_artifact_combo, 1)
        self.refresh_candidates_button = QPushButton("Odśwież kandydatów", self)
        self.refresh_candidates_button.setObjectName("signalHypothesisRefreshCandidates")
        self.refresh_candidates_button.clicked.connect(self._load_candidate_artifacts)
        source_row.addWidget(self.refresh_candidates_button)
        root.addLayout(source_row)

        self.table = QTableWidget(0, len(_HEADERS), self)
        self.table.setObjectName("signalHypothesisCandidateTable")
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._refresh_run_enabled)
        root.addWidget(self.table, 1)

        context_row = QHBoxLayout()
        context_row.addWidget(QLabel("Kontekst operatora (opcjonalnie):", self))
        self.user_context_edit = QLineEdit(self)
        self.user_context_edit.setObjectName("signalHypothesisUserContext")
        self.user_context_edit.setPlaceholderText(
            "np. marker oznaczał fizyczne odłączenie EGR; nie traktuj tego jako potwierdzenia"
        )
        self.user_context_edit.setMaxLength(1000)
        context_row.addWidget(self.user_context_edit, 1)
        root.addLayout(context_row)

        actions = QHBoxLayout()
        self.run_button = QPushButton("Zaproponuj hipotezę AI", self)
        self.run_button.setObjectName("runSignalHypothesisAI")
        self.run_button.clicked.connect(self._start)
        actions.addWidget(self.run_button)
        self.cancel_button = QPushButton("Anuluj", self)
        self.cancel_button.setObjectName("cancelSignalHypothesisAI")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.setEnabled(False)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.progress = QProgressBar(self)
        self.progress.setObjectName("signalHypothesisProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Oczekiwanie")
        root.addWidget(self.progress)

        self.status_label = QLabel("Gotowe. Signal Hypothesis może działać całkowicie niezależnie od RAW.", self)
        self.status_label.setObjectName("signalHypothesisStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.status_label)

        result_row = QHBoxLayout()
        result_row.addWidget(QLabel("Zapisana hipoteza:", self))
        self.hypothesis_combo = QComboBox(self)
        self.hypothesis_combo.setObjectName("signalHypothesisArtifactSelector")
        self.hypothesis_combo.currentIndexChanged.connect(self._show_selected_hypothesis)
        result_row.addWidget(self.hypothesis_combo, 1)
        self.refresh_results_button = QPushButton("Odśwież wyniki", self)
        self.refresh_results_button.setObjectName("signalHypothesisRefreshResults")
        self.refresh_results_button.clicked.connect(self._load_hypothesis_artifacts)
        result_row.addWidget(self.refresh_results_button)
        root.addLayout(result_row)

        self.hypothesis_label = QLabel("Brak zapisanej hipotezy.", self)
        self.hypothesis_label.setObjectName("signalHypothesisResult")
        self.hypothesis_label.setWordWrap(True)
        self.hypothesis_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.hypothesis_label)

        self.rationale_label = QLabel("", self)
        self.rationale_label.setObjectName("signalHypothesisRationale")
        self.rationale_label.setWordWrap(True)
        self.rationale_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.rationale_label)

        self.next_steps_label = QLabel("", self)
        self.next_steps_label.setObjectName("signalHypothesisNextSteps")
        self.next_steps_label.setWordWrap(True)
        self.next_steps_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.next_steps_label)

        self.guardrail_label = QLabel(
            "Kontrakt: hipoteza = suggested / verified=false. AI nie potwierdza sygnału automatycznie.",
            self,
        )
        self.guardrail_label.setObjectName("signalHypothesisGuardrails")
        self.guardrail_label.setWordWrap(True)
        root.addWidget(self.guardrail_label)
        self._refresh_run_enabled()

    def _load_settings(self) -> None:
        settings = QSettings()
        try:
            defaults = LocalAIConfig.from_environment()
            default_url = defaults.base_url
            default_model = defaults.model
            default_timeout = int(defaults.timeout_s)
        except Exception:
            default_url = "http://127.0.0.1:11434/v1"
            default_model = "qwen3.6:35b-hermes64k"
            default_timeout = 30
        self.base_url_edit.setText(settings.value(_SETTINGS_BASE_URL, default_url, str))
        self.model_edit.setText(settings.value(_SETTINGS_MODEL, default_model, str))
        self.timeout_spin.setValue(settings.value(_SETTINGS_TIMEOUT, default_timeout, type=int))

    def _save_settings(self) -> None:
        settings = QSettings()
        settings.setValue(_SETTINGS_BASE_URL, self.base_url_edit.text().strip())
        settings.setValue(_SETTINGS_MODEL, self.model_edit.text().strip())
        settings.setValue(_SETTINGS_TIMEOUT, self.timeout_spin.value())
        settings.sync()

    @Slot()
    def _load_candidate_artifacts(self) -> None:
        current = str(self.candidate_artifact_combo.currentData() or "")
        try:
            artifacts = self.catalog.list_candidate_artifacts(self.comparison_set_id)
        except Exception as exc:
            artifacts = ()
            self.status_label.setText(f"Nie można odczytać Signal Candidates: {exc}")
        self.candidate_artifact_combo.blockSignals(True)
        self.candidate_artifact_combo.clear()
        selected = -1
        for index, artifact in enumerate(artifacts):
            self.candidate_artifact_combo.addItem(
                f"{artifact.created_at_utc or 'bez daty'} — {artifact.sha256[:12]}",
                artifact.id,
            )
            if artifact.id == current:
                selected = index
        if artifacts:
            self.candidate_artifact_combo.setCurrentIndex(selected if selected >= 0 else 0)
        self.candidate_artifact_combo.blockSignals(False)
        self._candidate_artifact_changed()

    @Slot()
    @Slot(int)
    def _candidate_artifact_changed(self, _index: int = -1) -> None:
        artifact_id = str(self.candidate_artifact_combo.currentData() or "")
        artifact = next(
            (
                item
                for item in self.catalog.list_candidate_artifacts(self.comparison_set_id)
                if item.id == artifact_id
            ),
            None,
        )
        if artifact is None:
            self._render_candidates(())
            return
        try:
            rows = self.catalog.candidate_rows(artifact)
        except Exception as exc:
            self.status_label.setText(f"Nie można odczytać kandydatów: {exc}")
            rows = ()
        self._render_candidates(rows)

    def _render_candidates(self, rows) -> None:
        self._candidates = [dict(item) for item in rows]
        self.table.setRowCount(len(self._candidates))
        for row, candidate in enumerate(self._candidates):
            best = _mapping(candidate.get("best_support"))
            target = _mapping(best.get("target"))
            control = _mapping(best.get("control"))
            experiment = _mapping(best.get("experiment"))
            target_selection = _mapping(experiment.get("target"))
            values = (
                candidate.get("rank", "—"),
                candidate.get("strength", "—"),
                f"{float(candidate.get('candidate_score', 0.0)):.3f}",
                candidate.get("arbitration_id_hex", "—"),
                candidate.get("byte_index", "—"),
                candidate.get("bit_index", "—"),
                _event_ratio(target),
                _control_ratio(control),
                target_selection.get("label") or target_selection.get("name") or "—",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in {0, 2, 4, 5}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
        if self._candidates:
            self.table.selectRow(0)
        self._refresh_run_enabled()

    @Slot()
    def _start(self) -> None:
        if self._task is not None:
            return
        candidate = self._selected_candidate()
        artifact_id = str(self.candidate_artifact_combo.currentData() or "")
        if candidate is None or not artifact_id:
            return
        try:
            config = LocalAIConfig(
                base_url=self.base_url_edit.text(),
                model=self.model_edit.text(),
                timeout_s=float(self.timeout_spin.value()),
            )
        except Exception as exc:
            self.ai_status.setText(f"Nieprawidłowa konfiguracja AI: {exc}")
            return
        self._save_settings()
        service = SignalHypothesisService.from_config(self.project, config)
        task = _Task(
            service,
            self.comparison_set_id,
            artifact_id,
            str(candidate.get("candidate_key", "")),
            self.user_context_edit.text().strip(),
        )
        task.signals.progress.connect(self._progress)
        task.signals.completed.connect(self._completed)
        task.signals.failed.connect(self._failed)
        task.signals.cancelled.connect(self._cancelled)
        self._task = task
        self._set_running(True)
        self.progress.setRange(0, 0)
        self.progress.setFormat("Local AI…")
        self.status_label.setText(
            "Wysyłam wyłącznie bounded Signal Candidates + evidence do lokalnego AI…"
        )
        self.ai_status.setText(f"Local AI: {config.base_url} | model: {config.model}")
        QThreadPool.globalInstance().start(task)

    @Slot()
    def _cancel(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self.cancel_button.setEnabled(False)
            self.status_label.setText(
                "Anulowanie… aktywne żądanie HTTP zakończy się najpóźniej po timeout."
            )

    @Slot(int, int, str)
    def _progress(self, current: int, total: int, message: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
            self.progress.setFormat(f"{current}/{total}")
        else:
            self.progress.setRange(0, 0)
        self.status_label.setText(message or "Signal Hypothesis w toku…")

    @Slot(object)
    def _completed(self, value: object) -> None:
        result = value if isinstance(value, ComparisonAnalysisExecutionResult) else None
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("Gotowe — 100%")
        if result is None or not result.artifacts:
            self._failed("provider nie zwrócił hipotezy")
            return
        self.status_label.setText(
            "Lokalne AI zwróciło sugestię. Hipoteza została zapisana jako suggested / verified=false."
        )
        self.output_message.emit("Signal Hypothesis AI: zapisano niepotwierdzoną hipotezę")
        self._load_hypothesis_artifacts(result.artifacts[0].id)

    @Slot(str)
    def _failed(self, error: str) -> None:
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("AI unavailable / error")
        self.status_label.setText(
            f"Signal Hypothesis AI nie wykonał operacji: {error}. Pozostałe funkcje CRT działają normalnie."
        )

    @Slot()
    def _cancelled(self) -> None:
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Anulowano")
        self.status_label.setText("Signal Hypothesis anulowano. Candidate Engine i źródła są niezmienione.")

    def _set_running(self, running: bool) -> None:
        if not running:
            self._task = None
        self.cancel_button.setEnabled(running)
        self.base_url_edit.setEnabled(not running)
        self.model_edit.setEnabled(not running)
        self.timeout_spin.setEnabled(not running)
        self.candidate_artifact_combo.setEnabled(not running and self.candidate_artifact_combo.count() > 0)
        self.refresh_candidates_button.setEnabled(not running)
        self.refresh_results_button.setEnabled(not running)
        self.hypothesis_combo.setEnabled(not running and self.hypothesis_combo.count() > 0)
        self.table.setEnabled(not running)
        self._refresh_run_enabled()

    @Slot()
    @Slot(str)
    def _load_hypothesis_artifacts(self, preferred_artifact_id: str = "") -> None:
        current = preferred_artifact_id or str(self.hypothesis_combo.currentData() or "")
        try:
            artifacts = self.catalog.list_hypothesis_artifacts(self.comparison_set_id)
        except Exception as exc:
            artifacts = ()
            self.status_label.setText(f"Nie można odczytać hipotez: {exc}")
        self.hypothesis_combo.blockSignals(True)
        self.hypothesis_combo.clear()
        selected = -1
        for index, artifact in enumerate(artifacts):
            model = artifact.metadata.get("ai_model", "") if isinstance(artifact.metadata, dict) else ""
            self.hypothesis_combo.addItem(
                f"{artifact.created_at_utc or 'bez daty'} — {model or 'AI'} — {artifact.sha256[:12]}",
                artifact.id,
            )
            if artifact.id == current:
                selected = index
        if artifacts:
            self.hypothesis_combo.setCurrentIndex(selected if selected >= 0 else 0)
        self.hypothesis_combo.blockSignals(False)
        self.hypothesis_combo.setEnabled(bool(artifacts) and self._task is None)
        self._show_selected_hypothesis()

    @Slot()
    @Slot(int)
    def _show_selected_hypothesis(self, _index: int = -1) -> None:
        artifact_id = str(self.hypothesis_combo.currentData() or "")
        artifact = next(
            (
                item
                for item in self.catalog.list_hypothesis_artifacts(self.comparison_set_id)
                if item.id == artifact_id
            ),
            None,
        )
        if artifact is None:
            self.hypothesis_label.setText("Brak zapisanej hipotezy.")
            self.rationale_label.setText("")
            self.next_steps_label.setText("")
            return
        try:
            payload = self.catalog.read_hypothesis(artifact)
        except Exception as exc:
            self.status_label.setText(f"Nie można odczytać hipotezy: {exc}")
            return
        hypothesis = _mapping(payload.get("hypothesis"))
        source = _mapping(payload.get("source_candidate"))
        ai = _mapping(payload.get("ai"))
        unit = hypothesis.get("unit") or "—"
        scale = hypothesis.get("scale")
        offset = hypothesis.get("offset")
        self.hypothesis_label.setText(
            f"{source.get('arbitration_id_hex', '—')} B{source.get('byte_index', '—')}."
            f"{source.get('bit_index', '—')} | {source.get('strength', '—')} | "
            f"score={float(source.get('candidate_score', 0.0)):.3f}\n"
            f"Sugestia: {hypothesis.get('name') or 'bez nazwy'}\n"
            f"Znaczenie: {hypothesis.get('physical_meaning') or '—'}\n"
            f"Jednostka: {unit} | scale: {scale if scale is not None else '—'} | "
            f"offset: {offset if offset is not None else '—'} | "
            f"confidence AI: {float(hypothesis.get('confidence', 0.0)):.2f}\n"
            f"Model: {ai.get('model', '—')} | status: suggested / verified=false"
        )
        self.rationale_label.setText(
            f"Uzasadnienie AI (krótkie, evidence-based): {hypothesis.get('rationale') or '—'}"
        )
        next_experiments = hypothesis.get("next_experiments")
        warnings = hypothesis.get("warnings")
        next_text = "; ".join(str(item) for item in next_experiments) if isinstance(next_experiments, list) else ""
        warning_text = "; ".join(str(item) for item in warnings) if isinstance(warnings, list) else ""
        self.next_steps_label.setText(
            f"Następne eksperymenty: {next_text or '—'}\nOstrzeżenia: {warning_text or '—'}"
        )

    def _selected_candidate(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        if 0 <= row < len(self._candidates):
            return self._candidates[row]
        return None

    @Slot()
    def _refresh_run_enabled(self) -> None:
        ready = (
            self._task is None
            and self._selected_candidate() is not None
            and bool(str(self.candidate_artifact_combo.currentData() or ""))
        )
        self.run_button.setEnabled(ready)

    def cancel_all(self) -> None:
        self._cancel()


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _event_ratio(value: Mapping[str, Any]) -> str:
    changed = int(value.get("changed_event_count", 0) or 0)
    eligible = int(value.get("eligible_event_count", 0) or 0)
    return f"{changed}/{eligible}"


def _control_ratio(value: Mapping[str, Any]) -> str:
    if not value:
        return "—"
    changed = int(value.get("changed_event_count", 0) or 0)
    eligible = int(value.get("eligible_event_count", 0) or 0)
    return f"{changed}/{eligible}"


__all__ = ["SignalHypothesisView"]
