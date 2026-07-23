from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.comparison_analysis_service import (
    ComparisonAnalysisExecutionResult,
    ComparisonAnalysisService,
)
from app.domain import Artifact
from app.extensions import CancellationToken, ExtensionCancelled, ProgressUpdate
from app.project import CrtProject

_STATISTICS_REASON_LABELS = {
    "new": "Nowe ID",
    "missing": "Brakujące ID",
    "frequency_increase": "Częstotliwość ↑",
    "frequency_decrease": "Częstotliwość ↓",
    "share_increase": "Udział ↑",
    "share_decrease": "Udział ↓",
}
_PAYLOAD_CHANGE_LABELS = {
    "new_message_key": "Nowy klucz wiadomości",
    "missing_message_key": "Brakujący klucz wiadomości",
    "dlc_set_changed": "Zmiana zestawu DLC",
    "variant_comparison_truncated": "Limit wariantów",
    "constant_byte_changed": "Zmiana stałego bajtu",
    "byte_became_variable": "Bajt stał się zmienny",
    "byte_became_constant": "Bajt stał się stały",
    "byte_value_set_changed": "Zmiana zbioru wartości",
    "byte_position_removed": "Pozycja bajtu zniknęła",
    "byte_position_added": "Nowa pozycja bajtu",
    "missing_payload_variant": "Brakujący wariant payloadu",
    "new_payload_variant": "Nowy wariant payloadu",
    "byte_presence_changed": "Zmiana obecności bajtu",
    "dominant_value_changed": "Zmiana dominującej wartości",
    "dominant_share_changed": "Zmiana udziału dominanty",
}
_STATISTICS_SESSION_HEADERS = (
    "Sesja",
    "Rola",
    "Ramki",
    "Klucze ID",
    "Nowe",
    "Brakujące",
    "Hz ↑",
    "Hz ↓",
    "Udział ↑",
    "Udział ↓",
)
_STATISTICS_CHANGE_HEADERS = (
    "Sesja",
    "Kanał",
    "CAN ID",
    "Format",
    "Typ",
    "Zmiana",
    "Hz bazowe",
    "Hz bieżące",
    "Δ Hz [%]",
    "Udział bazowy [%]",
    "Udział bieżący [%]",
)
_PAYLOAD_SESSION_HEADERS = (
    "Sesja",
    "Rola",
    "Ramki danych",
    "Klucze payload",
    "Nowe",
    "Brakujące",
    "Warianty",
    "Ramki poza limitem",
    "Bajty stałe",
    "Bajty zmienne",
)
_PAYLOAD_CHANGE_HEADERS = (
    "Sesja",
    "Kanał",
    "CAN ID",
    "Format",
    "Zmiana",
    "Bajt",
    "Payload",
    "Baza",
    "Bieżąca",
)


