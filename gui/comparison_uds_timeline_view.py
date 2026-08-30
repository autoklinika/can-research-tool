from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, QRectF, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.comparison_uds_timeline import (
    UdsTimelineCancelled,
    UdsTimelineFilter,
    UdsTimelineResult,
    UdsTimelineSources,
    UdsTimelineTransaction,
    build_uds_timeline,
    load_uds_timeline_sources,
)
from app.extensions import CancellationToken, ExtensionCancelled


_STATUS_LABELS = {
    "positive-response": "Pozytywna",
    "negative-response": "Negatywna",
    "timeout": "Timeout",
    "capture-ended": "Koniec logu",
    "suppressed-no-response": "Bez odpowiedzi (suppress)",
}
_STATUS_COLORS = {
    "positive-response": QColor("#2ca25f"),
    "negative-response": QColor("#d94841"),
    "timeout": QColor("#f0ad4e"),
    "capture-ended": QColor("#7f8c8d"),
    "suppressed-no-response": QColor("#3b82c4"),
}
_CLASSIFICATION_LABELS = {
    "baseline": "baza",
    "matched": "zgodna",
    "shifted": "przesunięta",
    "additional": "dodatkowa",
}


class _LoadSignals(QObject):
    completed = Signal(int, object, object)
    failed = Signal(int, str)
    finished = Signal(int)


