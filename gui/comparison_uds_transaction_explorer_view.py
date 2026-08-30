from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QObject,
    QPointF,
    QRectF,
    QRunnable,
    QThreadPool,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.comparison_uds_latency import (
    ComparisonUdsLatencyService,
    StoredUdsLatency,
    UdsLatencyCancelled,
    UdsLatencyResult,
)
from app.comparison_uds_transaction_explorer import (
    UdsExplorerFilter,
    UdsLatencyDistribution,
    UdsTransactionExplorerResult,
    UdsTransactionRecord,
    build_uds_transaction_explorer,
    export_groups_csv,
    export_transactions_csv,
    format_transaction_details,
)
from app.domain import ComparisonSet
from app.extensions import CancellationToken, ExtensionCancelled
from app.project import CrtProject
from app.protocol_catalog import uds_nrc_name


class _ExplorerSignals(QObject):
    completed = Signal(int, object)
    failed = Signal(int, str)
    cancelled = Signal(int)
    finished = Signal(int)


class _ExplorerLoadTask(QRunnable):
    def __init__(
        self,
        generation: int,
        service: ComparisonUdsLatencyService,
        comparison_set: ComparisonSet,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.generation = generation
        self.service = service
        self.comparison_set = comparison_set
        self.cancellation = CancellationToken()
        self.signals = _ExplorerSignals()

    def cancel(self) -> None:
        self.cancellation.cancel()

    @Slot()
    def run(self) -> None:
        try:
            stored = self.service.load_latest_compatible(
                self.comparison_set,
                should_cancel=lambda: self.cancellation.is_cancelled,
            )
            self.cancellation.raise_if_cancelled()
        except (UdsLatencyCancelled, ExtensionCancelled):
            self.signals.cancelled.emit(self.generation)
        except Exception as exc:  # pragma: no cover - surfaced in GUI
            self.signals.failed.emit(self.generation, str(exc))
        else:
            self.signals.completed.emit(self.generation, stored)
        finally:
            self.signals.finished.emit(self.generation)


class UdsLatencyDistributionChart(QWidget):
    """Compact first/final latency percentile chart for filtered evidence."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: tuple[UdsLatencyDistribution, ...] = ()
        self.setMinimumHeight(190)

    def set_distributions(
        self,
        values: tuple[UdsLatencyDistribution, ...],
    ) -> None:
        self._values = tuple(values)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        values = self._values
        if not values:
            painter.setPen(self.palette().text().color())
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Brak przefiltrowanych transakcji",
            )
            return

        numeric = [
            value
            for item in values
            for value in (
                item.p95_first_response_latency_ns,
                item.p95_final_response_latency_ns,
            )
            if value is not None
        ]
        if not numeric:
            painter.setPen(self.palette().text().color())
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Brak zakończonych odpowiedzi z mierzalną latencją",
            )
            return

        maximum = max(float(item) for item in numeric)
        if maximum <= 0:
            maximum = 1.0
        left = 190.0
        right = 24.0
        top = 34.0
        bottom = 28.0
        width = max(1.0, self.width() - left - right)
        lane_height = max(
            32.0,
            (self.height() - top - bottom) / max(1, len(values)),
        )
        painter.setPen(self.palette().text().color())
        painter.drawText(
            QRectF(left, 3.0, width, 22.0),
            Qt.AlignmentFlag.AlignCenter,
            "Rozkład latencji: p50–p95 first/final [ms]",
        )
        axis_y = self.height() - bottom + 4.0
        painter.drawLine(
            QPointF(left, axis_y),
            QPointF(left + width, axis_y),
        )
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            x = left + width * fraction
            value_ms = maximum * fraction / 1_000_000.0
            painter.drawLine(
                QPointF(x, axis_y - 4),
                QPointF(x, axis_y + 4),
            )
            painter.drawText(
                QRectF(x - 38, axis_y + 4, 76, 18),
                Qt.AlignmentFlag.AlignCenter,
                f"{value_ms:.3f}",
            )

        first_pen = QPen(
            self.palette().highlight().color(),
            3.0,
        )
        final_pen = QPen(
            self.palette().link().color(),
            3.0,
            Qt.PenStyle.DashLine,
        )
        for index, item in enumerate(values):
            center_y = top + lane_height * (index + 0.5)
            painter.setPen(self.palette().text().color())
            painter.drawText(
                QRectF(6.0, center_y - 17.0, left - 16.0, 34.0),
                Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignVCenter,
                f"{item.session_name}\n{item.transaction_count} dowodów",
            )
            self._draw_range(
                painter,
                item.p50_first_response_latency_ns,
                item.p95_first_response_latency_ns,
                center_y - 6.0,
                left,
                width,
                maximum,
                first_pen,
            )
            self._draw_range(
                painter,
                item.p50_final_response_latency_ns,
                item.p95_final_response_latency_ns,
                center_y + 6.0,
                left,
                width,
                maximum,
                final_pen,
            )

        painter.setPen(first_pen)
        painter.drawLine(
            QPointF(left, 26),
            QPointF(left + 26, 26),
        )
        painter.setPen(self.palette().text().color())
        painter.drawText(
            QRectF(left + 31, 15, 90, 20),
            "first",
        )
        painter.setPen(final_pen)
        painter.drawLine(
            QPointF(left + 92, 26),
            QPointF(left + 118, 26),
        )
        painter.setPen(self.palette().text().color())
        painter.drawText(
            QRectF(left + 123, 15, 90, 20),
            "final",
        )

    @staticmethod
    def _draw_range(
        painter: QPainter,
        p50: float | None,
        p95: float | None,
        y: float,
        left: float,
        width: float,
        maximum: float,
        pen: QPen,
    ) -> None:
        if p50 is None or p95 is None:
            return
        x50 = left + width * max(
            0.0,
            min(1.0, float(p50) / maximum),
        )
        x95 = left + width * max(
            0.0,
            min(1.0, float(p95) / maximum),
        )
        painter.setPen(pen)
        painter.drawLine(QPointF(x50, y), QPointF(x95, y))
        painter.drawLine(
            QPointF(x50, y - 5),
            QPointF(x50, y + 5),
        )
        painter.drawLine(
            QPointF(x95, y - 5),
            QPointF(x95, y + 5),
        )


class ComparisonUdsTransactionExplorerView(QWidget):
    """Artifact-backed UDS transaction filtering and protocol correlation."""

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
        self._source_result: UdsLatencyResult | None = None
        self._source_artifact_id = ""
        self._explorer_result: UdsTransactionExplorerResult | None = None
        self._transaction_rows: list[UdsTransactionRecord] = []
        self._selected_record: UdsTransactionRecord | None = None

        root = QVBoxLayout(self)
        description = QLabel(
            "Eksplorator pracuje na trwałym artefakcie Stage 2C2. "
            "Nie skanuje ponownie surowych sesji. Grupowanie dotyczy "
            "zachowanych bounded par dowodowych i wyraźnie ostrzega "
            "o truncation.",
            self,
        )
        description.setWordWrap(True)
        root.addWidget(description)

        filters = QGridLayout()
        self.session_combo = QComboBox(self)
        self.session_combo.setObjectName("udsExplorerSessionCombo")
        self.service_combo = QComboBox(self)
        self.service_combo.setObjectName("udsExplorerServiceCombo")
        self.status_combo = QComboBox(self)
        self.status_combo.setObjectName("udsExplorerStatusCombo")
        self.nrc_combo = QComboBox(self)
        self.nrc_combo.setObjectName("udsExplorerNrcCombo")
        self.grouping_combo = QComboBox(self)
        self.grouping_combo.setObjectName("udsExplorerGroupingCombo")
        for label, value in (
            ("Automatycznie", "auto"),
            ("SID usługi", "service"),
            ("DID", "did"),
            ("Subfunkcja", "subfunction"),
            ("Routine ID", "routine"),
        ):
            self.grouping_combo.addItem(label, value)
        self.search_edit = QLineEdit(self)
        self.search_edit.setObjectName("udsExplorerSearchEdit")
        self.search_edit.setPlaceholderText(
            "payload, nazwa usługi, status, NRC, DID, Routine ID…"
        )
        self.start_time_spin = _optional_spin(
            self,
            "udsExplorerStartTimeSpin",
            " ms",
        )
        self.end_time_spin = _optional_spin(
            self,
            "udsExplorerEndTimeSpin",
            " ms",
        )
        self.minimum_latency_spin = _optional_spin(
            self,
            "udsExplorerMinimumLatencySpin",
            " ms",
        )
        self.maximum_latency_spin = _optional_spin(
            self,
            "udsExplorerMaximumLatencySpin",
            " ms",
        )

        filters.addWidget(QLabel("Sesja:", self), 0, 0)
        filters.addWidget(self.session_combo, 0, 1)
        filters.addWidget(QLabel("SID:", self), 0, 2)
        filters.addWidget(self.service_combo, 0, 3)
        filters.addWidget(QLabel("Status:", self), 0, 4)
        filters.addWidget(self.status_combo, 0, 5)
        filters.addWidget(QLabel("NRC:", self), 0, 6)
        filters.addWidget(self.nrc_combo, 0, 7)
        filters.addWidget(QLabel("Grupowanie:", self), 1, 0)
        filters.addWidget(self.grouping_combo, 1, 1)
        filters.addWidget(QLabel("Od czasu:", self), 1, 2)
        filters.addWidget(self.start_time_spin, 1, 3)
        filters.addWidget(QLabel("Do czasu:", self), 1, 4)
        filters.addWidget(self.end_time_spin, 1, 5)
        filters.addWidget(QLabel("Final min:", self), 1, 6)
        filters.addWidget(self.minimum_latency_spin, 1, 7)
        filters.addWidget(QLabel("Final max:", self), 2, 0)
        filters.addWidget(self.maximum_latency_spin, 2, 1)
        filters.addWidget(QLabel("Szukaj:", self), 2, 2)
        filters.addWidget(self.search_edit, 2, 3, 1, 5)
        root.addLayout(filters)

        actions = QHBoxLayout()
        self.load_button = QPushButton(
            "Wczytaj najnowszy artefakt UDS",
            self,
        )
        self.load_button.setObjectName("loadUdsExplorerButton")
        self.load_button.clicked.connect(self.load_latest)
        actions.addWidget(self.load_button)
        self.apply_button = QPushButton("Zastosuj filtry", self)
        self.apply_button.setObjectName(
            "applyUdsExplorerFiltersButton"
        )
        self.apply_button.clicked.connect(self.apply_filters)
        actions.addWidget(self.apply_button)
        self.reset_button = QPushButton("Wyczyść filtry", self)
        self.reset_button.setObjectName(
            "resetUdsExplorerFiltersButton"
        )
        self.reset_button.clicked.connect(self.reset_filters)
        actions.addWidget(self.reset_button)
        self.export_transactions_button = QPushButton(
            "Eksportuj transakcje CSV",
            self,
        )
        self.export_transactions_button.setObjectName(
            "exportUdsExplorerTransactionsButton"
        )
        self.export_transactions_button.clicked.connect(
            lambda: self.export_transactions()
        )
        actions.addWidget(self.export_transactions_button)
        self.export_groups_button = QPushButton(
            "Eksportuj grupy CSV",
            self,
        )
        self.export_groups_button.setObjectName(
            "exportUdsExplorerGroupsButton"
        )
        self.export_groups_button.clicked.connect(
            lambda: self.export_groups()
        )
        actions.addWidget(self.export_groups_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.status_label = QLabel(
            "Wczytaj trwały artefakt z karty Latencja UDS.",
            self,
        )
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        root.addWidget(splitter, 1)

        upper = QWidget(splitter)
        upper_layout = QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        self.chart = UdsLatencyDistributionChart(upper)
        self.chart.setObjectName("udsExplorerLatencyChart")
        upper_layout.addWidget(self.chart)
        summary_tabs = QTabWidget(upper)
        self.group_table = QTableWidget(0, 12, summary_tabs)
        self.group_table.setObjectName("udsExplorerGroupTable")
        self.group_table.setHorizontalHeaderLabels(
            [
                "Sesja",
                "Grupa",
                "Liczba",
                "Pozytywne",
                "Negatywne",
                "Timeout",
                "Koniec logu",
                "0x78 trans.",
                "0x78 razem",
                "Skuteczność",
                "p50 final [ms]",
                "p95 final [ms]",
            ]
        )
        _configure_table(self.group_table)
        summary_tabs.addTab(
            self.group_table,
            "Grupy protokołowe",
        )
        self.comparison_table = QTableWidget(
            0,
            10,
            summary_tabs,
        )
        self.comparison_table.setObjectName(
            "udsExplorerComparisonTable"
        )
        self.comparison_table.setHorizontalHeaderLabels(
            [
                "Sesja",
                "Grupa",
                "Liczba Δ",
                "Skuteczność Δ [pp]",
                "p50 first Δ [%]",
                "p50 final Δ [%]",
                "p95 final Δ [%]",
                "Timeout Δ",
                "Negatywne Δ",
                "0x78 Δ",
            ]
        )
        _configure_table(self.comparison_table)
        summary_tabs.addTab(
            self.comparison_table,
            "Porównanie z bazą",
        )
        upper_layout.addWidget(summary_tabs, 1)

        lower = QWidget(splitter)
        lower_layout = QVBoxLayout(lower)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_splitter = QSplitter(
            Qt.Orientation.Horizontal,
            lower,
        )
        lower_layout.addWidget(lower_splitter, 1)
        self.transaction_table = QTableWidget(
            0,
            12,
            lower_splitter,
        )
        self.transaction_table.setObjectName(
            "udsExplorerTransactionTable"
        )
        self.transaction_table.setHorizontalHeaderLabels(
            [
                "Sesja",
                "Czas [ms]",
                "Row",
                "SID",
                "Usługa / korelacja",
                "Status",
                "NRC",
                "0x78",
                "First [ms]",
                "Final [ms]",
                "Request payload",
                "Final payload",
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
        lower_splitter.addWidget(self.transaction_table)
        self.details = QPlainTextEdit(lower_splitter)
        self.details.setObjectName(
            "udsExplorerTransactionDetails"
        )
        self.details.setReadOnly(True)
        self.details.setPlaceholderText(
            "Zaznacz transakcję, aby zobaczyć payloady."
        )
        lower_splitter.addWidget(self.details)
        lower_splitter.setStretchFactor(0, 3)
        lower_splitter.setStretchFactor(1, 2)

        navigation = QHBoxLayout()
        self.open_request_button = QPushButton(
            "Otwórz żądanie",
            lower,
        )
        self.open_request_button.setObjectName(
            "openUdsExplorerRequestButton"
        )
        self.open_request_button.clicked.connect(
            self.open_request
        )
        navigation.addWidget(self.open_request_button)
        self.open_first_button = QPushButton(
            "Otwórz pierwszą odpowiedź",
            lower,
        )
        self.open_first_button.setObjectName(
            "openUdsExplorerFirstButton"
        )
        self.open_first_button.clicked.connect(
            self.open_first_response
        )
        navigation.addWidget(self.open_first_button)
        self.open_final_button = QPushButton(
            "Otwórz odpowiedź końcową",
            lower,
        )
        self.open_final_button.setObjectName(
            "openUdsExplorerFinalButton"
        )
        self.open_final_button.clicked.connect(
            self.open_final_response
        )
        navigation.addWidget(self.open_final_button)
        navigation.addStretch(1)
        lower_layout.addLayout(navigation)

        splitter.addWidget(upper)
        splitter.addWidget(lower)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        self._update_buttons()
        QTimer.singleShot(0, self.load_latest)

    @Slot()
    def load_latest(self) -> None:
        generation = self._next_generation()
        task = _ExplorerLoadTask(
            generation,
            self.service,
            self.comparison_set,
        )
        task.signals.completed.connect(self._task_completed)
        task.signals.failed.connect(self._task_failed)
        task.signals.cancelled.connect(self._task_cancelled)
        task.signals.finished.connect(self._task_finished)
        self._tasks[generation] = task
        self._set_running(True)
        self.status_label.setText(
            "Wczytuję trwały artefakt Stage 2C2…"
        )
        QThreadPool.globalInstance().start(task)

    def set_source_result(
        self,
        result: UdsLatencyResult,
        artifact_id: str,
    ) -> None:
        self._source_result = result
        self._source_artifact_id = str(artifact_id)
        self._populate_filter_catalogs()
        self.apply_filters()

    @Slot()
    def apply_filters(self) -> None:
        source = self._source_result
        if source is None:
            self.status_label.setText(
                "Brak źródłowego artefaktu. Najpierw uruchom analizę "
                "w karcie Latencja UDS, a następnie wczytaj najnowszy "
                "artefakt."
            )
            return
        try:
            result = build_uds_transaction_explorer(
                source,
                source_artifact_id=self._source_artifact_id,
                filter_specification=self._current_filter(),
                grouping_mode=str(
                    self.grouping_combo.currentData() or "auto"
                ),
            )
        except ValueError as exc:
            self.status_label.setText(
                f"Nieprawidłowe filtry: {exc}"
            )
            return
        self._explorer_result = result
        self._populate_result()
        status = (
            f"Widoczne transakcje: "
            f"{len(result.visible_transactions)} z "
            f"{result.source_transaction_count} zachowanych dowodów; "
            f"artefakt {result.source_artifact_id or 'bez ID'}."
        )
        if result.warnings:
            status += " " + " ".join(result.warnings)
        self.status_label.setText(status)

    @Slot()
    def reset_filters(self) -> None:
        for combo in (
            self.session_combo,
            self.service_combo,
            self.status_combo,
            self.nrc_combo,
        ):
            combo.setCurrentIndex(0)
        self.grouping_combo.setCurrentIndex(0)
        self.search_edit.clear()
        for spin in (
            self.start_time_spin,
            self.end_time_spin,
            self.minimum_latency_spin,
            self.maximum_latency_spin,
        ):
            spin.setValue(-1.0)
        self.apply_filters()

    def cancel_all(self) -> None:
        self._generation += 1
        for task in tuple(self._tasks.values()):
            cancel = getattr(task, "cancel", None)
            if callable(cancel):
                cancel()
        self._tasks.clear()
        self._set_running(False)

    def export_transactions(
        self,
        path: str | Path | None = None,
    ) -> Path | None:
        result = self._explorer_result
        if result is None:
            self.status_label.setText(
                "Brak widocznych danych do eksportu."
            )
            return None
        destination = self._resolve_export_path(
            path,
            "Eksport transakcji UDS",
            "uds-transactions.csv",
        )
        if destination is None:
            return None
        saved = export_transactions_csv(
            destination,
            result.visible_transactions,
        )
        self.status_label.setText(
            f"Zapisano transakcje CSV: {saved}"
        )
        return saved

    def export_groups(
        self,
        path: str | Path | None = None,
    ) -> Path | None:
        result = self._explorer_result
        if result is None:
            self.status_label.setText(
                "Brak grup do eksportu."
            )
            return None
        destination = self._resolve_export_path(
            path,
            "Eksport grup UDS",
            "uds-transaction-groups.csv",
        )
        if destination is None:
            return None
        saved = export_groups_csv(
            destination,
            result.groups,
        )
        self.status_label.setText(
            f"Zapisano grupy CSV: {saved}"
        )
        return saved

    def _resolve_export_path(
        self,
        path: str | Path | None,
        title: str,
        suggested_name: str,
    ) -> Path | None:
        if path is not None:
            return Path(path)
        selected, _ = QFileDialog.getSaveFileName(
            self,
            title,
            suggested_name,
            "CSV (*.csv)",
        )
        return None if not selected else Path(selected)

    def _next_generation(self) -> int:
        self._generation += 1
        for task in tuple(self._tasks.values()):
            cancel = getattr(task, "cancel", None)
            if callable(cancel):
                cancel()
        return self._generation

    @Slot(int, object)
    def _task_completed(
        self,
        generation: int,
        value: object,
    ) -> None:
        if generation != self._generation:
            return
        if isinstance(value, StoredUdsLatency):
            self.set_source_result(
                value.result,
                value.artifact.id,
            )
            self.status_label.setText(
                self.status_label.text()
                + " Wczytano bez ponownego skanowania surowych sesji."
            )
        elif value is None:
            self._source_result = None
            self._source_artifact_id = ""
            self._explorer_result = None
            self._clear_result()
            self.status_label.setText(
                "Nie znaleziono zgodnego artefaktu Stage 2C2. "
                "Uruchom najpierw kartę Latencja UDS."
            )
        else:
            self._task_failed(
                generation,
                "Nieobsługiwany wynik eksploratora.",
            )

    @Slot(int, str)
    def _task_failed(
        self,
        generation: int,
        error: str,
    ) -> None:
        if generation != self._generation:
            return
        self.status_label.setText(
            f"Nie udało się wczytać eksploratora UDS: {error}"
        )

    @Slot(int)
    def _task_cancelled(self, generation: int) -> None:
        if generation == self._generation:
            self.status_label.setText(
                "Anulowano wczytywanie eksploratora UDS."
            )

    @Slot(int)
    def _task_finished(self, generation: int) -> None:
        self._tasks.pop(generation, None)
        if generation == self._generation:
            self._set_running(False)

    def _set_running(self, running: bool) -> None:
        self.load_button.setEnabled(not running)
        self.apply_button.setEnabled(
            not running and self._source_result is not None
        )
        self.reset_button.setEnabled(
            not running and self._source_result is not None
        )

    def _populate_filter_catalogs(self) -> None:
        result = self._source_result
        if result is None:
            return
        selected = {
            "session": self.session_combo.currentData(),
            "service": self.service_combo.currentData(),
            "status": self.status_combo.currentData(),
            "nrc": self.nrc_combo.currentData(),
        }
        self.session_combo.clear()
        self.session_combo.addItem("Wszystkie sesje", "")
        for session in result.sessions:
            self.session_combo.addItem(
                session.session_name,
                session.session_id,
            )

        services: dict[int, str] = {}
        statuses: set[str] = set()
        nrcs: set[int] = set()
        for session in result.sessions:
            for transaction in session.transaction_evidence:
                services[
                    transaction.request_service_id
                ] = transaction.request_service_name
                statuses.add(transaction.status)
                if (
                    transaction.final_negative_response_code
                    is not None
                ):
                    nrcs.add(
                        transaction.final_negative_response_code
                    )

        self.service_combo.clear()
        self.service_combo.addItem("Wszystkie SID", None)
        for sid, name in sorted(services.items()):
            self.service_combo.addItem(
                f"0x{sid:02X} {name}",
                sid,
            )
        self.status_combo.clear()
        self.status_combo.addItem(
            "Wszystkie statusy",
            "",
        )
        for status in sorted(statuses):
            self.status_combo.addItem(
                _status_text(status),
                status,
            )
        self.nrc_combo.clear()
        self.nrc_combo.addItem("Wszystkie NRC", None)
        for nrc in sorted(nrcs):
            self.nrc_combo.addItem(
                f"0x{nrc:02X} {uds_nrc_name(nrc)}",
                nrc,
            )
        _restore_combo(
            self.session_combo,
            selected["session"],
        )
        _restore_combo(
            self.service_combo,
            selected["service"],
        )
        _restore_combo(
            self.status_combo,
            selected["status"],
        )
        _restore_combo(
            self.nrc_combo,
            selected["nrc"],
        )

    def _current_filter(self) -> UdsExplorerFilter:
        session = self.session_combo.currentData()
        service = self.service_combo.currentData()
        status = self.status_combo.currentData()
        nrc = self.nrc_combo.currentData()
        return UdsExplorerFilter(
            session_ids=(
                ()
                if not session
                else (str(session),)
            ),
            service_ids=(
                ()
                if service is None
                else (int(service),)
            ),
            statuses=(
                ()
                if not status
                else (str(status),)
            ),
            negative_response_codes=(
                ()
                if nrc is None
                else (int(nrc),)
            ),
            text_query=self.search_edit.text(),
            start_time_ms=_optional_spin_value(
                self.start_time_spin
            ),
            end_time_ms=_optional_spin_value(
                self.end_time_spin
            ),
            minimum_final_latency_ms=(
                _optional_spin_value(
                    self.minimum_latency_spin
                )
            ),
            maximum_final_latency_ms=(
                _optional_spin_value(
                    self.maximum_latency_spin
                )
            ),
        )

    def _populate_result(self) -> None:
        result = self._explorer_result
        if result is None:
            self._clear_result()
            return
        self.chart.set_distributions(result.distributions)
        self.group_table.setRowCount(len(result.groups))
        for row, item in enumerate(result.groups):
            values = [
                item.session_name,
                item.group_label,
                str(item.transaction_count),
                str(item.positive_response_count),
                str(item.negative_response_count),
                str(item.timeout_count),
                str(item.capture_ended_count),
                str(item.response_pending_transaction_count),
                str(item.response_pending_count),
                _percent(item.completion_rate_percent),
                _ms(item.p50_final_response_latency_ns),
                _ms(item.p95_final_response_latency_ns),
            ]
            _set_row(self.group_table, row, values)

        self.comparison_table.setRowCount(
            len(result.comparisons)
        )
        for row, item in enumerate(result.comparisons):
            values = [
                item.session_name,
                item.group_label,
                f"{item.transaction_count_delta:+d}",
                _signed(
                    item.completion_rate_delta_percentage_points,
                    " pp",
                ),
                _signed(
                    item.p50_first_latency_delta_percent,
                    "%",
                ),
                _signed(
                    item.p50_final_latency_delta_percent,
                    "%",
                ),
                _signed(
                    item.p95_final_latency_delta_percent,
                    "%",
                ),
                f"{item.timeout_count_delta:+d}",
                f"{item.negative_response_count_delta:+d}",
                f"{item.response_pending_count_delta:+d}",
            ]
            _set_row(self.comparison_table, row, values)

        self._transaction_rows = list(
            result.visible_transactions
        )
        self._selected_record = None
        self.transaction_table.setRowCount(
            len(self._transaction_rows)
        )
        for row, record in enumerate(self._transaction_rows):
            item = record.transaction
            values = [
                item.session_name,
                f"{record.relative_request_time_ms:.3f}",
                str(item.request.first_source_row + 1),
                f"0x{item.request_service_id:02X}",
                record.automatic_correlation_label,
                _status_text(item.status),
                (
                    "—"
                    if item.final_negative_response_code is None
                    else f"0x{item.final_negative_response_code:02X}"
                ),
                str(item.response_pending_count),
                _ms(item.first_response_latency_ns),
                _ms(item.final_response_latency_ns),
                item.request.payload_hex,
                (
                    "—"
                    if item.final_response is None
                    else item.final_response.payload_hex
                ),
            ]
            _set_row(self.transaction_table, row, values)
        self.details.clear()
        self._update_buttons()

    def _clear_result(self) -> None:
        self.chart.set_distributions(())
        self.group_table.setRowCount(0)
        self.comparison_table.setRowCount(0)
        self.transaction_table.setRowCount(0)
        self.details.clear()
        self._transaction_rows = []
        self._selected_record = None
        self._update_buttons()

    @Slot()
    def _transaction_selection_changed(self) -> None:
        rows = self.transaction_table.selectionModel().selectedRows()
        if not rows:
            self._selected_record = None
            self.details.clear()
        else:
            index = rows[0].row()
            self._selected_record = (
                self._transaction_rows[index]
                if 0 <= index < len(self._transaction_rows)
                else None
            )
            self.details.setPlainText(
                ""
                if self._selected_record is None
                else format_transaction_details(
                    self._selected_record
                )
            )
        self._update_buttons()

    def _update_buttons(self) -> None:
        selected = self._selected_record
        has_result = self._explorer_result is not None
        self.export_transactions_button.setEnabled(has_result)
        self.export_groups_button.setEnabled(has_result)
        self.open_request_button.setEnabled(
            selected is not None
        )
        self.open_first_button.setEnabled(
            selected is not None
            and selected.transaction.first_response is not None
        )
        self.open_final_button.setEnabled(
            selected is not None
            and selected.transaction.final_response is not None
        )

    @Slot()
    def open_request(self) -> None:
        selected = self._selected_record
        if selected is None:
            return
        message = selected.transaction.request
        self.source_row_requested.emit(
            selected.transaction.session_id,
            message.first_source_row,
            message.message_key,
        )

    @Slot()
    def open_first_response(self) -> None:
        selected = self._selected_record
        if (
            selected is None
            or selected.transaction.first_response is None
        ):
            return
        message = selected.transaction.first_response
        self.source_row_requested.emit(
            selected.transaction.session_id,
            message.first_source_row,
            message.message_key,
        )

    @Slot()
    def open_final_response(self) -> None:
        selected = self._selected_record
        if (
            selected is None
            or selected.transaction.final_response is None
        ):
            return
        message = selected.transaction.final_response
        self.source_row_requested.emit(
            selected.transaction.session_id,
            message.first_source_row,
            message.message_key,
        )


def _optional_spin(
    parent: QWidget,
    object_name: str,
    suffix: str,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox(parent)
    spin.setObjectName(object_name)
    spin.setRange(-1.0, 1_000_000_000.0)
    spin.setDecimals(3)
    spin.setSingleStep(10.0)
    spin.setSpecialValueText("bez limitu")
    spin.setSuffix(suffix)
    spin.setValue(-1.0)
    return spin


def _optional_spin_value(
    spin: QDoubleSpinBox,
) -> float | None:
    return (
        None
        if spin.value() < 0
        else float(spin.value())
    )


def _restore_combo(
    combo: QComboBox,
    value: Any,
) -> None:
    index = combo.findData(value)
    combo.setCurrentIndex(index if index >= 0 else 0)


def _configure_table(table: QTableWidget) -> None:
    table.setEditTriggers(
        QAbstractItemView.EditTrigger.NoEditTriggers
    )
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents
    )
    header.setStretchLastSection(True)


def _set_row(
    table: QTableWidget,
    row: int,
    values: list[str],
) -> None:
    for column, value in enumerate(values):
        table.setItem(
            row,
            column,
            QTableWidgetItem(value),
        )


def _ms(value: float | int | None) -> str:
    return (
        "—"
        if value is None
        else f"{float(value) / 1_000_000.0:.3f}"
    )


def _percent(value: float | None) -> str:
    return (
        "—"
        if value is None
        else f"{value:.1f}%"
    )


def _signed(
    value: float | None,
    suffix: str,
) -> str:
    return (
        "—"
        if value is None
        else f"{value:+.2f}{suffix}"
    )


def _status_text(value: str) -> str:
    return {
        "positive-response": "pozytywna",
        "negative-response": "negatywna",
        "timeout": "timeout",
        "capture-ended": "koniec logu",
        "suppressed-no-response": "bez odpowiedzi (suppress)",
    }.get(value, value)


__all__ = [
    "ComparisonUdsTransactionExplorerView",
    "UdsLatencyDistributionChart",
]
