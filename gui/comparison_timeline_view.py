from __future__ import annotations

from threading import Event

from PySide6.QtCore import (
    QObject,
    QPointF,
    QRunnable,
    Qt,
    QThreadPool,
    Signal,
    Slot,
)
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.comparison_timeline import (
    ComparisonTimelineCancelled,
    ComparisonTimelineEvent,
    ComparisonTimelineResult,
    SYNC_MESSAGE_KEY,
    SYNC_SESSION_START,
    build_comparison_timeline,
)


class _TimelineSignals(QObject):
    completed = Signal(int, object)
    failed = Signal(int, str)
    finished = Signal(int)


class _TimelineBuildTask(QRunnable):
    def __init__(
        self,
        generation: int,
        project,
        comparison_set,
        synchronization_mode: str,
        anchor_message_key: str,
        cancel_event: Event,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.generation = generation
        self.project = project
        self.comparison_set = comparison_set
        self.synchronization_mode = synchronization_mode
        self.anchor_message_key = anchor_message_key
        self.cancel_event = cancel_event
        self.signals = _TimelineSignals()

    @Slot()
    def run(self) -> None:
        try:
            try:
                result = build_comparison_timeline(
                    self.project,
                    self.comparison_set,
                    synchronization_mode=self.synchronization_mode,
                    anchor_message_key=self.anchor_message_key,
                    should_cancel=self.cancel_event.is_set,
                )
            except ComparisonTimelineCancelled:
                return
            except Exception as exc:  # pragma: no cover - surfaced through GUI
                if not self.cancel_event.is_set():
                    self.signals.failed.emit(self.generation, str(exc))
                return
            if not self.cancel_event.is_set():
                self.signals.completed.emit(self.generation, result)
        finally:
            self.signals.finished.emit(self.generation)


class ComparisonTimelineCanvas(QWidget):
    event_selected = Signal(object)
    event_activated = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("comparisonTimelineCanvas")
        self.setMinimumHeight(280)
        self._result: ComparisonTimelineResult | None = None
        self._selected: ComparisonTimelineEvent | None = None
        self._event_points: list[tuple[QPointF, ComparisonTimelineEvent]] = []

    def set_result(self, result: ComparisonTimelineResult | None) -> None:
        self._result = result
        self._selected = None
        lane_count = 0 if result is None else len(result.lanes)
        self.setMinimumHeight(max(280, 80 + lane_count * 58))
        self.update()

    def selected_event(self) -> ComparisonTimelineEvent | None:
        return self._selected

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), self.palette().base())
        self._event_points.clear()

        result = self._result
        if result is None or not result.lanes:
            painter.setPen(self.palette().text().color())
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Zbuduj oś czasu, aby porównać sesje na wspólnej skali.",
            )
            return

        left = 178
        right = 24
        top = 42
        lane_height = 58
        plot_width = max(1, self.width() - left - right)
        minimum = result.minimum_relative_time_ns
        maximum = result.maximum_relative_time_ns
        span = max(1, maximum - minimum)

        painter.setPen(self.palette().text().color())
        painter.drawText(left, 22, _format_axis_time(minimum))
        right_label = _format_axis_time(maximum)
        painter.drawText(
            self.width() - right - painter.fontMetrics().horizontalAdvance(right_label),
            22,
            right_label,
        )

        zero_x = left + ((0 - minimum) / span) * plot_width
        if left <= zero_x <= left + plot_width:
            zero_pen = QPen(QColor("#4da3ff"))
            zero_pen.setWidth(1)
            zero_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(zero_pen)
            painter.drawLine(
                int(zero_x),
                top - 18,
                int(zero_x),
                top + lane_height * len(result.lanes),
            )
            painter.drawText(int(zero_x) + 4, 36, "t = 0")

        for lane_index, lane in enumerate(result.lanes):
            y = top + lane_index * lane_height + 22
            painter.setPen(self.palette().text().color())
            painter.drawText(8, y + 4, _elide(lane.session_name, 26))

            baseline_pen = QPen(self.palette().mid().color())
            baseline_pen.setWidth(1)
            painter.setPen(baseline_pen)
            painter.drawLine(left, y, left + plot_width, y)

            if not lane.synchronized:
                painter.setPen(QColor("#f0ad4e"))
                painter.drawText(left + 8, y - 8, lane.warning or "Brak synchronizacji")
                continue

            for event in lane.events:
                relative = event.relative_time_ns
                if relative is None:
                    continue
                x = left + ((relative - minimum) / span) * plot_width
                point = QPointF(x, y)
                self._event_points.append((point, event))
                selected = event == self._selected
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(
                    QColor("#4da3ff") if selected else self.palette().highlight()
                )
                radius = 4.5 if selected else 2.2
                painter.drawEllipse(point, radius, radius)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        selected = _nearest_event(event.position(), self._event_points)
        if selected is None:
            return
        self._selected = selected
        self.event_selected.emit(selected)
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        selected = _nearest_event(event.position(), self._event_points)
        if selected is None:
            return
        self._selected = selected
        self.event_selected.emit(selected)
        self.event_activated.emit(selected)
        self.update()