class _LoadTask(QRunnable):
    def __init__(
        self,
        generation: int,
        project,
        comparison_set,
        cancellation: CancellationToken,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.generation = generation
        self.project = project
        self.comparison_set = comparison_set
        self.cancellation = cancellation
        self.signals = _LoadSignals()

    @Slot()
    def run(self) -> None:
        try:
            try:
                sources = load_uds_timeline_sources(
                    self.project,
                    self.comparison_set,
                    should_cancel=lambda: self.cancellation.is_cancelled,
                )
                result = build_uds_timeline(sources)
            except (UdsTimelineCancelled, ExtensionCancelled):
                return
            except Exception as exc:  # pragma: no cover - surfaced through GUI
                if not self.cancellation.is_cancelled:
                    self.signals.failed.emit(self.generation, str(exc))
                return
            if not self.cancellation.is_cancelled:
                self.signals.completed.emit(self.generation, sources, result)
        finally:
            self.signals.finished.emit(self.generation)


class UdsTimelineCanvas(QWidget):
    transaction_selected = Signal(object)
    transaction_activated = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("udsTimelineCanvas")
        self.setMinimumHeight(300)
        self._result: UdsTimelineResult | None = None
        self._selected: UdsTimelineTransaction | None = None
        self._hit_areas: list[tuple[QRectF, UdsTimelineTransaction]] = []

    def set_result(self, result: UdsTimelineResult | None) -> None:
        self._result = result
        self._selected = None
        lane_count = 0 if result is None else len(result.lanes)
        self.setMinimumHeight(max(300, 80 + lane_count * 66))
        self.update()

    def select_transaction(self, value: UdsTimelineTransaction | None) -> None:
        self._selected = value
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), self.palette().base())
        self._hit_areas.clear()
        result = self._result
        if result is None or not result.lanes:
            painter.setPen(self.palette().text().color())
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Wczytaj trwałą oś UDS opartą na artefaktach Stage 2B i Stage 2C2.",
            )
            return

        left, right, top, lane_height = 180, 28, 44, 66
        plot_width = max(1, self.width() - left - right)
        minimum = result.minimum_relative_time_ns
        maximum = result.maximum_relative_time_ns
        span = max(1, maximum - minimum)

        painter.setPen(self.palette().text().color())
        painter.drawText(left, 24, _format_time(minimum))
        right_text = _format_time(maximum)
        painter.drawText(
            self.width() - right - painter.fontMetrics().horizontalAdvance(right_text),
            24,
            right_text,
        )
        zero_x = left + ((0 - minimum) / span) * plot_width
        if left <= zero_x <= left + plot_width:
            painter.setPen(QPen(QColor("#4da3ff"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(zero_x), top - 20, int(zero_x), top + lane_height * len(result.lanes))
            painter.drawText(int(zero_x) + 4, 39, "t = 0")

        for lane_index, lane in enumerate(result.lanes):
            y = top + lane_index * lane_height + 24
            painter.setPen(self.palette().text().color())
            suffix = " [BAZA]" if lane.is_baseline else ""
            painter.drawText(8, y + 4, _elide(lane.session_name + suffix, 27))
            painter.setPen(QPen(self.palette().mid().color(), 1))
            painter.drawLine(left, y, left + plot_width, y)

            for item in lane.transactions:
                start_x = left + ((item.request_relative_time_ns - minimum) / span) * plot_width
                end_time = item.final_response_relative_time_ns
                if end_time is None:
                    end_time = item.first_response_relative_time_ns
                end_x = start_x if end_time is None else left + ((end_time - minimum) / span) * plot_width
                end_x = max(start_x + 3.0, end_x)
                color = _STATUS_COLORS.get(item.transaction.status, QColor("#7f8c8d"))
                selected = item == self._selected
                pen_width = 5.5 if selected else 3.5
                pen = QPen(color, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
                if item.transaction.status in {"timeout", "capture-ended"}:
                    pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawLine(QPointF(start_x, y), QPointF(end_x, y))
                painter.setBrush(color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(start_x, y), 4.5 if selected else 3.2, 4.5 if selected else 3.2)

                for pending_time in item.pending_relative_times_ns:
                    pending_x = left + ((pending_time - minimum) / span) * plot_width
                    painter.setBrush(QColor("#9b59b6"))
                    painter.drawEllipse(QPointF(pending_x, y - 9), 3.0, 3.0)

                if item.sequence_classification in {"additional", "shifted"}:
                    outline = QColor("#e67e22") if item.sequence_classification == "additional" else QColor("#f1c40f")
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(outline, 1.4))
                    painter.drawRect(QRectF(start_x - 5, y - 13, max(10.0, end_x - start_x + 10), 26))

                self._hit_areas.append(
                    (QRectF(start_x - 7, y - 16, max(14.0, end_x - start_x + 14), 32), item)
                )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        selected = _hit_transaction(event.position(), self._hit_areas)
        if selected is None:
            return
        self._selected = selected
        self.transaction_selected.emit(selected)
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        selected = _hit_transaction(event.position(), self._hit_areas)
        if selected is None:
            return
        self._selected = selected
        self.transaction_selected.emit(selected)
        self.transaction_activated.emit(selected)
        self.update()


class ComparisonUdsTimelineView(QWidget):
    source_row_requested = Signal(str, int, str)

    def __init__(self, project, comparison_set, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("comparisonUdsTimelineView")
        self.project = project
        self.comparison_set = comparison_set
        self._generation = 0
        self._tasks: dict[int, _LoadTask] = {}
        self._sources: UdsTimelineSources | None = None
        self._result: UdsTimelineResult | None = None
        self._visible_transactions: list[UdsTimelineTransaction] = []
        self._selected: UdsTimelineTransaction | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        intro = QLabel(
            "Widok łączy zapisane wyrównanie Stage 2B z zachowanymi transakcjami "
            "Stage 2C2. Nie skanuje ponownie surowych sesji.",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        controls = QHBoxLayout()
        form = QFormLayout()
        self.session_combo = QComboBox(self)
        self.session_combo.addItem("Wszystkie sesje", "")
        form.addRow("Sesja:", self.session_combo)
        self.service_combo = QComboBox(self)
        self.service_combo.addItem("Wszystkie SID", None)
        form.addRow("SID:", self.service_combo)
        self.status_combo = QComboBox(self)
        self.status_combo.addItem("Wszystkie statusy", "")
        for status, label in _STATUS_LABELS.items():
            self.status_combo.addItem(label, status)
        form.addRow("Status:", self.status_combo)
        controls.addLayout(form)

        form2 = QFormLayout()
        self.did_edit = QLineEdit(self)
        self.did_edit.setPlaceholderText("np. F190")
        form2.addRow("DID:", self.did_edit)
        self.nrc_edit = QLineEdit(self)
        self.nrc_edit.setPlaceholderText("np. 78 lub 31")
        form2.addRow("NRC:", self.nrc_edit)
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("usługa, payload, status, Routine ID…")
        form2.addRow("Szukaj:", self.search_edit)
        controls.addLayout(form2, 1)

        self.load_button = QPushButton("Wczytaj trwałą oś UDS", self)
        self.load_button.setObjectName("loadUdsTransactionTimeline")
        self.load_button.clicked.connect(self.load_sources)
        controls.addWidget(self.load_button)
        self.apply_button = QPushButton("Zastosuj filtry", self)
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply_filters)
        controls.addWidget(self.apply_button)
        self.clear_button = QPushButton("Wyczyść filtry", self)
        self.clear_button.setEnabled(False)
        self.clear_button.clicked.connect(self.clear_filters)
        controls.addWidget(self.clear_button)
        self.cancel_button = QPushButton("Anuluj", self)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        controls.addWidget(self.cancel_button)
        root.addLayout(controls)

        self.status_label = QLabel("Oczekiwanie na trwałe artefakty Stage 2B i Stage 2C2.", self)
        self.status_label.setObjectName("udsTimelineStatus")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.canvas = UdsTimelineCanvas(self)
        self.canvas.transaction_selected.connect(self._transaction_selected)
        self.canvas.transaction_activated.connect(self._transaction_activated)
        root.addWidget(self.canvas, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        left = QWidget(splitter)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.difference_table = QTableWidget(0, 5, left)
        self.difference_table.setHorizontalHeaderLabels(
            ["Sesja", "Brakujące", "Dodatkowe", "Przesunięte", "Brakujące usługi"]
        )
        self.difference_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.difference_table.verticalHeader().setVisible(False)
        self.difference_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.difference_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        left_layout.addWidget(self.difference_table)

        self.transaction_table = QTableWidget(0, 9, left)
        self.transaction_table.setObjectName("udsTimelineTransactions")
        self.transaction_table.setHorizontalHeaderLabels(
            ["Sesja", "t request", "SID", "Korelacja", "Status", "Sekwencja", "0x78", "First [ms]", "Final [ms]"]
        )
        self.transaction_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.transaction_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.transaction_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.transaction_table.verticalHeader().setVisible(False)
        self.transaction_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.transaction_table.itemSelectionChanged.connect(self._table_selection_changed)
        left_layout.addWidget(self.transaction_table, 1)
        splitter.addWidget(left)

        details_panel = QWidget(splitter)
        details_layout = QVBoxLayout(details_panel)
        details_layout.setContentsMargins(8, 0, 0, 0)
        self.details = QLabel("Zaznacz transakcję, aby zobaczyć szczegóły.", details_panel)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details.setWordWrap(True)
        self.details.setAlignment(Qt.AlignmentFlag.AlignTop)
        details_layout.addWidget(self.details, 1)
        buttons = QHBoxLayout()
        self.open_request_button = QPushButton("Otwórz żądanie", details_panel)
        self.open_request_button.clicked.connect(self._open_request)
        buttons.addWidget(self.open_request_button)
        self.open_first_button = QPushButton("Otwórz pierwszą odpowiedź", details_panel)
        self.open_first_button.clicked.connect(self._open_first)
        buttons.addWidget(self.open_first_button)
        self.open_final_button = QPushButton("Otwórz odpowiedź końcową", details_panel)
        self.open_final_button.clicked.connect(self._open_final)
        buttons.addWidget(self.open_final_button)
        details_layout.addLayout(buttons)
        splitter.addWidget(details_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        self._clear_selection()
        QTimer.singleShot(0, self.load_sources)

    @Slot()
    def load_sources(self) -> None:
        self.cancel()
        self._generation += 1
        generation = self._generation
        cancellation = CancellationToken()
        task = _LoadTask(generation, self.project, self.comparison_set, cancellation)
        task.signals.completed.connect(self._load_completed)
        task.signals.failed.connect(self._load_failed)
        task.signals.finished.connect(self._load_finished)
        self._tasks[generation] = task
        self._set_running(True)
        self.status_label.setText("Wczytuję trwałe artefakty bez skanowania sesji…")
        QThreadPool.globalInstance().start(task)

    @Slot()
    def apply_filters(self) -> None:
        if self._sources is None:
            self.status_label.setText("Najpierw wczytaj trwałe artefakty.")
            return
        try:
            specification = self._filter_from_controls()
            result = build_uds_timeline(self._sources, filter_specification=specification)
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return
        self._apply_result(result)

    @Slot()
    def clear_filters(self) -> None:
        self.session_combo.setCurrentIndex(0)
        self.service_combo.setCurrentIndex(0)
        self.status_combo.setCurrentIndex(0)
        self.did_edit.clear()
        self.nrc_edit.clear()
        self.search_edit.clear()
        self.apply_filters()

    @Slot()
    def cancel(self) -> None:
        if not self._tasks:
            return
        self._generation += 1
        for task in self._tasks.values():
            task.cancellation.cancel()
        self._set_running(False)
        self.status_label.setText("Anulowano wczytywanie trwałej osi UDS.")

    def cancel_all(self) -> None:
        self.cancel()

    @Slot(int, object, object)
    def _load_completed(self, generation: int, sources: object, result: object) -> None:
        if generation != self._generation:
            return
        if not isinstance(sources, UdsTimelineSources) or not isinstance(result, UdsTimelineResult):
            self._load_failed(generation, "Niepoprawny wynik trwałej osi UDS.")
            return
        self._sources = sources
        self._populate_filter_choices(sources)
        self._apply_result(result)

    @Slot(int, str)
    def _load_failed(self, generation: int, error: str) -> None:
        if generation != self._generation:
            return
        self._sources = None
        self._result = None
        self.canvas.set_result(None)
        self.transaction_table.setRowCount(0)
        self.difference_table.setRowCount(0)
        self._clear_selection()
        self.apply_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.status_label.setText(f"Nie udało się wczytać trwałej osi UDS: {error}")

    @Slot(int)
    def _load_finished(self, generation: int) -> None:
        self._tasks.pop(generation, None)
        if not self._tasks:
            self._set_running(False)

    def _apply_result(self, result: UdsTimelineResult) -> None:
        self._result = result
        self.canvas.set_result(result)
        self._populate_differences(result)
        self._populate_transactions(result)
        self._clear_selection()
        skipped = (
            f" Pominięto {result.skipped_newer_empty_uds_artifacts} nowszych pustych artefaktów UDS."
            if result.skipped_newer_empty_uds_artifacts
            else ""
        )
        warning = " " + " ".join(result.warnings) if result.warnings else ""
        self.status_label.setText(
            f"Wczytano bez skanowania sesji: {result.visible_transaction_count} z "
            f"{result.source_transaction_count} zachowanych transakcji; "
            f"wyrównanie {result.alignment_artifact_id}; UDS {result.uds_artifact_id}."
            f"{skipped}{warning}"
        )
        self.apply_button.setEnabled(True)
        self.clear_button.setEnabled(True)

    def _populate_filter_choices(self, sources: UdsTimelineSources) -> None:
        stored = sources.uds.stored
        if stored is None:
            return
        current_session = self.session_combo.currentData()
        self.session_combo.clear()
        self.session_combo.addItem("Wszystkie sesje", "")
        service_ids: set[int] = set()
        for session in stored.result.sessions:
            self.session_combo.addItem(session.session_name, session.session_id)
            service_ids.update(item.request_service_id for item in session.transaction_evidence)
        index = self.session_combo.findData(current_session)
        self.session_combo.setCurrentIndex(max(0, index))

        current_service = self.service_combo.currentData()
        self.service_combo.clear()
        self.service_combo.addItem("Wszystkie SID", None)
        for service_id in sorted(service_ids):
            self.service_combo.addItem(f"0x{service_id:02X}", service_id)
        index = self.service_combo.findData(current_service)
        self.service_combo.setCurrentIndex(max(0, index))

    def _filter_from_controls(self) -> UdsTimelineFilter:
        did = _parse_optional_hex(self.did_edit.text(), "DID")
        nrc = _parse_optional_hex(self.nrc_edit.text(), "NRC")
        session_id = str(self.session_combo.currentData() or "")
        service_id = self.service_combo.currentData()
        status = str(self.status_combo.currentData() or "")
        return UdsTimelineFilter(
            session_ids=() if not session_id else (session_id,),
            service_ids=() if service_id is None else (int(service_id),),
            statuses=() if not status else (status,),
            dids=() if did is None else (did,),
            negative_response_codes=() if nrc is None else (nrc,),
            text_query=self.search_edit.text(),
        )

    def _populate_differences(self, result: UdsTimelineResult) -> None:
        self.difference_table.setRowCount(0)
        visible_sessions = {lane.session_id for lane in result.lanes}
        for difference in result.differences:
            if difference.session_id not in visible_sessions:
                continue
            row = self.difference_table.rowCount()
            self.difference_table.insertRow(row)
            values = (
                difference.session_name,
                str(difference.missing_count),
                str(difference.additional_count),
                str(difference.shifted_count),
                ", ".join(difference.missing_labels[:12]) or "—",
            )
            for column, value in enumerate(values):
                self.difference_table.setItem(row, column, QTableWidgetItem(value))
        self.difference_table.resizeRowsToContents()
        self.difference_table.setMaximumHeight(min(150, 32 + 30 * max(1, self.difference_table.rowCount())))

    def _populate_transactions(self, result: UdsTimelineResult) -> None:
        self.transaction_table.clearSelection()
        self.transaction_table.setRowCount(0)
        self._visible_transactions = []
        for lane in result.lanes:
            for item in lane.transactions:
                index = len(self._visible_transactions)
                self._visible_transactions.append(item)
                transaction = item.transaction
                row = self.transaction_table.rowCount()
                self.transaction_table.insertRow(row)
                values = (
                    transaction.session_name,
                    _format_time(item.request_relative_time_ns),
                    f"0x{transaction.request_service_id:02X}",
                    item.record.automatic_correlation_label,
                    _STATUS_LABELS.get(transaction.status, transaction.status),
                    _CLASSIFICATION_LABELS.get(item.sequence_classification, item.sequence_classification),
                    str(transaction.response_pending_count),
                    _format_latency(transaction.first_response_latency_ns),
                    _format_latency(transaction.final_response_latency_ns),
                )
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    cell.setData(Qt.ItemDataRole.UserRole, index)
                    self.transaction_table.setItem(row, column, cell)
        self.transaction_table.resizeRowsToContents()

    @Slot()
    def _table_selection_changed(self) -> None:
        row = self.transaction_table.currentRow()
        if row < 0:
            self._clear_selection()
            return
        item = self.transaction_table.item(row, 0)
        if item is None:
            return
        index = int(item.data(Qt.ItemDataRole.UserRole))
        if not 0 <= index < len(self._visible_transactions):
            return
        self._transaction_selected(self._visible_transactions[index])

    @Slot(object)
    def _transaction_selected(self, value: object) -> None:
        if not isinstance(value, UdsTimelineTransaction):
            return
        self._selected = value
        self.canvas.select_transaction(value)
        transaction = value.transaction
        self.details.setText(
            "\n".join(
                (
                    f"Sesja: {transaction.session_name}",
                    f"Request: row {transaction.request.first_source_row + 1}; t={_format_time(value.request_relative_time_ns)}; {transaction.request.payload_hex}",
                    f"Usługa: 0x{transaction.request_service_id:02X} {transaction.request_service_name}",
                    f"Korelacja: {value.record.automatic_correlation_label}",
                    f"Status: {_STATUS_LABELS.get(transaction.status, transaction.status)}",
                    f"Sekwencja: {_CLASSIFICATION_LABELS.get(value.sequence_classification, value.sequence_classification)}",
                    f"ResponsePending 0x78: {transaction.response_pending_count}",
                    f"First latency: {_format_latency(transaction.first_response_latency_ns)} ms",
                    f"Final latency: {_format_latency(transaction.final_response_latency_ns)} ms",
                    f"NRC: {'—' if transaction.final_negative_response_code is None else f'0x{transaction.final_negative_response_code:02X}'}",
                    f"First response: {'—' if transaction.first_response is None else transaction.first_response.payload_hex}",
                    f"Final response: {'—' if transaction.final_response is None else transaction.final_response.payload_hex}",
                )
            )
        )
        self.open_request_button.setEnabled(True)
        self.open_first_button.setEnabled(transaction.first_response is not None)
        self.open_final_button.setEnabled(transaction.final_response is not None)

    @Slot(object)
    def _transaction_activated(self, value: object) -> None:
        self._transaction_selected(value)
        self._open_request()

    def _clear_selection(self) -> None:
        self._selected = None
        self.canvas.select_transaction(None)
        self.details.setText("Zaznacz transakcję, aby zobaczyć szczegóły.")
        self.open_request_button.setEnabled(False)
        self.open_first_button.setEnabled(False)
        self.open_final_button.setEnabled(False)

    @Slot()
    def _open_request(self) -> None:
        if self._selected is None:
            return
        evidence = self._selected.transaction.request
        self.source_row_requested.emit(evidence.session_id, evidence.first_source_row, evidence.message_key)

    @Slot()
    def _open_first(self) -> None:
        if self._selected is None or self._selected.transaction.first_response is None:
            return
        evidence = self._selected.transaction.first_response
        self.source_row_requested.emit(evidence.session_id, evidence.first_source_row, evidence.message_key)

    @Slot()
    def _open_final(self) -> None:
        if self._selected is None or self._selected.transaction.final_response is None:
            return
        evidence = self._selected.transaction.final_response
        self.source_row_requested.emit(evidence.session_id, evidence.first_source_row, evidence.message_key)

    def _set_running(self, running: bool) -> None:
        self.load_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        if running:
            self.apply_button.setEnabled(False)
            self.clear_button.setEnabled(False)


def _hit_transaction(
    position: QPointF,
    hit_areas: list[tuple[QRectF, UdsTimelineTransaction]],
) -> UdsTimelineTransaction | None:
    matches = [(area.width(), item) for area, item in hit_areas if area.contains(position)]
    if not matches:
        return None
    return min(matches, key=lambda entry: entry[0])[1]


def _parse_optional_hex(value: str, label: str) -> int | None:
    text = str(value).strip()
    if not text:
        return None
    if text.lower().startswith("0x"):
        text = text[2:]
    try:
        return int(text, 16)
    except ValueError as exc:
        raise ValueError(f"Niepoprawna wartość {label}: {value!r}") from exc


def _format_time(value_ns: int) -> str:
    value = float(value_ns)
    sign = "-" if value < 0 else ""
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{sign}{absolute / 1_000_000_000:.3f} s"
    if absolute >= 1_000_000:
        return f"{sign}{absolute / 1_000_000:.3f} ms"
    if absolute >= 1_000:
        return f"{sign}{absolute / 1_000:.3f} µs"
    return f"{sign}{absolute:.0f} ns"


def _format_latency(value_ns: int | float | None) -> str:
    if value_ns is None:
        return "—"
    return f"{float(value_ns) / 1_000_000.0:.3f}"


def _elide(value: str, maximum: int) -> str:
    text = str(value)
    return text if len(text) <= maximum else text[: maximum - 1] + "…"


__all__ = ["ComparisonUdsTimelineView", "UdsTimelineCanvas"]
