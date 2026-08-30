from __future__ import annotations

from PySide6.QtCore import (
    QObject,
    QRunnable,
    QThreadPool,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.comparison_uds_latency import (
    ComparisonUdsLatencyService,
    DEFAULT_TIMEOUT_MS,
    StoredUdsLatency,
    UdsLatencyCancelled,
    UdsLatencyExecutionResult,
    UdsLatencyResult,
    UdsTransactionEvidence,
)
from app.domain import ComparisonSet
from app.extensions import CancellationToken, ExtensionCancelled
from app.project import CrtProject


class _UdsLatencySignals(QObject):
    progress = Signal(int, int, int, str)
    completed = Signal(int, object)
    failed = Signal(int, str)
    cancelled = Signal(int)
    finished = Signal(int)


class _UdsLatencyRunTask(QRunnable):
    def __init__(
        self,
        generation: int,
        service: ComparisonUdsLatencyService,
        comparison_set: ComparisonSet,
        request_key: str,
        response_key: str,
        timeout_ms: float,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.generation = generation
        self.service = service
        self.comparison_set = comparison_set
        self.request_key = request_key
        self.response_key = response_key
        self.timeout_ms = timeout_ms
        self.cancellation = CancellationToken()
        self.signals = _UdsLatencySignals()

    def cancel(self) -> None:
        self.cancellation.cancel()

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.run_and_save(
                self.comparison_set,
                self.request_key,
                self.response_key,
                timeout_ms=self.timeout_ms,
                cancellation=self.cancellation,
                progress_callback=self._progress,
            )
        except (UdsLatencyCancelled, ExtensionCancelled):
            self.signals.cancelled.emit(self.generation)
        except Exception as exc:  # pragma: no cover - surfaced through GUI
            self.signals.failed.emit(self.generation, str(exc))
        else:
            self.signals.completed.emit(self.generation, result)
        finally:
            self.signals.finished.emit(self.generation)

    def _progress(self, current: int, total: int, message: str) -> None:
        self.signals.progress.emit(
            self.generation,
            current,
            total,
            message,
        )


class _UdsLatencyLoadTask(QRunnable):
    def __init__(
        self,
        generation: int,
        service: ComparisonUdsLatencyService,
        comparison_set: ComparisonSet,
        request_key: str,
        response_key: str,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.generation = generation
        self.service = service
        self.comparison_set = comparison_set
        self.request_key = request_key
        self.response_key = response_key
        self.cancellation = CancellationToken()
        self.signals = _UdsLatencySignals()

    def cancel(self) -> None:
        self.cancellation.cancel()

    @Slot()
    def run(self) -> None:
        try:
            stored = self.service.load_latest_compatible(
                self.comparison_set,
                request_message_key=self.request_key,
                response_message_key=self.response_key,
                should_cancel=lambda: self.cancellation.is_cancelled,
            )
            self.cancellation.raise_if_cancelled()
        except (UdsLatencyCancelled, ExtensionCancelled):
            self.signals.cancelled.emit(self.generation)
        except Exception as exc:  # pragma: no cover - surfaced through GUI
            self.signals.failed.emit(self.generation, str(exc))
        else:
            self.signals.completed.emit(self.generation, stored)
        finally:
            self.signals.finished.emit(self.generation)


class ComparisonUdsLatencyView(QWidget):
    """Passive UDS request/response latency analysis for a comparison set."""

    source_row_requested = Signal(str, int, str)

    def __init__(
        self,
        project: CrtProject,
        comparison_set: ComparisonSet,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.comparison_set = comparison_set
        self.service = ComparisonUdsLatencyService(project)
        self._generation = 0
        self._tasks: dict[int, QRunnable] = {}
        self._result: UdsLatencyResult | None = None
        self._loaded_artifact_id = ""
        self._selected_transaction: UdsTransactionEvidence | None = None
        self._transaction_rows: list[UdsTransactionEvidence] = []

        root = QVBoxLayout(self)
        description = QLabel(
            "Pasywne parowanie komunikatów ISO-TP/UDS. Latencja jest liczona "
            "od końca żądania do początku pierwszej i końcowej odpowiedzi.",
            self,
        )
        description.setWordWrap(True)
        root.addWidget(description)

        keys = QHBoxLayout()
        keys.addWidget(QLabel("Klucz żądania:", self))
        self.request_key_edit = QLineEdit(self)
        self.request_key_edit.setObjectName("udsLatencyRequestKeyEdit")
        self.request_key_edit.setPlaceholderText("0:EXT:18DA30F9:data")
        keys.addWidget(self.request_key_edit, 2)
        keys.addWidget(QLabel("Klucz odpowiedzi:", self))
        self.response_key_edit = QLineEdit(self)
        self.response_key_edit.setObjectName("udsLatencyResponseKeyEdit")
        self.response_key_edit.setPlaceholderText("0:EXT:18DAF930:data")
        keys.addWidget(self.response_key_edit, 2)
        keys.addWidget(QLabel("Timeout po żądaniu / 0x78:", self))
        self.timeout_spin = QDoubleSpinBox(self)
        self.timeout_spin.setObjectName("udsLatencyTimeoutSpin")
        self.timeout_spin.setRange(1.0, 120_000.0)
        self.timeout_spin.setDecimals(0)
        self.timeout_spin.setSingleStep(100.0)
        self.timeout_spin.setSuffix(" ms")
        self.timeout_spin.setValue(DEFAULT_TIMEOUT_MS)
        keys.addWidget(self.timeout_spin)
        root.addLayout(keys)

        actions = QHBoxLayout()
        self.analyze_button = QPushButton("Analizuj transakcje UDS", self)
        self.analyze_button.setObjectName("analyzeUdsLatencyButton")
        self.analyze_button.clicked.connect(self.analyze)
        actions.addWidget(self.analyze_button)
        self.load_button = QPushButton("Wczytaj ostatni", self)
        self.load_button.setObjectName("loadUdsLatencyButton")
        self.load_button.clicked.connect(self.load_latest)
        actions.addWidget(self.load_button)
        self.cancel_button = QPushButton("Anuluj", self)
        self.cancel_button.setObjectName("cancelUdsLatencyButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.status_label = QLabel("Brak wyniku analizy UDS.", self)
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        root.addWidget(splitter, 1)

        upper = QWidget(splitter)
        upper_layout = QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.addWidget(QLabel("Statystyki sesji", upper))
        self.session_table = QTableWidget(0, 13, upper)
        self.session_table.setObjectName("udsLatencySessionTable")
        self.session_table.setHorizontalHeaderLabels(
            [
                "Sesja",
                "Żądania",
                "Zakończone",
                "Pozytywne",
                "Negatywne",
                "0x78",
                "Timeout",
                "Nieparowane",
                "Skuteczność",
                "Śr. 1. odp. [ms]",
                "p50 final [ms]",
                "p95 final [ms]",
                "p99 final [ms]",
            ]
        )
        _configure_table(self.session_table)
        upper_layout.addWidget(self.session_table)
        upper_layout.addWidget(QLabel("Zmiany względem sesji bazowej", upper))
        self.comparison_table = QTableWidget(0, 9, upper)
        self.comparison_table.setObjectName("udsLatencyComparisonTable")
        self.comparison_table.setHorizontalHeaderLabels(
            [
                "Sesja",
                "Skuteczność [pp]",
                "p50 1. odp. [%]",
                "p50 final [%]",
                "p95 final [%]",
                "Timeout Δ",
                "Negatywne Δ",
                "0x78 Δ",
                "Nieparowane Δ",
            ]
        )
        _configure_table(self.comparison_table)
        upper_layout.addWidget(self.comparison_table)

        lower = QWidget(splitter)
        lower_layout = QVBoxLayout(lower)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_layout.addWidget(QLabel("Pary dowodowe transakcji", lower))
        self.transaction_table = QTableWidget(0, 11, lower)
        self.transaction_table.setObjectName("udsLatencyTransactionTable")
        self.transaction_table.setHorizontalHeaderLabels(
            [
                "Sesja",
                "Żądanie",
                "SID",
                "Usługa",
                "Status",
                "0x78",
                "1. odpowiedź [ms]",
                "Final [ms]",
                "Pierwsza odpowiedź",
                "Końcowa odpowiedź",
                "NRC",
            ]
        )
        _configure_table(self.transaction_table)
        self.transaction_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.transaction_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.transaction_table.itemSelectionChanged.connect(
            self._transaction_selection_changed
        )
        lower_layout.addWidget(self.transaction_table, 1)
        navigation = QHBoxLayout()
        self.open_request_button = QPushButton("Otwórz żądanie", lower)
        self.open_request_button.setObjectName("openUdsRequestButton")
        self.open_request_button.clicked.connect(self.open_request)
        navigation.addWidget(self.open_request_button)
        self.open_first_button = QPushButton("Otwórz pierwszą odpowiedź", lower)
        self.open_first_button.setObjectName("openUdsFirstResponseButton")
        self.open_first_button.clicked.connect(self.open_first_response)
        navigation.addWidget(self.open_first_button)
        self.open_final_button = QPushButton("Otwórz odpowiedź końcową", lower)
        self.open_final_button.setObjectName("openUdsFinalResponseButton")
        self.open_final_button.clicked.connect(self.open_final_response)
        navigation.addWidget(self.open_final_button)
        navigation.addStretch(1)
        lower_layout.addLayout(navigation)
        self._update_navigation_buttons()

        splitter.addWidget(upper)
        splitter.addWidget(lower)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        QTimer.singleShot(0, self.load_latest)

    @Slot()
    def analyze(self) -> None:
        request_key = self.request_key_edit.text().strip()
        response_key = self.response_key_edit.text().strip()
        if not request_key or not response_key:
            self.status_label.setText(
                "Podaj dokładny klucz żądania i odpowiedzi UDS."
            )
            return
        self._start_task(
            _UdsLatencyRunTask(
                self._next_generation(),
                self.service,
                self.comparison_set,
                request_key,
                response_key,
                self.timeout_spin.value(),
            )
        )

    @Slot()
    def load_latest(self) -> None:
        self._start_task(
            _UdsLatencyLoadTask(
                self._next_generation(),
                self.service,
                self.comparison_set,
                self.request_key_edit.text().strip(),
                self.response_key_edit.text().strip(),
            )
        )

    @Slot()
    def cancel(self) -> None:
        self._generation += 1
        for task in tuple(self._tasks.values()):
            cancel = getattr(task, "cancel", None)
            if callable(cancel):
                cancel()
        self.status_label.setText("Anulowano analizę latencji UDS.")
        self._set_running(False)

    def cancel_all(self) -> None:
        self.cancel()

    def _next_generation(self) -> int:
        self._generation += 1
        return self._generation

    def _start_task(self, task: QRunnable) -> None:
        for current in tuple(self._tasks.values()):
            cancel = getattr(current, "cancel", None)
            if callable(cancel):
                cancel()
        generation = int(getattr(task, "generation"))
        signals = getattr(task, "signals")
        signals.progress.connect(self._task_progress)
        signals.completed.connect(self._task_completed)
        signals.failed.connect(self._task_failed)
        signals.cancelled.connect(self._task_cancelled)
        signals.finished.connect(self._task_finished)
        self._tasks[generation] = task
        self._set_running(True)
        self.status_label.setText("Przetwarzam zapisane sesje…")
        QThreadPool.globalInstance().start(task)

    @Slot(int, int, int, str)
    def _task_progress(
        self,
        generation: int,
        current: int,
        total: int,
        message: str,
    ) -> None:
        if generation != self._generation:
            return
        maximum = max(1, int(total))
        self.progress.setValue(
            max(0, min(100, round(int(current) / maximum * 100)))
        )
        self.status_label.setText(message)

    @Slot(int, object)
    def _task_completed(self, generation: int, value: object) -> None:
        if generation != self._generation:
            return
        if isinstance(value, UdsLatencyExecutionResult):
            self._loaded_artifact_id = value.artifact.id
            self._apply_result(value.result)
            self.status_label.setText(
                "Analiza UDS zakończona i zapisana jako trwały artefakt."
            )
            return
        if isinstance(value, StoredUdsLatency):
            self._loaded_artifact_id = value.artifact.id
            self._apply_result(value.result)
            self.status_label.setText(
                "Wczytano zapisane transakcje UDS bez ponownego skanowania sesji."
            )
            return
        if value is None:
            if self._result is None:
                self.status_label.setText(
                    "Nie znaleziono zgodnego zapisanego wyniku UDS."
                )
            return
        self._task_failed(generation, "Nieobsługiwany wynik zadania UDS.")

    @Slot(int, str)
    def _task_failed(self, generation: int, error: str) -> None:
        if generation != self._generation:
            return
        self.status_label.setText(
            f"Nie udało się wykonać analizy latencji UDS: {error}"
        )

    @Slot(int)
    def _task_cancelled(self, generation: int) -> None:
        if generation != self._generation:
            return
        self.status_label.setText("Anulowano analizę latencji UDS.")

    @Slot(int)
    def _task_finished(self, generation: int) -> None:
        self._tasks.pop(generation, None)
        if generation == self._generation:
            self._set_running(False)

    def _set_running(self, running: bool) -> None:
        self.analyze_button.setEnabled(not running)
        self.load_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.request_key_edit.setEnabled(not running)
        self.response_key_edit.setEnabled(not running)
        self.timeout_spin.setEnabled(not running)
        self.progress.setVisible(running)
        if not running:
            self.progress.setValue(0)

    def _apply_result(self, result: UdsLatencyResult) -> None:
        self._result = result
        self.request_key_edit.setText(
            result.configuration.request_message_key
        )
        self.response_key_edit.setText(
            result.configuration.response_message_key
        )
        self.timeout_spin.setValue(result.configuration.timeout_ms)
        self._populate_sessions()
        self._populate_comparisons()
        self._populate_transactions()

    def _populate_sessions(self) -> None:
        result = self._result
        self.session_table.setRowCount(0 if result is None else len(result.sessions))
        if result is None:
            return
        for row, item in enumerate(result.sessions):
            values = [
                item.session_name,
                str(item.request_count),
                str(item.completed_count),
                str(item.positive_response_count),
                str(item.negative_response_count),
                str(item.response_pending_count),
                str(item.timeout_count),
                str(item.unmatched_response_count),
                _percent(item.completion_rate_percent),
                _ms(item.mean_first_response_latency_ns),
                _ms(item.p50_final_response_latency_ns),
                _ms(item.p95_final_response_latency_ns),
                _ms(item.p99_final_response_latency_ns),
            ]
            for column, value in enumerate(values):
                self.session_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )

    def _populate_comparisons(self) -> None:
        result = self._result
        self.comparison_table.setRowCount(
            0 if result is None else len(result.comparisons)
        )
        if result is None:
            return
        for row, item in enumerate(result.comparisons):
            values = [
                item.session_name,
                _signed(item.completion_rate_delta_percentage_points, " pp"),
                _signed(item.p50_first_latency_delta_percent, "%"),
                _signed(item.p50_final_latency_delta_percent, "%"),
                _signed(item.p95_final_latency_delta_percent, "%"),
                f"{item.timeout_count_delta:+d}",
                f"{item.negative_response_count_delta:+d}",
                f"{item.response_pending_count_delta:+d}",
                f"{item.unmatched_response_count_delta:+d}",
            ]
            for column, value in enumerate(values):
                self.comparison_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )

    def _populate_transactions(self) -> None:
        result = self._result
        self._selected_transaction = None
        self._transaction_rows = []
        if result is not None:
            self._transaction_rows = sorted(
                (
                    transaction
                    for session in result.sessions
                    for transaction in session.transaction_evidence
                ),
                key=lambda value: (
                    value.request.first_timestamp_ns,
                    value.request.first_source_row,
                ),
            )
        self.transaction_table.setRowCount(len(self._transaction_rows))
        for row, item in enumerate(self._transaction_rows):
            first_response = item.first_response
            final_response = item.final_response
            values = [
                item.session_name,
                str(item.request.first_source_row + 1),
                f"0x{item.request_service_id:02X}",
                item.request_service_name,
                _status_text(item.status),
                str(item.response_pending_count),
                _ms(item.first_response_latency_ns),
                _ms(item.final_response_latency_ns),
                (
                    "—"
                    if first_response is None
                    else str(first_response.first_source_row + 1)
                ),
                (
                    "—"
                    if final_response is None
                    else str(final_response.first_source_row + 1)
                ),
                (
                    "—"
                    if item.final_negative_response_code is None
                    else f"0x{item.final_negative_response_code:02X}"
                ),
            ]
            for column, value in enumerate(values):
                self.transaction_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )
        self._update_navigation_buttons()

    @Slot()
    def _transaction_selection_changed(self) -> None:
        rows = self.transaction_table.selectionModel().selectedRows()
        if not rows:
            self._selected_transaction = None
        else:
            index = rows[0].row()
            self._selected_transaction = (
                self._transaction_rows[index]
                if 0 <= index < len(self._transaction_rows)
                else None
            )
        self._update_navigation_buttons()

    def _update_navigation_buttons(self) -> None:
        selected = self._selected_transaction
        self.open_request_button.setEnabled(selected is not None)
        self.open_first_button.setEnabled(
            selected is not None and selected.first_response is not None
        )
        self.open_final_button.setEnabled(
            selected is not None and selected.final_response is not None
        )

    @Slot()
    def open_request(self) -> None:
        selected = self._selected_transaction
        if selected is None:
            return
        self.source_row_requested.emit(
            selected.session_id,
            selected.request.first_source_row,
            selected.request.message_key,
        )

    @Slot()
    def open_first_response(self) -> None:
        selected = self._selected_transaction
        if selected is None or selected.first_response is None:
            return
        self.source_row_requested.emit(
            selected.session_id,
            selected.first_response.first_source_row,
            selected.first_response.message_key,
        )

    @Slot()
    def open_final_response(self) -> None:
        selected = self._selected_transaction
        if selected is None or selected.final_response is None:
            return
        self.source_row_requested.emit(
            selected.session_id,
            selected.final_response.first_source_row,
            selected.final_response.message_key,
        )


def _configure_table(table: QTableWidget) -> None:
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    header.setStretchLastSection(True)


def _ms(value: float | int | None) -> str:
    return "—" if value is None else f"{float(value) / 1_000_000.0:.3f}"


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def _signed(value: float | None, suffix: str) -> str:
    return "—" if value is None else f"{value:+.2f}{suffix}"


def _status_text(value: str) -> str:
    return {
        "positive-response": "pozytywna",
        "negative-response": "negatywna",
        "timeout": "timeout",
        "capture-ended": "koniec logu",
        "suppressed-no-response": "bez odpowiedzi (suppress)",
    }.get(value, value)


__all__ = ["ComparisonUdsLatencyView"]