class ComparisonTimelineView(QWidget):
    source_row_requested = Signal(str, int, str)

    def __init__(self, project, comparison_set, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("comparisonTimelineView")
        self.project = project
        self.comparison_set = comparison_set
        self._generation = 0
        self._tasks: dict[int, _TimelineBuildTask] = {}
        self._selected_event: ComparisonTimelineEvent | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        controls = QHBoxLayout()
        form = QFormLayout()
        self.mode_combo = QComboBox(self)
        self.mode_combo.setObjectName("timelineSynchronizationMode")
        self.mode_combo.addItem("Początek każdej sesji", SYNC_SESSION_START)
        self.mode_combo.addItem(
            "Pierwsze wystąpienie klucza wiadomości",
            SYNC_MESSAGE_KEY,
        )
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        form.addRow("Synchronizacja:", self.mode_combo)

        self.anchor_edit = QLineEdit(self)
        self.anchor_edit.setObjectName("timelineAnchorMessageKey")
        self.anchor_edit.setPlaceholderText("Np. 0:EXT:1AFFB680:data")
        form.addRow("Kotwica:", self.anchor_edit)
        controls.addLayout(form, 1)

        self.build_button = QPushButton("Zbuduj oś czasu", self)
        self.build_button.setObjectName("buildComparisonTimeline")
        self.build_button.clicked.connect(self.build_timeline)
        controls.addWidget(self.build_button)
        self.cancel_button = QPushButton("Anuluj", self)
        self.cancel_button.setObjectName("cancelComparisonTimeline")
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False)
        controls.addWidget(self.cancel_button)
        root.addLayout(controls)

        self.status_label = QLabel(
            "Oś czasu jest budowana pasywnie ze źródłowych sesji i nie zmienia ich danych.",
            self,
        )
        self.status_label.setObjectName("comparisonTimelineStatus")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.canvas = ComparisonTimelineCanvas(self)
        self.canvas.event_selected.connect(self._event_selected)
        self.canvas.event_activated.connect(self._event_activated)
        root.addWidget(self.canvas, 1)

        self.lanes_table = QTableWidget(0, 7, self)
        self.lanes_table.setObjectName("comparisonTimelineLanes")
        self.lanes_table.setHorizontalHeaderLabels(
            ["Sesja", "Ramki", "Punkty", "Krok", "Kotwica", "Zakres", "Stan"]
        )
        self.lanes_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.lanes_table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.lanes_table.verticalHeader().setVisible(False)
        self.lanes_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        for column in range(1, 7):
            self.lanes_table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        root.addWidget(self.lanes_table)

        selected_row = QHBoxLayout()
        self.selected_label = QLabel(
            "Kliknij punkt osi czasu, aby wskazać ramkę.",
            self,
        )
        self.selected_label.setObjectName("comparisonTimelineSelection")
        selected_row.addWidget(self.selected_label, 1)
        self.open_button = QPushButton("Otwórz ramkę źródłową", self)
        self.open_button.setObjectName("openTimelineSourceFrame")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected)
        selected_row.addWidget(self.open_button)
        root.addLayout(selected_row)

        self._mode_changed()

    @Slot()
    def build_timeline(self) -> None:
        mode = str(self.mode_combo.currentData() or SYNC_SESSION_START)
        anchor = self.anchor_edit.text().strip()
        if mode == SYNC_MESSAGE_KEY and not anchor:
            self.status_label.setText("Podaj klucz wiadomości używany jako kotwica.")
            self.anchor_edit.setFocus()
            return

        self._cancel_tasks()
        self._generation += 1
        generation = self._generation
        cancel_event = Event()
        task = _TimelineBuildTask(
            generation,
            self.project,
            self.comparison_set,
            mode,
            anchor,
            cancel_event,
        )
        task.signals.completed.connect(self._timeline_ready)
        task.signals.failed.connect(self._timeline_failed)
        task.signals.finished.connect(self._timeline_finished)
        self._tasks[generation] = task
        self._set_running(True)
        self.status_label.setText("Buduję wspólną oś czasu…")
        QThreadPool.globalInstance().start(task)

    @Slot()
    def cancel(self) -> None:
        had_tasks = bool(self._tasks)
        self._generation += 1
        self._cancel_tasks()
        if had_tasks:
            self.status_label.setText("Anulowano budowanie osi czasu.")
        self._set_running(False)

    def cancel_all(self) -> None:
        self.cancel()

    def _cancel_tasks(self) -> None:
        for task in self._tasks.values():
            task.cancel_event.set()

    @Slot(int, object)
    def _timeline_ready(self, generation: int, value: object) -> None:
        if generation != self._generation:
            return
        if not isinstance(value, ComparisonTimelineResult):
            self._timeline_failed(generation, "Niepoprawny wynik osi czasu.")
            return
        self.canvas.set_result(value)
        self._populate_lanes(value)
        self._clear_selection()
        warning_text = (
            f" Ostrzeżenia: {len(value.warnings)}."
            if value.warnings
            else ""
        )
        sampled = sum(lane.sampled_frame_count for lane in value.lanes)
        self.status_label.setText(
            f"Oś czasu gotowa: {len(value.lanes)} sesje, {sampled} punktów."
            f"{warning_text}"
        )

    @Slot(int, str)
    def _timeline_failed(self, generation: int, error: str) -> None:
        if generation != self._generation:
            return
        self.canvas.set_result(None)
        self.lanes_table.setRowCount(0)
        self._clear_selection()
        self.status_label.setText(f"Nie udało się zbudować osi czasu: {error}")

    @Slot(int)
    def _timeline_finished(self, generation: int) -> None:
        self._tasks.pop(generation, None)
        if generation == self._generation:
            self._set_running(False)

    def _populate_lanes(self, result: ComparisonTimelineResult) -> None:
        self.lanes_table.setRowCount(0)
        for lane in result.lanes:
            row = self.lanes_table.rowCount()
            self.lanes_table.insertRow(row)
            duration_ns = (
                0
                if lane.first_timestamp_ns is None or lane.last_timestamp_ns is None
                else max(0, lane.last_timestamp_ns - lane.first_timestamp_ns)
            )
            values = (
                lane.session_name,
                str(lane.total_frame_count),
                str(lane.sampled_frame_count),
                str(lane.sample_stride),
                "—" if lane.anchor_source_row is None else str(lane.anchor_source_row + 1),
                _format_axis_time(duration_ns),
                lane.warning or "Gotowa",
            )
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if lane.warning:
                    item.setToolTip(lane.warning)
                self.lanes_table.setItem(row, column, item)
        self.lanes_table.resizeRowsToContents()
        self.lanes_table.setMaximumHeight(
            min(220, 34 + self.lanes_table.rowCount() * 30)
        )

    def _clear_selection(self) -> None:
        self._selected_event = None
        self.open_button.setEnabled(False)
        self.selected_label.setText(
            "Kliknij punkt osi czasu, aby wskazać ramkę."
        )

    @Slot(object)
    def _event_selected(self, value: object) -> None:
        if not isinstance(value, ComparisonTimelineEvent):
            return
        self._selected_event = value
        self.open_button.setEnabled(True)
        relative = value.relative_time_ns or 0
        self.selected_label.setText(
            f"{value.session_name} · t={_format_axis_time(relative)} · "
            f"ramka {value.source_row + 1} · {value.message_key} · "
            f"DLC {value.dlc} · {value.data_hex or '—'}"
        )

    @Slot(object)
    def _event_activated(self, value: object) -> None:
        self._event_selected(value)
        self._open_selected()

    @Slot()
    def _open_selected(self) -> None:
        event = self._selected_event
        if event is None:
            return
        self.source_row_requested.emit(
            event.session_id,
            event.source_row,
            event.message_key,
        )

    @Slot()
    def _mode_changed(self) -> None:
        message_key_mode = self.mode_combo.currentData() == SYNC_MESSAGE_KEY
        self.anchor_edit.setEnabled(message_key_mode)

    def _set_running(self, running: bool) -> None:
        self.build_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.mode_combo.setEnabled(not running)
        self.anchor_edit.setEnabled(
            not running and self.mode_combo.currentData() == SYNC_MESSAGE_KEY
        )

    def closeEvent(self, event) -> None:
        self.cancel_all()
        super().closeEvent(event)


def _nearest_event(
    position: QPointF,
    points: list[tuple[QPointF, ComparisonTimelineEvent]],
) -> ComparisonTimelineEvent | None:
    best: ComparisonTimelineEvent | None = None
    best_distance = 10.0 * 10.0
    for point, event in points:
        dx = point.x() - position.x()
        dy = point.y() - position.y()
        distance = dx * dx + dy * dy
        if distance <= best_distance:
            best = event
            best_distance = distance
    return best


def _format_axis_time(value_ns: int) -> str:
    seconds = value_ns / 1_000_000_000
    if abs(seconds) < 0.001:
        return f"{value_ns / 1_000_000:.3f} ms"
    return f"{seconds:.3f} s"


def _elide(value: str, maximum: int) -> str:
    return value if len(value) <= maximum else value[: maximum - 1] + "…"


__all__ = ["ComparisonTimelineCanvas", "ComparisonTimelineView"]
