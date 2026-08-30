from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from PySide6.QtCore import QObject, QPointF, QRectF, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QMouseEvent, QPainter, QPaintEvent, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.extensions import CancellationToken, ExtensionCancelled, ProgressUpdate
from app.extensions.builtin import SIGNAL_DISCOVERY_PROVIDER_ID
from app.extensions.builtin.signal_discovery import bitfield_series_from_sample
from app.session_analysis_service import AnalysisExecutionResult, SessionAnalysisService

from .stored_search_navigation import StoredSearchNavigator


class _DiscoverySignals(QObject):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class _DiscoveryTask(QRunnable):
    def __init__(
        self,
        service: SessionAnalysisService,
        session_id: str,
        parameters: Mapping[str, Any],
    ) -> None:
        super().__init__()
        self.service = service
        self.session_id = session_id
        self.parameters = dict(parameters)
        self.cancellation = CancellationToken()
        self.signals = _DiscoverySignals()

    def cancel(self) -> None:
        self.cancellation.cancel()

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.run(
                SIGNAL_DISCOVERY_PROVIDER_ID,
                self.session_id,
                parameters=self.parameters,
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


class SignalPlotWidget(QWidget):
    """Small dependency-free plot for bounded signal evidence samples."""

    point_selected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("signalDiscoveryPlot")
        self.setMinimumHeight(260)
        self.setMouseTracking(True)
        self._series: tuple[Mapping[str, Any], ...] = ()
        self._screen_points: list[QPointF] = []
        self._selected_index = -1

    def set_series(self, series: Sequence[Mapping[str, Any]]) -> None:
        self._series = tuple(series)
        self._selected_index = -1
        self._screen_points.clear()
        self.update()

    @property
    def selected_point(self) -> Mapping[str, Any] | None:
        if 0 <= self._selected_index < len(self._series):
            return self._series[self._selected_index]
        return None

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = self.palette()
        text_color = palette.color(QPalette.ColorRole.Text)
        muted = palette.color(QPalette.ColorRole.Mid)
        accent = palette.color(QPalette.ColorRole.Highlight)

        plot_rect = QRectF(self.rect()).adjusted(58.0, 16.0, -18.0, -38.0)
        painter.setPen(QPen(muted, 1.0))
        painter.drawRect(plot_rect)

        if not self._series:
            painter.setPen(text_color)
            painter.drawText(plot_rect, Qt.AlignmentFlag.AlignCenter, "Brak punktów do wykresu")
            self._screen_points.clear()
            return

        timestamps = [int(point["timestamp_ns"]) for point in self._series]
        values = [float(point["value"]) for point in self._series]
        x_min = min(timestamps)
        x_max = max(timestamps)
        y_min = min(values)
        y_max = max(values)
        if x_max == x_min:
            x_max = x_min + 1
        if y_max == y_min:
            padding = max(1.0, abs(y_min) * 0.05)
            y_min -= padding
            y_max += padding

        points: list[QPointF] = []
        for timestamp, value in zip(timestamps, values, strict=True):
            x = plot_rect.left() + (
                (timestamp - x_min) / (x_max - x_min)
            ) * plot_rect.width()
            y = plot_rect.bottom() - ((value - y_min) / (y_max - y_min)) * plot_rect.height()
            points.append(QPointF(x, y))
        self._screen_points = points

        painter.setPen(QPen(accent, 1.5))
        if len(points) == 1:
            painter.drawEllipse(points[0], 3.0, 3.0)
        else:
            painter.drawPolyline(QPolygonF(points))

        if 0 <= self._selected_index < len(points):
            painter.setPen(QPen(accent, 2.0))
            painter.drawEllipse(points[self._selected_index], 5.0, 5.0)

        painter.setPen(text_color)
        painter.drawText(4, int(plot_rect.top() + 8), f"{y_max:.6g}")
        painter.drawText(4, int(plot_rect.bottom()), f"{y_min:.6g}")
        duration_s = (x_max - x_min) / 1e9
        painter.drawText(
            plot_rect,
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
            f"czas względny — zakres {duration_s:.6g} s",
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._screen_points:
            super().mousePressEvent(event)
            return
        position = event.position()
        nearest = min(
            range(len(self._screen_points)),
            key=lambda index: (
                (self._screen_points[index].x() - position.x()) ** 2
                + (self._screen_points[index].y() - position.y()) ** 2
            ),
        )
        self._selected_index = nearest
        self.update()
        self.point_selected.emit(dict(self._series[nearest]))


class SignalDiscoveryView(QWidget):
    """Passive Signal Discovery Stage 1 workspace for one stored session."""

    def __init__(
        self,
        *,
        service: SessionAnalysisService | None,
        session_record: object | None,
        session_view: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("signalDiscoveryWorkspace")
        self._service = service
        self._session_record = session_record
        self._task: _DiscoveryTask | None = None
        self._payload: dict[str, Any] | None = None
        self._byte_rows: list[Mapping[str, Any]] = []
        self._selected_plot_point: Mapping[str, Any] | None = None
        self._navigator = StoredSearchNavigator(
            session_view,  # type: ignore[arg-type]
            cancel_widget=self,
            parent=self,
        )
        self._build_ui()
        self._set_enabled(service is not None and session_record is not None)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        intro = QLabel(
            "Pasywna analiza jednego dokładnego klucza CAN. Surowa sesja pozostaje "
            "niezmieniona; statystyki liczone są na całej sesji, a wykres korzysta "
            "z deterministycznej próbki z zachowanym source_row.",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("Kanał:"))
        self.channel_spin = QSpinBox(self)
        self.channel_spin.setObjectName("signalDiscoveryChannel")
        self.channel_spin.setRange(0, 255)
        key_row.addWidget(self.channel_spin)

        key_row.addWidget(QLabel("CAN ID [hex]:"))
        self.can_id_edit = QLineEdit("123", self)
        self.can_id_edit.setObjectName("signalDiscoveryCanId")
        self.can_id_edit.setMaximumWidth(150)
        key_row.addWidget(self.can_id_edit)

        self.id_format_combo = QComboBox(self)
        self.id_format_combo.setObjectName("signalDiscoveryIdFormat")
        self.id_format_combo.addItem("STD 11-bit", False)
        self.id_format_combo.addItem("EXT 29-bit", True)
        key_row.addWidget(self.id_format_combo)

        self.frame_kind_combo = QComboBox(self)
        self.frame_kind_combo.setObjectName("signalDiscoveryFrameKind")
        self.frame_kind_combo.addItem("Data", "data")
        self.frame_kind_combo.addItem("RTR", "remote")
        self.frame_kind_combo.addItem("Error", "error")
        key_row.addWidget(self.frame_kind_combo)

        self.run_button = QPushButton("Analizuj aktywność", self)
        self.run_button.setObjectName("runSignalDiscovery")
        self.run_button.clicked.connect(self._start_analysis)
        key_row.addWidget(self.run_button)

        self.cancel_button = QPushButton("Anuluj", self)
        self.cancel_button.setObjectName("cancelSignalDiscovery")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_analysis)
        key_row.addWidget(self.cancel_button)
        key_row.addStretch(1)
        root.addLayout(key_row)

        self.progress = QProgressBar(self)
        self.progress.setObjectName("signalDiscoveryProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Oczekiwanie")
        root.addWidget(self.progress)

        self.status_label = QLabel("Gotowe.", self)
        self.status_label.setObjectName("signalDiscoveryStatus")
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.status_label)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root.addWidget(splitter, 1)

        activity_group = QGroupBox("Byte / Bit Activity Map", splitter)
        activity_layout = QVBoxLayout(activity_group)
        self.summary_label = QLabel("Uruchom analizę wybranego klucza CAN.", activity_group)
        self.summary_label.setWordWrap(True)
        activity_layout.addWidget(self.summary_label)

        self.activity_table = QTableWidget(0, 13, activity_group)
        self.activity_table.setObjectName("signalDiscoveryActivityTable")
        self.activity_table.setHorizontalHeaderLabels(
            (
                "Byte",
                "Obecny",
                "Brak",
                "Zakres",
                "Unikalne",
                "Zmiana %",
                "B7",
                "B6",
                "B5",
                "B4",
                "B3",
                "B2",
                "B1/B0",
            )
        )
        self.activity_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.activity_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.activity_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.activity_table.verticalHeader().hide()
        header = self.activity_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        activity_layout.addWidget(self.activity_table, 1)

        evidence_row = QHBoxLayout()
        self.open_min_button = QPushButton("Otwórz ramkę MIN", activity_group)
        self.open_min_button.setObjectName("signalDiscoveryOpenMin")
        self.open_min_button.clicked.connect(lambda: self._open_selected_byte_evidence("min_source_row"))
        evidence_row.addWidget(self.open_min_button)
        self.open_max_button = QPushButton("Otwórz ramkę MAX", activity_group)
        self.open_max_button.setObjectName("signalDiscoveryOpenMax")
        self.open_max_button.clicked.connect(lambda: self._open_selected_byte_evidence("max_source_row"))
        evidence_row.addWidget(self.open_max_button)
        evidence_row.addStretch(1)
        activity_layout.addLayout(evidence_row)
        splitter.addWidget(activity_group)

        inspector_group = QGroupBox("Arbitrary Bitfield Inspector / Plotter", splitter)
        inspector_layout = QVBoxLayout(inspector_group)
        form = QFormLayout()
        self.start_bit_spin = QSpinBox(inspector_group)
        self.start_bit_spin.setObjectName("signalDiscoveryStartBit")
        self.start_bit_spin.setRange(0, 511)
        form.addRow("Start bit:", self.start_bit_spin)

        self.length_spin = QSpinBox(inspector_group)
        self.length_spin.setObjectName("signalDiscoveryLength")
        self.length_spin.setRange(1, 64)
        self.length_spin.setValue(8)
        form.addRow("Length:", self.length_spin)

        self.byte_order_combo = QComboBox(inspector_group)
        self.byte_order_combo.setObjectName("signalDiscoveryByteOrder")
        self.byte_order_combo.addItem("Intel / little endian", "intel")
        self.byte_order_combo.addItem("Motorola / big endian (DBC)", "motorola")
        form.addRow("Byte order:", self.byte_order_combo)

        self.signed_check = QCheckBox("signed", inspector_group)
        self.signed_check.setObjectName("signalDiscoverySigned")
        form.addRow("Typ:", self.signed_check)

        self.scale_spin = QDoubleSpinBox(inspector_group)
        self.scale_spin.setObjectName("signalDiscoveryScale")
        self.scale_spin.setDecimals(9)
        self.scale_spin.setRange(-1_000_000_000.0, 1_000_000_000.0)
        self.scale_spin.setValue(1.0)
        form.addRow("Scale:", self.scale_spin)

        self.offset_spin = QDoubleSpinBox(inspector_group)
        self.offset_spin.setObjectName("signalDiscoveryOffset")
        self.offset_spin.setDecimals(9)
        self.offset_spin.setRange(-1_000_000_000.0, 1_000_000_000.0)
        self.offset_spin.setValue(0.0)
        form.addRow("Offset:", self.offset_spin)
        inspector_layout.addLayout(form)

        self.plot_button = QPushButton("Przelicz wykres", inspector_group)
        self.plot_button.setObjectName("signalDiscoveryPlotButton")
        self.plot_button.clicked.connect(self._update_plot)
        inspector_layout.addWidget(self.plot_button)

        self.plot = SignalPlotWidget(inspector_group)
        self.plot.point_selected.connect(self._plot_point_selected)
        inspector_layout.addWidget(self.plot, 1)

        self.point_label = QLabel("Kliknij punkt wykresu, aby zobaczyć dowód.", inspector_group)
        self.point_label.setWordWrap(True)
        inspector_layout.addWidget(self.point_label)
        self.open_plot_source_button = QPushButton("Otwórz ramkę źródłową punktu", inspector_group)
        self.open_plot_source_button.setObjectName("signalDiscoveryOpenPlotSource")
        self.open_plot_source_button.clicked.connect(self._open_plot_source)
        inspector_layout.addWidget(self.open_plot_source_button)
        splitter.addWidget(inspector_group)
        splitter.setSizes((760, 620))

        self._refresh_evidence_buttons()
        self.activity_table.itemSelectionChanged.connect(self._refresh_evidence_buttons)

    def _set_enabled(self, enabled: bool) -> None:
        for widget in (
            self.channel_spin,
            self.can_id_edit,
            self.id_format_combo,
            self.frame_kind_combo,
            self.run_button,
        ):
            widget.setEnabled(enabled)
        if not enabled:
            self.status_label.setText("Signal Discovery wymaga zapisanej sesji w projekcie CRT.")
        self.plot_button.setEnabled(False)
        self.open_plot_source_button.setEnabled(False)

    @Slot()
    def _start_analysis(self) -> None:
        if self._task is not None or self._service is None or self._session_record is None:
            return
        can_text = self.can_id_edit.text().strip()
        try:
            arbitration_id = int(can_text[2:], 16) if can_text.lower().startswith("0x") else int(can_text, 16)
        except ValueError:
            self.status_label.setText("Nieprawidłowy CAN ID — wpisz wartość szesnastkową, np. 18FEEE00.")
            return

        parameters = {
            "channel": self.channel_spin.value(),
            "arbitration_id": arbitration_id,
            "is_extended_id": bool(self.id_format_combo.currentData()),
            "frame_kind": str(self.frame_kind_combo.currentData()),
            "sample_limit": 5_000,
        }
        session_id = str(getattr(self._session_record, "id", ""))
        if not session_id:
            self.status_label.setText("Brak ID zapisanej sesji.")
            return

        task = _DiscoveryTask(self._service, session_id, parameters)
        task.signals.progress.connect(self._analysis_progress)
        task.signals.completed.connect(self._analysis_completed)
        task.signals.failed.connect(self._analysis_failed)
        task.signals.cancelled.connect(self._analysis_cancelled)
        self._task = task
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 0)
        self.progress.setFormat("Uruchamianie…")
        self.status_label.setText("Signal Discovery pracuje pasywnie w tle…")
        QThreadPool.globalInstance().start(task)

    @Slot()
    def _cancel_analysis(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Anulowanie Signal Discovery…")

    @Slot(int, int, str)
    def _analysis_progress(self, current: int, total: int, message: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
            self.progress.setFormat(f"{current:,}/{total:,}".replace(",", " "))
        else:
            self.progress.setRange(0, 0)
        self.status_label.setText(message or "Analiza w toku…")

    @Slot(object)
    def _analysis_completed(self, result: object) -> None:
        self._finish_task()
        execution = result if isinstance(result, AnalysisExecutionResult) else None
        if execution is None or not execution.artifacts or self._service is None:
            self._analysis_failed("provider nie zwrócił artefaktu Signal Discovery")
            return
        try:
            payload = self._service.artifacts.read_json(execution.artifacts[0])
        except Exception as exc:
            self._analysis_failed(f"nie można odczytać artefaktu: {exc}")
            return
        if not isinstance(payload, dict) or payload.get("schema") != "crt.signal_discovery_activity":
            self._analysis_failed("nieprawidłowy schemat artefaktu Signal Discovery")
            return

        self._payload = payload
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("Gotowe — 100%")
        self.status_label.setText("Analiza zakończona. Artefakt i dowody zostały zapisane w projekcie.")
        self._render_activity()
        self._update_plot()

    @Slot(str)
    def _analysis_failed(self, error: str) -> None:
        self._finish_task()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Błąd")
        self.status_label.setText(f"Signal Discovery: {error}")

    @Slot()
    def _analysis_cancelled(self) -> None:
        self._finish_task()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Anulowano")
        self.status_label.setText("Analiza anulowana. Sesja źródłowa nie została zmieniona.")

    def _finish_task(self) -> None:
        self._task = None
        enabled = self._service is not None and self._session_record is not None
        self.run_button.setEnabled(enabled)
        self.cancel_button.setEnabled(False)

    def _render_activity(self) -> None:
        payload = self._payload or {}
        key = payload.get("message_key") if isinstance(payload.get("message_key"), dict) else {}
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        sample = payload.get("sample") if isinstance(payload.get("sample"), dict) else {}
        self.summary_label.setText(
            f"Ch {key.get('channel', '—')} | "
            f"{'EXT' if key.get('is_extended_id') else 'STD'} 0x{key.get('arbitration_id_hex', '—')} | "
            f"{key.get('frame_kind', '—')} | "
            f"ramki: {summary.get('matching_frame_count', 0)} | "
            f"DLC: {summary.get('min_dlc', '—')}..{summary.get('max_dlc', '—')} | "
            f"próbka wykresu: {sample.get('sampled_frame_count', 0)}/{sample.get('matching_frame_count', 0)}"
        )

        byte_rows = payload.get("bytes") if isinstance(payload.get("bytes"), list) else []
        self._byte_rows = [row for row in byte_rows if isinstance(row, dict)]
        self.activity_table.setRowCount(len(self._byte_rows))
        for row_index, byte in enumerate(self._byte_rows):
            bits = byte.get("bits") if isinstance(byte.get("bits"), list) else []
            bit_map = {
                int(bit.get("bit", -1)): bit
                for bit in bits
                if isinstance(bit, dict) and isinstance(bit.get("bit"), int)
            }
            change_rate = byte.get("change_rate")
            values = [
                str(byte.get("byte", row_index)),
                str(byte.get("present_count", 0)),
                str(byte.get("missing_count", 0)),
                f"{_hex_byte(byte.get('min_value'))}..{_hex_byte(byte.get('max_value'))}",
                str(byte.get("unique_value_count", 0)),
                _percent(change_rate),
            ]
            for bit_index in range(7, 0, -1):
                values.append(_format_bit(bit_map.get(bit_index)))
            values.append(
                f"B1 {_format_bit(bit_map.get(1))} | B0 {_format_bit(bit_map.get(0))}"
            )
            for column, text in enumerate(values):
                self.activity_table.setItem(row_index, column, QTableWidgetItem(text))

        max_dlc = summary.get("max_dlc")
        if isinstance(max_dlc, int) and max_dlc > 0:
            self.start_bit_spin.setMaximum(max(0, max_dlc * 8 - 1))
        self.plot_button.setEnabled(bool(self._byte_rows) and bool(sample.get("frames")))
        if self._byte_rows:
            self.activity_table.selectRow(0)
        self._refresh_evidence_buttons()

    @Slot()
    def _update_plot(self) -> None:
        payload = self._payload or {}
        sample = payload.get("sample") if isinstance(payload.get("sample"), dict) else {}
        frames = sample.get("frames") if isinstance(sample.get("frames"), list) else []
        if not frames:
            self.plot.set_series(())
            self.point_label.setText("Brak próbek wybranego klucza CAN.")
            self._selected_plot_point = None
            self.open_plot_source_button.setEnabled(False)
            return
        try:
            series = bitfield_series_from_sample(
                frames,
                start_bit=self.start_bit_spin.value(),
                length=self.length_spin.value(),
                byte_order=str(self.byte_order_combo.currentData()),
                signed=self.signed_check.isChecked(),
                scale=self.scale_spin.value(),
                offset=self.offset_spin.value(),
            )
        except Exception as exc:
            self.status_label.setText(f"Nie można zdekodować bitfielda: {exc}")
            return
        self.plot.set_series(series)
        self._selected_plot_point = None
        self.open_plot_source_button.setEnabled(False)
        if series:
            values = [float(point["value"]) for point in series]
            self.point_label.setText(
                f"Punkty: {len(series)} | min={min(values):.9g} | max={max(values):.9g}. "
                "Kliknij punkt, aby przejść do dokładnej ramki."
            )
        else:
            self.point_label.setText(
                "Wybrane pole nie mieści się w payloadzie żadnej ramki z próbki."
            )

    @Slot(object)
    def _plot_point_selected(self, point: object) -> None:
        if not isinstance(point, dict):
            return
        self._selected_plot_point = point
        self.open_plot_source_button.setEnabled(True)
        payload = self._payload or {}
        sample = payload.get("sample") if isinstance(payload.get("sample"), dict) else {}
        frames = sample.get("frames") if isinstance(sample.get("frames"), list) else []
        t0 = int(frames[0].get("timestamp_ns", point.get("timestamp_ns", 0))) if frames else int(point.get("timestamp_ns", 0))
        relative_s = (int(point.get("timestamp_ns", t0)) - t0) / 1e9
        self.point_label.setText(
            f"source_row={point.get('source_row')} | t={relative_s:.9g} s | "
            f"raw={point.get('raw')} | value={float(point.get('value', 0.0)):.9g}"
        )

    @Slot()
    def _open_plot_source(self) -> None:
        point = self._selected_plot_point
        if point is None:
            return
        source_row = point.get("source_row")
        if isinstance(source_row, int):
            self._navigator.navigate_to_source_row(source_row)

    def _open_selected_byte_evidence(self, field: str) -> None:
        row = self.activity_table.currentRow()
        if not 0 <= row < len(self._byte_rows):
            return
        source_row = self._byte_rows[row].get(field)
        if isinstance(source_row, int):
            self._navigator.navigate_to_source_row(source_row)

    @Slot()
    def _refresh_evidence_buttons(self) -> None:
        row = self.activity_table.currentRow()
        byte = self._byte_rows[row] if 0 <= row < len(self._byte_rows) else None
        self.open_min_button.setEnabled(bool(byte and isinstance(byte.get("min_source_row"), int)))
        self.open_max_button.setEnabled(bool(byte and isinstance(byte.get("max_source_row"), int)))

    def shutdown(self) -> None:
        if self._task is not None:
            self._task.cancel()
        self._navigator.close()


def _hex_byte(value: object) -> str:
    return f"0x{value:02X}" if isinstance(value, int) else "—"


def _percent(value: object) -> str:
    return f"{float(value) * 100.0:.2f}%" if isinstance(value, (int, float)) else "—"


def _format_bit(bit: Mapping[str, Any] | None) -> str:
    if bit is None:
        return "—"
    ratio = bit.get("set_ratio")
    transitions = bit.get("transition_count", 0)
    if not isinstance(ratio, (int, float)):
        return "—"
    return f"{float(ratio) * 100.0:.0f}% Δ{transitions}"


__all__ = ["SignalDiscoveryView", "SignalPlotWidget"]