class _TaskSignals(QObject):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class ComparisonAnalysisTask(QRunnable):
    def __init__(
        self,
        service: ComparisonAnalysisService,
        provider_id: str,
        set_id: str,
    ) -> None:
        super().__init__()
        self.service = service
        self.provider_id = provider_id
        self.set_id = set_id
        self.cancellation = CancellationToken()
        self.signals = _TaskSignals()

    def cancel(self) -> None:
        self.cancellation.cancel()

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.run(
                self.provider_id,
                self.set_id,
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


class ComparisonAnalysisDialog(QDialog):
    output_message = Signal(str)
    analysis_completed = Signal(str)

    def __init__(
        self,
        project: CrtProject,
        comparison_set_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.comparison_set_id = comparison_set_id
        self.service = ComparisonAnalysisService(project)
        self.comparison_set = self.service.comparison_sets.get(comparison_set_id)
        self._task: ComparisonAnalysisTask | None = None
        self._artifacts: tuple[Artifact, ...] = ()

        self.setWindowTitle(f"Analiza porównawcza — {self.comparison_set.name}")
        self.resize(1180, 780)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        title = QLabel(f"Zestaw: {self.comparison_set.name}", self)
        title.setObjectName("comparisonAnalysisTitle")
        font = title.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        title.setFont(font)
        root.addWidget(title)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Analiza:", self))
        self.provider_combo = QComboBox(self)
        self.provider_combo.setObjectName("comparisonAnalysisProvider")
        self.provider_combo.setMinimumWidth(320)
        for manifest in self.service.available_comparison_analyses():
            self.provider_combo.addItem(manifest.name, manifest.id)
        controls.addWidget(self.provider_combo)
        self.run_button = QPushButton("Uruchom", self)
        self.run_button.setObjectName("runComparisonAnalysis")
        self.run_button.clicked.connect(self._start_analysis)
        controls.addWidget(self.run_button)
        self.cancel_button = QPushButton("Anuluj", self)
        self.cancel_button.setObjectName("cancelComparisonAnalysis")
        self.cancel_button.clicked.connect(self._cancel_analysis)
        controls.addWidget(self.cancel_button)
        self.refresh_button = QPushButton("Odśwież wyniki", self)
        self.refresh_button.setObjectName("refreshComparisonArtifacts")
        self.refresh_button.clicked.connect(self._load_artifacts)
        controls.addWidget(self.refresh_button)
        controls.addStretch(1)
        root.addLayout(controls)

        self.progress = QProgressBar(self)
        self.progress.setObjectName("comparisonAnalysisProgress")
        self.progress.setRange(0, 100)
        self.progress.setFormat("Oczekiwanie")
        root.addWidget(self.progress)
        self.status_label = QLabel(self)
        self.status_label.setObjectName("comparisonAnalysisStatus")
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(self.status_label)

        artifacts = QHBoxLayout()
        artifacts.addWidget(QLabel("Wynik analizy:", self))
        self.artifact_combo = QComboBox(self)
        self.artifact_combo.setObjectName("comparisonArtifactSelector")
        self.artifact_combo.currentIndexChanged.connect(
            self._show_selected_artifact
        )
        artifacts.addWidget(self.artifact_combo, 1)
        root.addLayout(artifacts)
        self.artifact_info = QLabel(self)
        self.artifact_info.setWordWrap(True)
        root.addWidget(self.artifact_info)
        self.summary_label = QLabel(self)
        self.summary_label.setObjectName("comparisonAnalysisSummary")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.sessions_table = _table(
            splitter,
            "comparisonSessionSummaryTable",
            _STATISTICS_SESSION_HEADERS,
        )
        self.changes_table = _table(
            splitter,
            "comparisonNotableChangesTable",
            _STATISTICS_CHANGE_HEADERS,
        )
        splitter.addWidget(self.sessions_table)
        splitter.addWidget(self.changes_table)
        splitter.setSizes((240, 420))
        root.addWidget(splitter, 1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close,
            parent=self,
        )
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        enabled = self.provider_combo.count() > 0
        self.provider_combo.setEnabled(enabled)
        self.run_button.setEnabled(enabled)
        self.cancel_button.setEnabled(False)
        self.status_label.setText(
            "Gotowe. Analiza jest pasywna i odczytuje wyłącznie zapisane sesje."
            if enabled
            else "Brak zarejestrowanego providera porównawczego."
        )
        self._load_artifacts()

    @Slot()
    def _start_analysis(self) -> None:
        if self._task is not None:
            return
        provider_id = str(self.provider_combo.currentData() or "")
        if not provider_id:
            return
        task = ComparisonAnalysisTask(
            self.service,
            provider_id,
            self.comparison_set_id,
        )
        task.signals.progress.connect(self._analysis_progress)
        task.signals.completed.connect(self._analysis_done)
        task.signals.failed.connect(self._analysis_failed)
        task.signals.cancelled.connect(self._analysis_cancelled)
        self._task = task
        self._set_running(True)
        self.progress.setRange(0, 0)
        self.progress.setFormat("Uruchamianie…")
        QThreadPool.globalInstance().start(task)

    @Slot()
    def _cancel_analysis(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self.status_label.setText("Anulowanie analizy…")

    @Slot(int, int, str)
    def _analysis_progress(
        self,
        current: int,
        total: int,
        message: str,
    ) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
            self.progress.setFormat(f"%p% — {message}")
        else:
            self.progress.setRange(0, 0)
        self.status_label.setText(message)

    @Slot(object)
    def _analysis_done(self, value: object) -> None:
        result = (
            value
            if isinstance(value, ComparisonAnalysisExecutionResult)
            else None
        )
        preferred = result.artifacts[0].id if result and result.artifacts else ""
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("Gotowe — 100%")
        self.status_label.setText(
            "Porównanie zakończone. Artefakt zapisano w projekcie."
        )
        self._load_artifacts(preferred)
        if result is not None:
            self.output_message.emit(
                f"Analiza {result.provider_id} zakończona: "
                f"{len(result.artifacts)} artefakt(ów)"
            )
            self.analysis_completed.emit(result.comparison_set_id)

    @Slot(str)
    def _analysis_failed(self, error: str) -> None:
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Błąd")
        self.status_label.setText(f"Analiza nie powiodła się: {error}")
        self.output_message.emit(
            f"Błąd analizy zestawu {self.comparison_set.name}: {error}"
        )

    @Slot()
    def _analysis_cancelled(self) -> None:
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Anulowano")
        self.status_label.setText(
            "Analiza została anulowana bez zmiany sesji źródłowych."
        )

    def _set_running(self, running: bool) -> None:
        if not running:
            self._task = None
        available = self.provider_combo.count() > 0
        self.provider_combo.setEnabled(available and not running)
        self.run_button.setEnabled(available and not running)
        self.cancel_button.setEnabled(running)
        self.refresh_button.setEnabled(not running)
        self.buttons.setEnabled(not running)

    def _load_artifacts(self, preferred_artifact_id: str = "") -> None:
        current = preferred_artifact_id or str(
            self.artifact_combo.currentData() or ""
        )
        try:
            self._artifacts = self.service.list_artifacts(
                self.comparison_set_id
            )
        except Exception as exc:
            self._artifacts = ()
            self.status_label.setText(
                f"Nie można odczytać katalogu artefaktów: {exc}"
            )
        self.artifact_combo.blockSignals(True)
        self.artifact_combo.clear()
        selected = -1
        for index, artifact in enumerate(self._artifacts):
            self.artifact_combo.addItem(
                f"{artifact.artifact_type} — "
                f"{_timestamp(artifact.created_at_utc)} — "
                f"{artifact.provider_id} {artifact.provider_version}",
                artifact.id,
            )
            if artifact.id == current:
                selected = index
        if self._artifacts:
            self.artifact_combo.setCurrentIndex(
                selected if selected >= 0 else 0
            )
        self.artifact_combo.blockSignals(False)
        self.artifact_combo.setEnabled(bool(self._artifacts))
        self._show_selected_artifact()

    @Slot()
    @Slot(int)
    def _show_selected_artifact(self, _index: int = -1) -> None:
        artifact_id = str(self.artifact_combo.currentData() or "")
        artifact = next(
            (item for item in self._artifacts if item.id == artifact_id),
            None,
        )
        if artifact is None:
            self.artifact_info.setText(
                "Brak zapisanych wyników dla tego zestawu."
            )
            self.summary_label.setText(
                "Uruchom pierwszy provider porównawczy."
            )
            self.sessions_table.setRowCount(0)
            self.changes_table.setRowCount(0)
            return
        self.artifact_info.setText(
            f"Provider: {artifact.provider_id} "
            f"{artifact.provider_version} | "
            f"Algorytm: {artifact.algorithm_version} | "
            f"Schemat: {artifact.schema_version} | "
            f"SHA-256: {artifact.sha256 or '—'}"
        )
        try:
            payload = self.service.artifacts.read_json(artifact)
        except Exception as exc:
            self.summary_label.setText(
                f"Nie można odczytać artefaktu: {exc}"
            )
            return
        schema = payload.get("schema")
        if schema == "crt.comparison_statistics":
            self._render_statistics(payload)
        elif schema == "crt.payload_differences":
            self._render_payload_difference(payload)
        else:
            self.summary_label.setText(
                "Szczegółowy podgląd nie jest dostępny."
            )
            self.sessions_table.setRowCount(0)
            self.changes_table.setRowCount(0)

    def _render_statistics(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        _configure_table(
            self.sessions_table,
            _STATISTICS_SESSION_HEADERS,
        )
        _configure_table(
            self.changes_table,
            _STATISTICS_CHANGE_HEADERS,
        )
        summary = (
            payload.get("summary")
            if isinstance(payload.get("summary"), dict)
            else {}
        )
        comparison = (
            payload.get("comparison_set")
            if isinstance(payload.get("comparison_set"), dict)
            else {}
        )
        sessions = _dict_list(payload.get("sessions"))
        changes = _dict_list(payload.get("notable_changes"))
        base_id = str(summary.get("baseline_session_id") or "")
        base_name = _session_name(sessions, base_id)
        self.summary_label.setText(
            f"Baza: {base_name or '—'}. "
            f"Sesje: {summary.get('session_count', '—')}. "
            f"Klucze wiadomości: "
            f"{summary.get('union_message_key_count', '—')}. "
            f"Istotne zmiany: "
            f"{summary.get('notable_change_count', '—')}. "
            f"Synchronizacja: "
            f"{comparison.get('synchronization_mode', '—')}."
        )
        self.sessions_table.setRowCount(len(sessions))
        for row, item in enumerate(sessions):
            _set_row(
                self.sessions_table,
                row,
                (
                    item.get("name", "—"),
                    _role(item),
                    item.get("observed_frame_count", "—"),
                    item.get("unique_message_key_count", "—"),
                    item.get("new_message_key_count", "—"),
                    item.get("missing_message_key_count", "—"),
                    item.get("frequency_increase_count", "—"),
                    item.get("frequency_decrease_count", "—"),
                    item.get("share_increase_count", "—"),
                    item.get("share_decrease_count", "—"),
                ),
            )
        self.changes_table.setRowCount(len(changes))
        for row, item in enumerate(changes):
            baseline = (
                item.get("baseline")
                if isinstance(item.get("baseline"), dict)
                else {}
            )
            current = (
                item.get("current")
                if isinstance(item.get("current"), dict)
                else {}
            )
            reasons = (
                item.get("reasons")
                if isinstance(item.get("reasons"), list)
                else []
            )
            _set_row(
                self.changes_table,
                row,
                (
                    item.get("session_name", "—"),
                    item.get("channel", "—"),
                    item.get("arbitration_id_hex", "—"),
                    "EXT" if item.get("is_extended_id") else "STD",
                    item.get("frame_kind", "—"),
                    ", ".join(
                        _STATISTICS_REASON_LABELS.get(
                            str(reason),
                            str(reason),
                        )
                        for reason in reasons
                    ),
                    _number(
                        baseline.get("mean_positive_frequency_hz")
                    ),
                    _number(
                        current.get("mean_positive_frequency_hz")
                    ),
                    _number(item.get("frequency_delta_percent")),
                    _number(baseline.get("share_percent")),
                    _number(current.get("share_percent")),
                ),
            )

    def _render_payload_difference(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        _configure_table(
            self.sessions_table,
            _PAYLOAD_SESSION_HEADERS,
        )
        _configure_table(
            self.changes_table,
            _PAYLOAD_CHANGE_HEADERS,
        )
        summary = (
            payload.get("summary")
            if isinstance(payload.get("summary"), dict)
            else {}
        )
        comparison = (
            payload.get("comparison_set")
            if isinstance(payload.get("comparison_set"), dict)
            else {}
        )
        sessions = _dict_list(payload.get("sessions"))
        changes = _dict_list(payload.get("ranked_changes"))
        base_id = str(summary.get("baseline_session_id") or "")
        base_name = _session_name(sessions, base_id)
        self.summary_label.setText(
            f"Baza: {base_name or '—'}. "
            f"Sesje: {summary.get('session_count', '—')}. "
            f"Klucze payload: "
            f"{summary.get('union_payload_message_key_count', '—')} "
            f"(wspólne: "
            f"{summary.get('common_payload_message_key_count', '—')}). "
            f"Zmiany: {summary.get('notable_change_count', '—')}. "
            f"Synchronizacja: "
            f"{comparison.get('synchronization_mode', '—')}."
        )
        self.sessions_table.setRowCount(len(sessions))
        for row, item in enumerate(sessions):
            _set_row(
                self.sessions_table,
                row,
                (
                    item.get("name", "—"),
                    _role(item),
                    item.get("observed_data_frame_count", "—"),
                    item.get("payload_message_key_count", "—"),
                    item.get("new_payload_message_key_count", "—"),
                    item.get(
                        "missing_payload_message_key_count",
                        "—",
                    ),
                    item.get("tracked_payload_variant_count", "—"),
                    item.get(
                        "untracked_payload_variant_frame_count",
                        "—",
                    ),
                    item.get("constant_byte_position_count", "—"),
                    item.get("variable_byte_position_count", "—"),
                ),
            )
        self.changes_table.setRowCount(len(changes))
        for row, item in enumerate(changes):
            byte_index, payload_hex, baseline, current = (
                _payload_change_details(item)
            )
            change_type = str(item.get("change_type") or "")
            _set_row(
                self.changes_table,
                row,
                (
                    item.get("session_name", "—"),
                    item.get("channel", "—"),
                    item.get("arbitration_id_hex", "—"),
                    "EXT" if item.get("is_extended_id") else "STD",
                    _PAYLOAD_CHANGE_LABELS.get(
                        change_type,
                        change_type,
                    ),
                    byte_index,
                    payload_hex,
                    baseline,
                    current,
                ),
            )

    def reject(self) -> None:
        if self._task is not None:
            self._cancel_analysis()
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self._task is not None:
            self._cancel_analysis()
            event.ignore()
            return
        super().closeEvent(event)


def _table(
    parent: QWidget,
    name: str,
    headers: tuple[str, ...],
) -> QTableWidget:
    table = QTableWidget(0, len(headers), parent)
    table.setObjectName(name)
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(
        QAbstractItemView.SelectionBehavior.SelectRows
    )
    table.setSelectionMode(
        QAbstractItemView.SelectionMode.SingleSelection
    )
    table.setEditTriggers(
        QAbstractItemView.EditTrigger.NoEditTriggers
    )
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents
    )
    table.horizontalHeader().setSectionResizeMode(
        0,
        QHeaderView.ResizeMode.Stretch,
    )
    return table


def _configure_table(
    table: QTableWidget,
    headers: tuple[str, ...],
) -> None:
    table.clearContents()
    table.setRowCount(0)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents
    )
    table.horizontalHeader().setSectionResizeMode(
        0,
        QHeaderView.ResizeMode.Stretch,
    )


def _set_row(
    table: QTableWidget,
    row: int,
    values: tuple[object, ...],
) -> None:
    for column, value in enumerate(values):
        item = QTableWidgetItem(str(value))
        if isinstance(value, (int, float)):
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignVCenter
            )
        table.setItem(row, column, item)


def _dict_list(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _session_name(
    sessions: list[dict],
    session_id: str,
) -> str:
    return next(
        (
            str(item.get("name"))
            for item in sessions
            if item.get("id") == session_id
        ),
        session_id,
    )


def _role(item: dict) -> str:
    return "Bazowa" if item.get("role") == "base" else "Porównywana"


def _payload_change_details(
    item: dict,
) -> tuple[object, str, str, str]:
    change_type = str(item.get("change_type") or "")
    byte_index: object = item.get("byte_index", "—")
    payload_hex = str(item.get("payload_hex") or "—")
    baseline = (
        item.get("baseline")
        if isinstance(item.get("baseline"), dict)
        else {}
    )
    current = (
        item.get("current")
        if isinstance(item.get("current"), dict)
        else {}
    )
    if "byte_index" in item:
        return (
            byte_index,
            "—",
            _byte_summary(baseline),
            _byte_summary(current),
        )
    if change_type == "dlc_set_changed":
        return (
            "—",
            "—",
            _dlc_summary(item.get("baseline_dlc_counts")),
            _dlc_summary(item.get("current_dlc_counts")),
        )
    if change_type == "variant_comparison_truncated":
        return (
            "—",
            "—",
            str(item.get("baseline_untracked_frame_count", "—")),
            str(item.get("current_untracked_frame_count", "—")),
        )
    if change_type in {
        "new_payload_variant",
        "missing_payload_variant",
    }:
        return (
            "—",
            payload_hex,
            _variant_summary(baseline),
            _variant_summary(current),
        )
    return "—", payload_hex, "—", "—"


def _byte_summary(value: dict) -> str:
    if not value:
        return "—"
    classification = str(value.get("classification") or "")
    if classification == "constant":
        result = f"stały {value.get('dominant_value_hex', '—')}"
    elif classification == "absent":
        result = "nieobecny"
    else:
        values = _dict_list(value.get("values"))
        labels = [str(item.get("value_hex", "—")) for item in values[:8]]
        suffix = (
            f" +{len(values) - len(labels)}"
            if len(values) > len(labels)
            else ""
        )
        result = f"zmienny [{', '.join(labels)}]{suffix}"
        dominant = value.get("dominant_value_hex")
        share = value.get("dominant_share_percent")
        if dominant is not None:
            result += f", dominanta {dominant} ({share}%)"
    presence = value.get("presence_percent")
    if presence is not None and float(presence) != 100.0:
        result += f", obecność {presence}%"
    return result


def _dlc_summary(value: object) -> str:
    items = _dict_list(value)
    if not items:
        return "—"
    return ", ".join(
        f"{item.get('dlc', '—')}:{item.get('count', '—')}"
        for item in items
    )


def _variant_summary(value: dict) -> str:
    if not value:
        return "—"
    return (
        f"{value.get('count', '—')} "
        f"({value.get('share_percent', '—')}%)"
    )


def _number(value: object) -> str:
    return "—" if value is None else str(value)


def _timestamp(value: str) -> str:
    return (
        value.replace("T", " ").replace("+00:00", "Z")
        if value
        else "—"
    )


__all__ = ["ComparisonAnalysisDialog", "ComparisonAnalysisTask"]
