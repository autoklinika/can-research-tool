from __future__ import annotations

from PySide6.QtCore import (
    QObject,
    QPointF,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.comparison_timeline import (
    ComparisonTimelineCancelled,
    ComparisonTimelineEvent,
    ComparisonTimelineResult,
    SYNC_EXPLICIT_EVENT,
    SYNC_MESSAGE_KEY,
    SYNC_OPERATOR_MARKER,
    SYNC_SESSION_START,
    TimelineAnchorConfiguration,
    build_comparison_timeline,
    normalize_timeline_configuration,
)
from app.comparison_timeline_artifacts import (
    ComparisonTimelineArtifactService,
    StoredComparisonTimeline,
)
from app.domain import Artifact
from app.extensions import CancellationToken, ExtensionCancelled


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
        configuration: TimelineAnchorConfiguration,
        cancellation: CancellationToken,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.generation = generation
        self.project = project
        self.comparison_set = comparison_set
        self.configuration = configuration
        self.cancellation = cancellation
        self.signals = _TimelineSignals()

    @Slot()
    def run(self) -> None:
        try:
            try:
                result = build_comparison_timeline(
                    self.project,
                    self.comparison_set,
                    synchronization_mode=self.configuration.synchronization_mode,
                    anchor_message_key=self.configuration.anchor_message_key,
                    anchor_marker_name=self.configuration.anchor_marker_name,
                    anchor_occurrence=self.configuration.anchor_occurrence,
                    explicit_anchor_rows=self.configuration.explicit_rows,
                    should_cancel=lambda: self.cancellation.is_cancelled,
                )
            except (ComparisonTimelineCancelled, ExtensionCancelled):
                return
            except Exception as exc:  # pragma: no cover - surfaced through GUI
                if not self.cancellation.is_cancelled:
                    self.signals.failed.emit(self.generation, str(exc))
                return
            if not self.cancellation.is_cancelled:
                self.signals.completed.emit(self.generation, result)
        finally:
            self.signals.finished.emit(self.generation)


class _TimelineStorageSignals(QObject):
    completed = Signal(int, str, object)
    failed = Signal(int, str, str)
    finished = Signal(int, str)


class _TimelineStorageTask(QRunnable):
    def __init__(
        self,
        generation: int,
        operation: str,
        project,
        comparison_set,
        cancellation: CancellationToken,
        result: ComparisonTimelineResult | None = None,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.generation = generation
        self.operation = operation
        self.project = project
        self.comparison_set = comparison_set
        self.cancellation = cancellation
        self.result = result
        self.signals = _TimelineStorageSignals()

    @Slot()
    def run(self) -> None:
        try:
            try:
                service = ComparisonTimelineArtifactService(self.project)
                if self.operation == "load":
                    value = service.load_latest_compatible(
                        self.comparison_set,
                        should_cancel=lambda: self.cancellation.is_cancelled,
                    )
                elif self.operation == "save":
                    if self.result is None:
                        raise ValueError("Brak gotowej osi czasu do zapisania.")
                    value = service.save(
                        self.comparison_set,
                        self.result,
                        cancellation=self.cancellation,
                    )
                else:
                    raise ValueError(
                        f"Nieobsługiwana operacja osi czasu: {self.operation}"
                    )
            except (ComparisonTimelineCancelled, ExtensionCancelled):
                return
            except Exception as exc:  # pragma: no cover - surfaced through GUI
                if not self.cancellation.is_cancelled:
                    self.signals.failed.emit(
                        self.generation,
                        self.operation,
                        str(exc),
                    )
                return
            if not self.cancellation.is_cancelled:
                self.signals.completed.emit(
                    self.generation,
                    self.operation,
                    value,
                )
        finally:
            self.signals.finished.emit(self.generation, self.operation)


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
                "Zbuduj lub wczytaj oś czasu, aby porównać sesje na wspólnej skali.",
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
            self.width()
            - right
            - painter.fontMetrics().horizontalAdvance(right_label),
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
                painter.drawText(
                    left + 8,
                    y - 8,
                    lane.warning or "Brak synchronizacji",
                )
                continue

            for event in lane.events:
                relative = event.relative_time_ns
                if relative is None:
                    continue
                x = left + ((relative - minimum) / span) * plot_width
                point = QPointF(x, y)
                self._event_points.append((point, event))
                selected = event == self._selected
                is_anchor = event.source_row == lane.anchor_source_row
                painter.setPen(
                    QPen(QColor("#f0ad4e"), 1.4)
                    if is_anchor
                    else Qt.PenStyle.NoPen
                )
                painter.setBrush(
                    QColor("#4da3ff")
                    if selected
                    else self.palette().highlight()
                )
                radius = 5.0 if selected else (4.0 if is_anchor else 2.2)
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
        self._storage_generation = 0
        self._tasks: dict[int, _TimelineBuildTask] = {}
        self._storage_tasks: dict[int, _TimelineStorageTask] = {}
        self._selected_event: ComparisonTimelineEvent | None = None
        self._current_result: ComparisonTimelineResult | None = None
        self._explicit_anchor_rows: dict[str, int] = {}
        self._loaded_artifact_id = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        controls = QHBoxLayout()
        form = QFormLayout()
        self.mode_combo = QComboBox(self)
        self.mode_combo.setObjectName("timelineSynchronizationMode")
        self.mode_combo.addItem("Początek każdej sesji", SYNC_SESSION_START)
        self.mode_combo.addItem(
            "N-te wystąpienie klucza wiadomości",
            SYNC_MESSAGE_KEY,
        )
        self.mode_combo.addItem("N-ty znacznik operatora", SYNC_OPERATOR_MARKER)
        self.mode_combo.addItem(
            "Wybrane dokładne zdarzenia",
            SYNC_EXPLICIT_EVENT,
        )
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        form.addRow("Synchronizacja:", self.mode_combo)

        self.anchor_label = QLabel("Kotwica:", self)
        self.anchor_edit = QLineEdit(self)
        self.anchor_edit.setObjectName("timelineAnchorValue")
        form.addRow(self.anchor_label, self.anchor_edit)

        self.occurrence_spin = QSpinBox(self)
        self.occurrence_spin.setObjectName("timelineAnchorOccurrence")
        self.occurrence_spin.setRange(1, 1_000_000)
        self.occurrence_spin.setValue(1)
        form.addRow("Wystąpienie:", self.occurrence_spin)
        controls.addLayout(form, 1)

        self.build_button = QPushButton("Zbuduj oś czasu", self)
        self.build_button.setObjectName("buildComparisonTimeline")
        self.build_button.clicked.connect(self.build_timeline)
        controls.addWidget(self.build_button)
        self.load_button = QPushButton("Wczytaj zapisane", self)
        self.load_button.setObjectName("loadComparisonTimelineAlignment")
        self.load_button.clicked.connect(self.load_latest_alignment)
        controls.addWidget(self.load_button)
        self.save_button = QPushButton("Zapisz wyrównanie", self)
        self.save_button.setObjectName("saveComparisonTimelineAlignment")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_alignment)
        controls.addWidget(self.save_button)
        self.cancel_button = QPushButton("Anuluj", self)
        self.cancel_button.setObjectName("cancelComparisonTimeline")
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False)
        controls.addWidget(self.cancel_button)
        root.addLayout(controls)

        self.status_label = QLabel(
            "Oś czasu jest pasywna. Zapisane wyrównanie można otworzyć "
            "bez ponownego skanowania sesji.",
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
            [
                "Sesja",
                "Ramki",
                "Punkty",
                "Krok",
                "Kotwica",
                "Zakres",
                "Stan",
            ]
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
        self.set_anchor_button = QPushButton(
            "Ustaw jako kotwicę sesji",
            self,
        )
        self.set_anchor_button.setObjectName("setTimelineExplicitAnchor")
        self.set_anchor_button.setEnabled(False)
        self.set_anchor_button.clicked.connect(self._set_selected_as_anchor)
        selected_row.addWidget(self.set_anchor_button)
        self.clear_anchors_button = QPushButton("Wyczyść kotwice", self)
        self.clear_anchors_button.setObjectName("clearTimelineExplicitAnchors")
        self.clear_anchors_button.setEnabled(False)
        self.clear_anchors_button.clicked.connect(self._clear_explicit_anchors)
        selected_row.addWidget(self.clear_anchors_button)
        self.open_button = QPushButton("Otwórz ramkę źródłową", self)
        self.open_button.setObjectName("openTimelineSourceFrame")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected)
        selected_row.addWidget(self.open_button)
        root.addLayout(selected_row)

        self.explicit_anchors_label = QLabel("Dokładne kotwice: 0", self)
        self.explicit_anchors_label.setObjectName(
            "timelineExplicitAnchorsSummary"
        )
        root.addWidget(self.explicit_anchors_label)

        self._mode_changed()
        QTimer.singleShot(0, self.load_latest_alignment)

    @Slot()
    def build_timeline(self) -> None:
        try:
            configuration = self._configuration_from_controls()
        except (TypeError, ValueError) as exc:
            self.status_label.setText(str(exc))
            self.anchor_edit.setFocus()
            return

        self._cancel_build_tasks()
        self._generation += 1
        generation = self._generation
        cancellation = CancellationToken()
        task = _TimelineBuildTask(
            generation,
            self.project,
            self.comparison_set,
            configuration,
            cancellation,
        )
        task.signals.completed.connect(self._timeline_ready)
        task.signals.failed.connect(self._timeline_failed)
        task.signals.finished.connect(self._timeline_finished)
        self._tasks[generation] = task
        self._set_running(True)
        self.status_label.setText(
            "Buduję wspólną oś czasu ze źródłowych sesji…"
        )
        QThreadPool.globalInstance().start(task)

    @Slot()
    def load_latest_alignment(self) -> None:
        self._start_storage_task("load")

    @Slot()
    def save_alignment(self) -> None:
        if self._current_result is None:
            self.status_label.setText("Najpierw zbuduj lub wczytaj oś czasu.")
            return
        self._start_storage_task("save", result=self._current_result)

    def _start_storage_task(
        self,
        operation: str,
        *,
        result: ComparisonTimelineResult | None = None,
    ) -> None:
        self._cancel_storage_tasks()
        self._storage_generation += 1
        generation = self._storage_generation
        cancellation = CancellationToken()
        task = _TimelineStorageTask(
            generation,
            operation,
            self.project,
            self.comparison_set,
            cancellation,
            result,
        )
        task.signals.completed.connect(self._storage_completed)
        task.signals.failed.connect(self._storage_failed)
        task.signals.finished.connect(self._storage_finished)
        self._storage_tasks[generation] = task
        self._set_running(True)
        self.status_label.setText(
            "Wczytuję ostatnie zgodne wyrównanie…"
            if operation == "load"
            else "Zapisuję wersjonowany artefakt wyrównania…"
        )
        QThreadPool.globalInstance().start(task)

    @Slot()
    def cancel(self) -> None:
        had_tasks = bool(self._tasks or self._storage_tasks)
        self._generation += 1
        self._storage_generation += 1
        self._cancel_build_tasks()
        self._cancel_storage_tasks()
        if had_tasks:
            self.status_label.setText("Anulowano operację osi czasu.")
        self._set_running(False)

    def cancel_all(self) -> None:
        self.cancel()

    def _cancel_build_tasks(self) -> None:
        for task in self._tasks.values():
            task.cancellation.cancel()

    def _cancel_storage_tasks(self) -> None:
        for task in self._storage_tasks.values():
            task.cancellation.cancel()

    @Slot(int, object)
    def _timeline_ready(self, generation: int, value: object) -> None:
        if generation != self._generation:
            return
        if not isinstance(value, ComparisonTimelineResult):
            self._timeline_failed(generation, "Niepoprawny wynik osi czasu.")
            return
        self._loaded_artifact_id = ""
        self._apply_result(value)
        self.status_label.setText(
            self._ready_status(value, prefix="Oś czasu gotowa")
        )

    @Slot(int, str)
    def _timeline_failed(self, generation: int, error: str) -> None:
        if generation != self._generation:
            return
        self.canvas.set_result(None)
        self.lanes_table.setRowCount(0)
        self._current_result = None
        self._clear_selection()
        self.save_button.setEnabled(False)
        self.status_label.setText(
            f"Nie udało się zbudować osi czasu: {error}"
        )

    @Slot(int)
    def _timeline_finished(self, generation: int) -> None:
        self._tasks.pop(generation, None)
        if not self._tasks and not self._storage_tasks:
            self._set_running(False)

    @Slot(int, str, object)
    def _storage_completed(
        self,
        generation: int,
        operation: str,
        value: object,
    ) -> None:
        if generation != self._storage_generation:
            return
        if operation == "load":
            if value is None:
                if self._current_result is None:
                    self.status_label.setText(
                        "Brak zgodnego zapisanego wyrównania. "
                        "Zbuduj oś czasu i zapisz checkpoint."
                    )
                return
            if not isinstance(value, StoredComparisonTimeline):
                self._storage_failed(
                    generation,
                    operation,
                    "Niepoprawny artefakt osi czasu.",
                )
                return
            self._loaded_artifact_id = value.artifact.id
            self._apply_configuration(value.configuration)
            self._apply_result(value.result)
            self.status_label.setText(
                self._ready_status(
                    value.result,
                    prefix=(
                        "Wczytano zapisane wyrównanie bez skanowania sesji"
                    ),
                )
            )
        elif operation == "save":
            if not isinstance(value, Artifact):
                self._storage_failed(
                    generation,
                    operation,
                    "Niepoprawny zapis artefaktu.",
                )
                return
            self._loaded_artifact_id = value.id
            self.status_label.setText(
                "Zapisano wersjonowany artefakt wyrównania. "
                "Przy następnym otwarciu zostanie wczytany bez skanowania sesji."
            )

    @Slot(int, str, str)
    def _storage_failed(
        self,
        generation: int,
        operation: str,
        error: str,
    ) -> None:
        if generation != self._storage_generation:
            return
        action = "wczytać" if operation == "load" else "zapisać"
        self.status_label.setText(
            f"Nie udało się {action} wyrównania: {error}"
        )

    @Slot(int, str)
    def _storage_finished(self, generation: int, _operation: str) -> None:
        self._storage_tasks.pop(generation, None)
        if not self._tasks and not self._storage_tasks:
            self._set_running(False)

    def _apply_result(self, result: ComparisonTimelineResult) -> None:
        self._current_result = result
        self.canvas.set_result(result)
        self._populate_lanes(result)
        self._clear_selection()
        self.save_button.setEnabled(True)

    def _apply_configuration(
        self,
        configuration: TimelineAnchorConfiguration,
    ) -> None:
        index = self.mode_combo.findData(configuration.synchronization_mode)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        if configuration.synchronization_mode == SYNC_MESSAGE_KEY:
            self.anchor_edit.setText(configuration.anchor_message_key)
        elif configuration.synchronization_mode == SYNC_OPERATOR_MARKER:
            self.anchor_edit.setText(configuration.anchor_marker_name)
        else:
            self.anchor_edit.clear()
        self.occurrence_spin.setValue(configuration.anchor_occurrence)
        self._explicit_anchor_rows = configuration.explicit_rows
        self._update_explicit_anchor_summary()
        self._mode_changed()

    def _configuration_from_controls(self) -> TimelineAnchorConfiguration:
        mode = str(self.mode_combo.currentData() or SYNC_SESSION_START)
        anchor_value = self.anchor_edit.text().strip()
        return normalize_timeline_configuration(
            synchronization_mode=mode,
            anchor_message_key=(
                anchor_value if mode == SYNC_MESSAGE_KEY else ""
            ),
            anchor_marker_name=(
                anchor_value if mode == SYNC_OPERATOR_MARKER else ""
            ),
            anchor_occurrence=self.occurrence_spin.value(),
            explicit_anchor_rows=(
                self._explicit_anchor_rows
                if mode == SYNC_EXPLICIT_EVENT
                else {}
            ),
        )

    def _populate_lanes(self, result: ComparisonTimelineResult) -> None:
        self.lanes_table.setRowCount(0)
        for lane in result.lanes:
            row = self.lanes_table.rowCount()
            self.lanes_table.insertRow(row)
            duration_ns = (
                0
                if lane.first_timestamp_ns is None
                or lane.last_timestamp_ns is None
                else max(0, lane.last_timestamp_ns - lane.first_timestamp_ns)
            )
            anchor_text = (
                "—"
                if lane.anchor_source_row is None
                else (
                    f"{lane.anchor_source_row + 1}: "
                    f"{lane.anchor_label or lane.anchor_kind}"
                )
            )
            values = (
                lane.session_name,
                str(lane.total_frame_count),
                str(lane.sampled_frame_count),
                str(lane.sample_stride),
                anchor_text,
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
        self.set_anchor_button.setEnabled(False)
        self.selected_label.setText(
            "Kliknij punkt osi czasu, aby wskazać ramkę."
        )

    @Slot(object)
    def _event_selected(self, value: object) -> None:
        if not isinstance(value, ComparisonTimelineEvent):
            return
        self._selected_event = value
        self.open_button.setEnabled(True)
        self.set_anchor_button.setEnabled(True)
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
    def _set_selected_as_anchor(self) -> None:
        event = self._selected_event
        if event is None:
            return
        self._explicit_anchor_rows[event.session_id] = event.source_row
        self.clear_anchors_button.setEnabled(True)
        self._update_explicit_anchor_summary()
        self.status_label.setText(
            f"Ustawiono dokładną kotwicę dla sesji {event.session_name}: "
            f"ramka {event.source_row + 1}."
        )

    @Slot()
    def _clear_explicit_anchors(self) -> None:
        self._explicit_anchor_rows.clear()
        self._update_explicit_anchor_summary()
        self.status_label.setText(
            "Wyczyszczono dokładne kotwice zdarzeń."
        )

    def _update_explicit_anchor_summary(self) -> None:
        total = len(self.comparison_set.session_ids)
        selected = len(self._explicit_anchor_rows)
        self.explicit_anchors_label.setText(
            f"Dokładne kotwice: {selected}/{total}. "
            "Można je ustawić klikając punkty istniejącej osi."
        )
        self.clear_anchors_button.setEnabled(selected > 0)

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
        mode = self.mode_combo.currentData()
        message_mode = mode == SYNC_MESSAGE_KEY
        marker_mode = mode == SYNC_OPERATOR_MARKER
        explicit_mode = mode == SYNC_EXPLICIT_EVENT
        self.anchor_edit.setEnabled(message_mode or marker_mode)
        self.occurrence_spin.setEnabled(message_mode or marker_mode)
        self.anchor_label.setText(
            "Klucz wiadomości:"
            if message_mode
            else "Nazwa znacznika:"
            if marker_mode
            else "Kotwica:"
        )
        self.anchor_edit.setPlaceholderText(
            "Np. 0:EXT:1AFFB680:data"
            if message_mode
            else "Dokładna nazwa znacznika z sesji"
            if marker_mode
            else ""
        )
        self.explicit_anchors_label.setVisible(
            explicit_mode or bool(self._explicit_anchor_rows)
        )

    def _set_running(self, running: bool) -> None:
        any_running = running or bool(self._tasks or self._storage_tasks)
        self.build_button.setEnabled(not any_running)
        self.load_button.setEnabled(not any_running)
        self.save_button.setEnabled(
            not any_running and self._current_result is not None
        )
        self.cancel_button.setEnabled(any_running)
        self.mode_combo.setEnabled(not any_running)
        self.anchor_edit.setEnabled(
            not any_running
            and self.mode_combo.currentData()
            in {SYNC_MESSAGE_KEY, SYNC_OPERATOR_MARKER}
        )
        self.occurrence_spin.setEnabled(
            not any_running
            and self.mode_combo.currentData()
            in {SYNC_MESSAGE_KEY, SYNC_OPERATOR_MARKER}
        )

    @staticmethod
    def _ready_status(
        result: ComparisonTimelineResult,
        *,
        prefix: str,
    ) -> str:
        warning_text = (
            f" Ostrzeżenia: {len(result.warnings)}."
            if result.warnings
            else ""
        )
        sampled = sum(lane.sampled_frame_count for lane in result.lanes)
        return (
            f"{prefix}: {len(result.lanes)} sesje, "
            f"{sampled} punktów.{warning_text}"
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
