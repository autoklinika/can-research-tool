from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.domain import Artifact
from app.extensions import CancellationToken, ExtensionCancelled, ProgressUpdate
from app.project import CrtProject
from app.session_analysis_service import AnalysisExecutionResult, SessionAnalysisService

from .detailed_logical_session_view import DetailedLogicalSessionViewWidget


class SessionAnalysisSignals(QObject):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class SessionAnalysisTask(QRunnable):
    def __init__(
        self,
        service: SessionAnalysisService,
        provider_id: str,
        session_id: str,
    ) -> None:
        super().__init__()
        self.service = service
        self.provider_id = provider_id
        self.session_id = session_id
        self.cancellation = CancellationToken()
        self.signals = SessionAnalysisSignals()

    def cancel(self) -> None:
        self.cancellation.cancel()

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.run(
                self.provider_id,
                self.session_id,
                cancellation=self.cancellation,
                progress_callback=self._report_progress,
            )
        except ExtensionCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        else:
            self.signals.completed.emit(result)

    def _report_progress(self, update: ProgressUpdate) -> None:
        self.signals.progress.emit(update.current, update.total, update.message)


class AnalysisEnabledSessionViewWidget(DetailedLogicalSessionViewWidget):
    """Stored session workspace with registry-driven passive analyses."""

    def __init__(
        self,
        *args,
        project: CrtProject | None = None,
        **kwargs,
    ) -> None:
        self.project = project
        self._analysis_service: SessionAnalysisService | None = None
        self._analysis_task: SessionAnalysisTask | None = None
        self._analysis_artifacts: tuple[Artifact, ...] = ()
        self._session_record = None
        super().__init__(*args, **kwargs)

        if project is not None:
            self._session_record = project.session_by_path(self.path)
            if self._session_record is not None:
                self._analysis_service = SessionAnalysisService(project)
        self._build_analysis_workspace()
        self._refresh_artifacts()

    def _build_analysis_workspace(self) -> None:
        page = QWidget(self.tabs)
        page.setObjectName("storedSessionAnalysisWorkspace")
        root = QVBoxLayout(page)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Analiza:"))
        self.analysis_provider_combo = QComboBox(page)
        self.analysis_provider_combo.setObjectName("sessionAnalysisProvider")
        self.analysis_provider_combo.setMinimumWidth(240)
        service = self._analysis_service
        if service is not None:
            for manifest in service.available_session_analyses():
                self.analysis_provider_combo.addItem(manifest.name, manifest.id)
        controls.addWidget(self.analysis_provider_combo)

        self.run_analysis_button = QPushButton("Uruchom", page)
        self.run_analysis_button.setObjectName("runSessionAnalysis")
        self.run_analysis_button.clicked.connect(self._start_analysis)
        controls.addWidget(self.run_analysis_button)

        self.cancel_analysis_button = QPushButton("Anuluj", page)
        self.cancel_analysis_button.setObjectName("cancelSessionAnalysis")
        self.cancel_analysis_button.setEnabled(False)
        self.cancel_analysis_button.clicked.connect(self._cancel_analysis)
        controls.addWidget(self.cancel_analysis_button)

        self.refresh_artifacts_button = QPushButton("Odśwież artefakty", page)
        self.refresh_artifacts_button.setObjectName("refreshSessionArtifacts")
        self.refresh_artifacts_button.clicked.connect(self._refresh_artifacts)
        controls.addWidget(self.refresh_artifacts_button)
        controls.addStretch(1)
        root.addLayout(controls)

        self.analysis_progress = QProgressBar(page)
        self.analysis_progress.setObjectName("sessionAnalysisProgress")
        self.analysis_progress.setRange(0, 100)
        self.analysis_progress.setValue(0)
        self.analysis_progress.setFormat("Oczekiwanie")
        root.addWidget(self.analysis_progress)

        self.analysis_status = QLabel(page)
        self.analysis_status.setObjectName("sessionAnalysisStatus")
        self.analysis_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.analysis_status)

        splitter = QSplitter(Qt.Horizontal, page)
        self.artifact_table = QTableWidget(0, 7, splitter)
        self.artifact_table.setObjectName("sessionArtifactTable")
        self.artifact_table.setHorizontalHeaderLabels(
            (
                "Utworzono",
                "Typ",
                "Provider",
                "Wersja",
                "Algorytm",
                "Schemat",
                "Plik",
            )
        )
        self.artifact_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.artifact_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.artifact_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.artifact_table.verticalHeader().hide()
        self.artifact_table.horizontalHeader().setStretchLastSection(True)
        self.artifact_table.setColumnWidth(0, 175)
        self.artifact_table.setColumnWidth(1, 150)
        self.artifact_table.setColumnWidth(2, 220)
        self.artifact_table.setColumnWidth(3, 75)
        self.artifact_table.setColumnWidth(4, 75)
        self.artifact_table.setColumnWidth(5, 65)
        self.artifact_table.currentCellChanged.connect(self._artifact_selection_changed)
        splitter.addWidget(self.artifact_table)

        self.artifact_details = QPlainTextEdit(splitter)
        self.artifact_details.setObjectName("sessionArtifactDetails")
        self.artifact_details.setReadOnly(True)
        self.artifact_details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        splitter.addWidget(self.artifact_details)
        splitter.setSizes((760, 520))
        root.addWidget(splitter, 1)

        self.analysis_tab_index = self.tabs.addTab(page, "Analizy")
        enabled = service is not None and self.analysis_provider_combo.count() > 0
        self.run_analysis_button.setEnabled(enabled)
        self.analysis_provider_combo.setEnabled(enabled)
        self.refresh_artifacts_button.setEnabled(service is not None)
        if self.project is None:
            self.analysis_status.setText(
                "Analizy są niedostępne: widok sesji nie ma kontekstu projektu CRT."
            )
        elif self._session_record is None:
            self.analysis_status.setText(
                "Analizy są niedostępne: sesja nie jest zarejestrowana w projekcie."
            )
        elif not enabled:
            self.analysis_status.setText("Brak dostępnych providerów dla pojedynczej sesji.")
        else:
            self.analysis_status.setText(
                "Gotowe. Analiza działa pasywnie na niezmiennym pliku zapisanej sesji."
            )

    @Slot()
    def _start_analysis(self) -> None:
        if self._analysis_task is not None:
            return
        service = self._analysis_service
        record = self._session_record
        provider_id = str(self.analysis_provider_combo.currentData() or "")
        if service is None or record is None or not provider_id:
            return

        task = SessionAnalysisTask(service, provider_id, record.id)
        task.signals.progress.connect(self._analysis_progress_changed)
        task.signals.completed.connect(self._analysis_completed)
        task.signals.failed.connect(self._analysis_failed)
        task.signals.cancelled.connect(self._analysis_cancelled)
        self._analysis_task = task
        self.run_analysis_button.setEnabled(False)
        self.analysis_provider_combo.setEnabled(False)
        self.cancel_analysis_button.setEnabled(True)
        self.analysis_progress.setRange(0, 0)
        self.analysis_progress.setFormat("Uruchamianie…")
        self.analysis_status.setText("Uruchamianie analizy w tle…")
        QThreadPool.globalInstance().start(task)

    @Slot()
    def _cancel_analysis(self) -> None:
        task = self._analysis_task
        if task is None:
            return
        task.cancel()
        self.cancel_analysis_button.setEnabled(False)
        self.analysis_status.setText("Anulowanie analizy…")

    @Slot(int, int, str)
    def _analysis_progress_changed(self, current: int, total: int, message: str) -> None:
        if total > 0:
            self.analysis_progress.setRange(0, total)
            self.analysis_progress.setValue(current)
            self.analysis_progress.setFormat(f"{current:,}/{total:,}".replace(",", " "))
        else:
            self.analysis_progress.setRange(0, 0)
        self.analysis_status.setText(message or "Analiza w toku…")

    @Slot(object)
    def _analysis_completed(self, result: object) -> None:
        execution = result if isinstance(result, AnalysisExecutionResult) else None
        preferred = execution.artifacts[0].id if execution and execution.artifacts else ""
        self._finish_analysis_controls()
        self.analysis_progress.setRange(0, 100)
        self.analysis_progress.setValue(100)
        self.analysis_progress.setFormat("Gotowe — 100%")
        self.analysis_status.setText("Analiza zakończona. Artefakt został zapisany w projekcie.")
        self._load_artifacts(preferred_artifact_id=preferred)
        if execution is not None:
            self.output_message.emit(
                f"Analiza {execution.provider_id} zakończona: "
                f"{len(execution.artifacts)} artefakt(ów)"
            )

    @Slot(str)
    def _analysis_failed(self, error: str) -> None:
        self._finish_analysis_controls()
        self.analysis_progress.setRange(0, 100)
        self.analysis_progress.setValue(0)
        self.analysis_progress.setFormat("Błąd")
        self.analysis_status.setText(f"Analiza nie powiodła się: {error}")
        self.output_message.emit(f"Błąd analizy sesji {self.path}: {error}")

    @Slot()
    def _analysis_cancelled(self) -> None:
        self._finish_analysis_controls()
        self.analysis_progress.setRange(0, 100)
        self.analysis_progress.setValue(0)
        self.analysis_progress.setFormat("Anulowano")
        self.analysis_status.setText("Analiza została anulowana bez zmiany sesji źródłowej.")
        self.output_message.emit(f"Anulowano analizę sesji {self.path}")

    def _finish_analysis_controls(self) -> None:
        self._analysis_task = None
        enabled = self._analysis_service is not None and self.analysis_provider_combo.count() > 0
        self.run_analysis_button.setEnabled(enabled)
        self.analysis_provider_combo.setEnabled(enabled)
        self.cancel_analysis_button.setEnabled(False)

    @Slot()
    def _refresh_artifacts(self) -> None:
        self._load_artifacts()

    def _load_artifacts(self, *, preferred_artifact_id: str = "") -> None:
        service = self._analysis_service
        record = self._session_record
        if service is None or record is None:
            self._analysis_artifacts = ()
        else:
            try:
                self._analysis_artifacts = service.list_artifacts(record.id)
            except Exception as exc:
                self._analysis_artifacts = ()
                self.analysis_status.setText(f"Nie można odczytać katalogu artefaktów: {exc}")

        self.artifact_table.setRowCount(len(self._analysis_artifacts))
        preferred_row = -1
        for row, artifact in enumerate(self._analysis_artifacts):
            values = (
                _display_timestamp(artifact.created_at_utc),
                artifact.artifact_type,
                artifact.provider_id,
                artifact.provider_version,
                artifact.algorithm_version,
                str(artifact.schema_version),
                artifact.relative_path or "—",
            )
            for column, value in enumerate(values):
                self.artifact_table.setItem(row, column, QTableWidgetItem(value))
            if artifact.id == preferred_artifact_id:
                preferred_row = row

        self.tabs.setTabText(self.analysis_tab_index, f"Analizy ({len(self._analysis_artifacts)})")
        if self._analysis_artifacts:
            target_row = preferred_row if preferred_row >= 0 else 0
            self.artifact_table.selectRow(target_row)
            self.artifact_table.setCurrentCell(target_row, 0)
            self._show_artifact_details(target_row)
        else:
            self.artifact_details.setPlainText("Brak artefaktów analizy dla tej sesji.")

    @Slot(int, int, int, int)
    def _artifact_selection_changed(
        self,
        current_row: int,
        _current_column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        self._show_artifact_details(current_row)

    def _show_artifact_details(self, row: int) -> None:
        if not 0 <= row < len(self._analysis_artifacts):
            return
        artifact = self._analysis_artifacts[row]
        service = self._analysis_service
        if service is None:
            return
        try:
            payload = service.artifacts.read_json(artifact)
            details = _format_artifact_details(artifact, payload)
        except Exception as exc:
            details = _format_artifact_header(artifact) + f"\n\nBŁĄD ODCZYTU\n{exc}"
        self.artifact_details.setPlainText(details)

    def shutdown(self) -> None:
        task = self._analysis_task
        if task is not None:
            task.cancel()
        super().shutdown()


def _display_timestamp(value: str) -> str:
    return value.replace("T", " ").replace("+00:00", "Z") if value else "—"


def _format_artifact_header(artifact: Artifact) -> str:
    sources = ", ".join(
        f"{source.session_id}:{source.source_kind}" for source in artifact.sources
    )
    return "\n".join(
        (
            "ARTEFAKT ANALIZY",
            "",
            f"ID: {artifact.id}",
            f"Typ: {artifact.artifact_type}",
            f"Provider: {artifact.provider_id} {artifact.provider_version}",
            f"Algorytm: {artifact.algorithm_version}",
            f"Schemat: {artifact.schema_version}",
            f"Utworzono: {_display_timestamp(artifact.created_at_utc)}",
            f"Plik: {artifact.relative_path or '—'}",
            f"SHA-256: {artifact.sha256 or '—'}",
            f"Źródła: {sources or '—'}",
        )
    )


def _format_artifact_details(artifact: Artifact, payload: object) -> str:
    header = _format_artifact_header(artifact)
    if not isinstance(payload, dict):
        return header
    if payload.get("schema") != "crt.session_statistics":
        return header + "\n\nPodgląd szczegółowy nie jest dostępny dla tego typu artefaktu."

    totals = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
    timing = (
        payload.get("capture_timing")
        if isinstance(payload.get("capture_timing"), dict)
        else {}
    )
    channels = payload.get("channels") if isinstance(payload.get("channels"), list) else []
    channel_text = ", ".join(
        f"{item.get('channel')}: {item.get('frame_count')}"
        for item in channels
        if isinstance(item, dict)
    ) or "—"
    return header + "\n\n" + "\n".join(
        (
            "PODSUMOWANIE SESJI",
            "",
            f"Ramki: {totals.get('frame_count', '—')}",
            f"Bajty payloadu: {totals.get('payload_bytes', '—')}",
            f"Unikalne CAN ID: {totals.get('unique_arbitration_id_count', '—')}",
            f"Klucze wiadomości: {totals.get('unique_message_key_count', '—')}",
            f"Data / RTR / Error: {totals.get('data_frame_count', '—')} / "
            f"{totals.get('remote_frame_count', '—')} / "
            f"{totals.get('error_frame_count', '—')}",
            f"STD / EXT: {totals.get('standard_frame_count', '—')} / "
            f"{totals.get('extended_frame_count', '—')}",
            f"Zakres czasu [s]: {totals.get('timestamp_span_s', '—')}",
            f"Średnia częstotliwość dodatnich interwałów [Hz]: "
            f"{timing.get('mean_positive_frequency_hz', '—')}",
            f"Zerowe / ujemne delty czasu: {timing.get('zero_interval_count', '—')} / "
            f"{timing.get('negative_interval_count', '—')}",
            f"Kanały (ramki): {channel_text}",
        )
    )
