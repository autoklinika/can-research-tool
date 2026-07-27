from __future__ import annotations

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

from app.comparison_interframe_timing import (
    ComparisonInterFrameTimingService,
    DEFAULT_GAP_FACTOR,
    InterFrameGapEvidence,
    InterFrameTimingCancelled,
    InterFrameTimingExecutionResult,
    InterFrameTimingResult,
    StoredInterFrameTiming,
)
from app.domain import ComparisonSet
from app.extensions import CancellationToken, ExtensionCancelled
from app.project import CrtProject


class _TimingSignals(QObject):
    progress = Signal(int, int, int, str)
    completed = Signal(int, object)
    failed = Signal(int, str)
    cancelled = Signal(int)
    finished = Signal(int)


class _TimingTask(QRunnable):
    def __init__(
        self,
        generation: int,
        service: ComparisonInterFrameTimingService,
        comparison_set: ComparisonSet,
        message_key: str,
        gap_factor: float,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.generation = generation
        self.service = service
        self.comparison_set = comparison_set
        self.message_key = message_key
        self.gap_factor = gap_factor
        self.cancellation = CancellationToken()
        self.signals = _TimingSignals()

    def cancel(self) -> None:
        self.cancellation.cancel()

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.run_and_save(
                self.comparison_set,
                self.message_key,
                gap_factor=self.gap_factor,
                cancellation=self.cancellation,
                progress_callback=self._progress,
            )
        except (InterFrameTimingCancelled, ExtensionCancelled):
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


class _TimingLoadTask(QRunnable):
    def __init__(
        self,
        generation: int,
        service: ComparisonInterFrameTimingService,
        comparison_set: ComparisonSet,
        message_key: str,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.generation = generation
        self.service = service
        self.comparison_set = comparison_set
        self.message_key = message_key
        self.cancellation = CancellationToken()
        self.signals = _TimingSignals()

    def cancel(self) -> None:
        self.cancellation.cancel()

    @Slot()
    def run(self) -> None:
        try:
            stored = self.service.load_latest_compatible(
                self.comparison_set,
                message_key=self.message_key,
                should_cancel=lambda: self.cancellation.is_cancelled,
            )
            self.cancellation.raise_if_cancelled()
        except (InterFrameTimingCancelled, ExtensionCancelled):
            self.signals.cancelled.emit(self.generation)
        except Exception as exc:  # pragma: no cover - surfaced through GUI
            self.signals.failed.emit(self.generation, str(exc))
        else:
            self.signals.completed.emit(self.generation, stored)
        finally:
            self.signals.finished.emit(self.generation)


class InterFrameTimingChart(QWidget):
    """Dependency-free percentile chart for every compared session."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._result: InterFrameTimingResult | None = None
        self.setMinimumHeight(190)

    def set_result(self, result: InterFrameTimingResult | None) -> None:
        self._result = result
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        result = self._result
        if result is None or not result.sessions:
            painter.setPen(self.palette().text().color())
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Brak danych timingowych",
            )
            return

        values = [
            value
            for session in result.sessions
            for value in (
                session.p05_interval_ns,
                session.p95_interval_ns,
            )
            if value is not None
        ]
        if not values:
            painter.setPen(self.palette().text().color())
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Za mało wystąpień wybranego klucza",
            )
            return

        maximum = max(values)
        minimum = min(0.0, min(values))
        if maximum <= minimum:
            maximum = minimum + 1.0

        left = 190.0
        right = 24.0
        top = 28.0
        bottom = 28.0
        width = max(1.0, self.width() - left - right)
        lane_height = max(
            28.0,
            (self.height() - top - bottom) / len(result.sessions),
        )

        painter.setPen(self.palette().text().color())
        painter.drawText(
            QRectF(left, 2.0, width, 22.0),
            Qt.AlignmentFlag.AlignCenter,
            "Rozkład odstępów p05–p95 [ms]",
        )
        axis_y = self.height() - bottom + 4.0
        painter.drawLine(
            QPointF(left, axis_y),
            QPointF(left + width, axis_y),
        )
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            x = left + width * fraction
            value_ms = (
                minimum + (maximum - minimum) * fraction
            ) / 1_000_000.0
            painter.drawLine(
                QPointF(x, axis_y - 4),
                QPointF(x, axis_y + 4),
            )
            painter.drawText(
                QRectF(x - 35, axis_y + 4, 70, 18),
                Qt.AlignmentFlag.AlignCenter,
                f"{value_ms:.3f}",
            )

        for index, session in enumerate(result.sessions):
            center_y = top + lane_height * (index + 0.5)
            painter.drawText(
                QRectF(8.0, center_y - 11.0, left - 18.0, 22.0),
                Qt.AlignmentFlag.AlignVCenter
                | Qt.AlignmentFlag.AlignRight,
                session.session_name,
            )
            if (
                session.p05_interval_ns is None
                or session.p95_interval_ns is None
            ):
                continue
            x05 = _scale(
                session.p05_interval_ns,
                minimum,
                maximum,
                left,
                width,
            )
            x25 = _scale(
                session.p25_interval_ns or session.p05_interval_ns,
                minimum,
                maximum,
                left,
                width,
            )
            x50 = _scale(
                session.median_interval_ns or session.p05_interval_ns,
                minimum,
                maximum,
                left,
                width,
            )
            x75 = _scale(
                session.p75_interval_ns or session.p95_interval_ns,
                minimum,
                maximum,
                left,
                width,
            )
            x95 = _scale(
                session.p95_interval_ns,
                minimum,
                maximum,
                left,
                width,
            )
            painter.setPen(
                QPen(self.palette().highlight().color(), 2.0)
            )
            painter.drawLine(
                QPointF(x05, center_y),
                QPointF(x95, center_y),
            )
            painter.drawRect(
                QRectF(
                    x25,
                    center_y - 7.0,
                    max(1.0, x75 - x25),
                    14.0,
                )
            )
            painter.drawLine(
                QPointF(x50, center_y - 10.0),
                QPointF(x50, center_y + 10.0),
            )
            painter.drawLine(
                QPointF(x05, center_y - 4.0),
                QPointF(x05, center_y + 4.0),
            )
            painter.drawLine(
                QPointF(x95, center_y - 4.0),
                QPointF(x95, center_y + 4.0),
            )


class ComparisonInterFrameTimingView(QWidget):
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
        self.service = ComparisonInterFrameTimingService(project)
        self._generation = 0
        self._tasks: dict[int, QRunnable] = {}
        self._result: InterFrameTimingResult | None = None
        self._selected_evidence: InterFrameGapEvidence | None = None
        self._loaded_artifact_id = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Klucz wiadomości:", self))
        self.key_edit = QLineEdit(self)
        self.key_edit.setObjectName("interFrameTimingMessageKey")
        self.key_edit.setPlaceholderText(
            "np. 0:EXT:1AFFB680:data"
        )
        controls.addWidget(self.key_edit, 1)
        controls.addWidget(
            QLabel("Przerwa ≥ mediana ×", self)
        )
        self.gap_factor_spin = QDoubleSpinBox(self)
        self.gap_factor_spin.setObjectName(
            "interFrameTimingGapFactor"
        )
        self.gap_factor_spin.setRange(1.1, 100.0)
        self.gap_factor_spin.setDecimals(1)
        self.gap_factor_spin.setSingleStep(0.5)
        self.gap_factor_spin.setValue(DEFAULT_GAP_FACTOR)
        controls.addWidget(self.gap_factor_spin)
        self.run_button = QPushButton("Analizuj timing", self)
        self.run_button.setObjectName("runInterFrameTiming")
        self.run_button.clicked.connect(self.start_analysis)
        controls.addWidget(self.run_button)
        self.load_button = QPushButton("Wczytaj ostatni", self)
        self.load_button.setObjectName("loadInterFrameTiming")
        self.load_button.clicked.connect(self.load_latest)
        controls.addWidget(self.load_button)
        self.cancel_button = QPushButton("Anuluj", self)
        self.cancel_button.setObjectName("cancelInterFrameTiming")
        self.cancel_button.clicked.connect(self.cancel_all)
        controls.addWidget(self.cancel_button)
        root.addLayout(controls)

        self.progress = QProgressBar(self)
        self.progress.setObjectName("interFrameTimingProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)
        self.status_label = QLabel(
            "Podaj dokładny klucz wiadomości. Analiza jest pasywna "
            "i nie wysyła ramek CAN.",
            self,
        )
        self.status_label.setObjectName("interFrameTimingStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(self.status_label)

        self.chart = InterFrameTimingChart(self)
        self.chart.setObjectName("interFrameTimingChart")
        root.addWidget(self.chart)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.sessions_table = _table(
            splitter,
            "interFrameTimingSessions",
            (
                "Sesja",
                "Wystąpienia",
                "Odstępy",
                "Średnia [ms]",
                "Mediana [ms]",
                "p95 [ms]",
                "Jitter p95-p05 [ms]",
                "RMS jitter [ms]",
                "CV [%]",
                "Częstotliwość [Hz]",
                "Przerwy",
            ),
        )
        self.comparisons_table = _table(
            splitter,
            "interFrameTimingComparisons",
            (
                "Sesja",
                "Δ średniej [%]",
                "Δ mediany [%]",
                "Δ jitteru [%]",
                "Δ częstotliwości [%]",
                "Δ CV [pp]",
                "Δ przerw",
            ),
        )
        evidence_page = QWidget(splitter)
        evidence_layout = QVBoxLayout(evidence_page)
        evidence_layout.setContentsMargins(0, 0, 0, 0)
        evidence_actions = QHBoxLayout()
        evidence_actions.addWidget(
            QLabel("Najdłuższe wykryte przerwy:", evidence_page)
        )
        evidence_actions.addStretch(1)
        self.open_previous_button = QPushButton(
            "Otwórz początek odstępu",
            evidence_page,
        )
        self.open_previous_button.setObjectName(
            "openInterFrameGapStart"
        )
        self.open_previous_button.clicked.connect(
            self._open_previous
        )
        evidence_actions.addWidget(self.open_previous_button)
        self.open_current_button = QPushButton(
            "Otwórz koniec odstępu",
            evidence_page,
        )
        self.open_current_button.setObjectName(
            "openInterFrameGapEnd"
        )
        self.open_current_button.clicked.connect(
            self._open_current
        )
        evidence_actions.addWidget(self.open_current_button)
        evidence_layout.addLayout(evidence_actions)
        self.evidence_table = _table(
            evidence_page,
            "interFrameTimingEvidence",
            (
                "Sesja",
                "Poprzednia ramka",
                "Bieżąca ramka",
                "Odstęp [ms]",
                "Próg [ms]",
                "× mediana",
            ),
        )
        self.evidence_table.itemSelectionChanged.connect(
            self._evidence_selected
        )
        evidence_layout.addWidget(self.evidence_table)
        splitter.addWidget(self.sessions_table)
        splitter.addWidget(self.comparisons_table)
        splitter.addWidget(evidence_page)
        splitter.setSizes((230, 170, 260))
        root.addWidget(splitter, 1)

        self._set_busy(False)
        QTimer.singleShot(0, self.load_latest)

    @Slot()
    def start_analysis(self) -> None:
        if self._tasks:
            return
        key = self.key_edit.text().strip()
        if not key:
            self.status_label.setText(
                "Podaj dokładny klucz wiadomości."
            )
            return
        self._generation += 1
        generation = self._generation
        task = _TimingTask(
            generation,
            self.service,
            self.comparison_set,
            key,
            self.gap_factor_spin.value(),
        )
        task.signals.progress.connect(self._progress)
        task.signals.completed.connect(self._analysis_ready)
        task.signals.failed.connect(self._failed)
        task.signals.cancelled.connect(self._cancelled)
        task.signals.finished.connect(self._finished)
        self._tasks[generation] = task
        self._set_busy(True)
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)
        self.status_label.setText(
            "Rozpoczynam dwuprzebiegową analizę timingów…"
        )
        QThreadPool.globalInstance().start(task)

    @Slot()
    def load_latest(self) -> None:
        if self._tasks:
            return
        self._generation += 1
        generation = self._generation
        task = _TimingLoadTask(
            generation,
            self.service,
            self.comparison_set,
            self.key_edit.text().strip(),
        )
        task.signals.completed.connect(self._load_ready)
        task.signals.failed.connect(self._failed)
        task.signals.cancelled.connect(self._cancelled)
        task.signals.finished.connect(self._finished)
        self._tasks[generation] = task
        self._set_busy(True)
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)
        self.status_label.setText(
            "Szukam ostatniego zgodnego artefaktu timingów…"
        )
        QThreadPool.globalInstance().start(task)

    @Slot()
    def cancel_all(self) -> None:
        self._generation += 1
        for task in self._tasks.values():
            cancel = getattr(task, "cancel", None)
            if callable(cancel):
                cancel()
        if self._tasks:
            self.status_label.setText(
                "Anulowanie analizy timingów…"
            )

    @Slot(int, int, int, str)
    def _progress(
        self,
        generation: int,
        current: int,
        total: int,
        message: str,
    ) -> None:
        if generation != self._generation:
            return
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
            self.progress.setFormat("%p%")
        else:
            self.progress.setRange(0, 0)
        self.status_label.setText(message)

    @Slot(int, object)
    def _analysis_ready(
        self,
        generation: int,
        value: object,
    ) -> None:
        if generation != self._generation:
            return
        if not isinstance(value, InterFrameTimingExecutionResult):
            self._failed(
                generation,
                "Niepoprawny wynik analizy timingów.",
            )
            return
        self._loaded_artifact_id = value.artifact.id
        self._apply_result(value.result)
        self.status_label.setText(
            "Analiza zakończona. Zapisano wersjonowany artefakt "
            "timingów i jitteru."
        )

    @Slot(int, object)
    def _load_ready(
        self,
        generation: int,
        value: object,
    ) -> None:
        if generation != self._generation:
            return
        if value is None:
            self.status_label.setText(
                "Brak zapisanego zgodnego artefaktu timingów."
            )
            return
        if not isinstance(value, StoredInterFrameTiming):
            self._failed(
                generation,
                "Niepoprawny zapisany wynik timingów.",
            )
            return
        self._loaded_artifact_id = value.artifact.id
        self.key_edit.setText(value.result.message_key)
        self.gap_factor_spin.setValue(value.result.gap_factor)
        self._apply_result(value.result)
        self.status_label.setText(
            "Wczytano zapisany wynik timingów bez ponownego "
            "skanowania sesji."
        )

    @Slot(int, str)
    def _failed(
        self,
        generation: int,
        error: str,
    ) -> None:
        if generation != self._generation:
            return
        self.status_label.setText(
            f"Analiza timingów nie powiodła się: {error}"
        )

    @Slot(int)
    def _cancelled(self, generation: int) -> None:
        if generation != self._generation:
            return
        self.status_label.setText(
            "Analiza timingów została anulowana."
        )

    @Slot(int)
    def _finished(self, generation: int) -> None:
        self._tasks.pop(generation, None)
        if not self._tasks:
            self._set_busy(False)

    def _apply_result(self, result: InterFrameTimingResult) -> None:
        self._result = result
        self._selected_evidence = None
        self.chart.set_result(result)
        self.key_edit.setText(result.message_key)
        self.gap_factor_spin.setValue(result.gap_factor)

        self.sessions_table.setRowCount(len(result.sessions))
        for row, item in enumerate(result.sessions):
            _set_row(
                self.sessions_table,
                row,
                (
                    item.session_name,
                    item.occurrence_count,
                    item.positive_interval_count,
                    _milliseconds(item.mean_interval_ns),
                    _milliseconds(item.median_interval_ns),
                    _milliseconds(item.p95_interval_ns),
                    _milliseconds(item.jitter_p95_p05_ns),
                    _milliseconds(
                        item.jitter_rms_from_median_ns
                    ),
                    _number(
                        item.coefficient_of_variation_percent
                    ),
                    _number(item.nominal_frequency_hz),
                    item.gap_count,
                ),
            )

        self.comparisons_table.setRowCount(
            len(result.comparisons)
        )
        for row, item in enumerate(result.comparisons):
            _set_row(
                self.comparisons_table,
                row,
                (
                    item.session_name,
                    _number(item.mean_interval_delta_percent),
                    _number(item.median_interval_delta_percent),
                    _number(item.jitter_delta_percent),
                    _number(item.frequency_delta_percent),
                    _number(
                        item.coefficient_of_variation_delta_percentage_points
                    ),
                    item.gap_count_delta,
                ),
            )

        evidence = [
            item
            for session in result.sessions
            for item in session.gap_evidence
        ]
        evidence.sort(
            key=lambda item: (
                -item.interval_ns,
                item.session_name,
                item.current_source_row,
            )
        )
        self.evidence_table.setRowCount(len(evidence))
        for row, item in enumerate(evidence):
            _set_row(
                self.evidence_table,
                row,
                (
                    item.session_name,
                    item.previous_source_row + 1,
                    item.current_source_row + 1,
                    _milliseconds(item.interval_ns),
                    _milliseconds(item.threshold_ns),
                    round(item.ratio_to_nominal, 3),
                ),
            )
            self.evidence_table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole,
                item,
            )
        self.open_previous_button.setEnabled(False)
        self.open_current_button.setEnabled(False)

        if result.warnings:
            self.status_label.setText(
                "; ".join(result.warnings)
            )

    @Slot()
    def _evidence_selected(self) -> None:
        rows = self.evidence_table.selectionModel().selectedRows()
        if not rows:
            self._selected_evidence = None
        else:
            value = self.evidence_table.item(
                rows[0].row(),
                0,
            ).data(Qt.ItemDataRole.UserRole)
            self._selected_evidence = (
                value
                if isinstance(value, InterFrameGapEvidence)
                else None
            )
        enabled = (
            self._selected_evidence is not None
            and not self._tasks
        )
        self.open_previous_button.setEnabled(enabled)
        self.open_current_button.setEnabled(enabled)

    @Slot()
    def _open_previous(self) -> None:
        evidence = self._selected_evidence
        if evidence is not None:
            self.source_row_requested.emit(
                evidence.session_id,
                evidence.previous_source_row,
                evidence.message_key,
            )

    @Slot()
    def _open_current(self) -> None:
        evidence = self._selected_evidence
        if evidence is not None:
            self.source_row_requested.emit(
                evidence.session_id,
                evidence.current_source_row,
                evidence.message_key,
            )

    def _set_busy(self, busy: bool) -> None:
        self.run_button.setEnabled(not busy)
        self.load_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.key_edit.setEnabled(not busy)
        self.gap_factor_spin.setEnabled(not busy)
        self.open_previous_button.setEnabled(
            not busy and self._selected_evidence is not None
        )
        self.open_current_button.setEnabled(
            not busy and self._selected_evidence is not None
        )
        if not busy:
            self.progress.setVisible(False)


def _table(
    parent: QWidget,
    name: str,
    headers: tuple[str, ...],
) -> QTableWidget:
    table = QTableWidget(parent)
    table.setObjectName(name)
    table.setColumnCount(len(headers))
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
    table.horizontalHeader().setStretchLastSection(True)
    return table


def _set_row(
    table: QTableWidget,
    row: int,
    values: tuple[Any, ...],
) -> None:
    for column, value in enumerate(values):
        text = "—" if value is None else str(value)
        table.setItem(
            row,
            column,
            QTableWidgetItem(text),
        )


def _milliseconds(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"{float(value) / 1_000_000.0:.6f}"


def _number(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.6f}"


def _scale(
    value: float,
    minimum: float,
    maximum: float,
    left: float,
    width: float,
) -> float:
    return left + (value - minimum) / (maximum - minimum) * width


__all__ = [
    "ComparisonInterFrameTimingView",
    "InterFrameTimingChart",
]
