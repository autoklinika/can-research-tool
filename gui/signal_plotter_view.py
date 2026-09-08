from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from PySide6.QtCore import QObject, QPointF, QRectF, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QMouseEvent, QPainter, QPaintEvent, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.domain import Artifact
from app.extensions import CancellationToken, ExtensionCancelled, ProgressUpdate
from app.extensions.builtin import DEFAULT_MAXIMUM_POINTS, MAXIMUM_POINTS_LIMIT
from app.signal_plot_service import SignalPlotService, cursor_delta, decimate_for_render, nearest_point_index

from .stored_search_navigation import StoredSearchNavigator


class _PlotSignals(QObject):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class _PlotTask(QRunnable):
    def __init__(
        self,
        service: SignalPlotService,
        session_id: str,
        parameters: Mapping[str, Any],
    ) -> None:
        super().__init__()
        self.service = service
        self.session_id = session_id
        self.parameters = dict(parameters)
        self.cancellation = CancellationToken()
        self.signals = _PlotSignals()

    def cancel(self) -> None:
        self.cancellation.cancel()

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.run(
                self.session_id,
                parameters=self.parameters,
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


class FullSignalPlotWidget(QWidget):
    """Dependency-free full-series plot with exact A/B cursor selection."""

    cursor_changed = Signal(str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("fullSignalPlotCanvas")
        self.setMinimumHeight(360)
        self.setMouseTracking(True)
        self._points: tuple[Mapping[str, Any], ...] = ()
        self._cursor_a = -1
        self._cursor_b = -1
        self._active_cursor = "A"

    def set_series(self, points: Sequence[Mapping[str, Any]]) -> None:
        self._points = tuple(points)
        self._cursor_a = -1
        self._cursor_b = -1
        self.update()

    def set_active_cursor(self, name: str) -> None:
        normalized = str(name).strip().upper()
        if normalized not in {"A", "B"}:
            raise ValueError("cursor must be A or B")
        self._active_cursor = normalized

    @property
    def points(self) -> tuple[Mapping[str, Any], ...]:
        return self._points

    def cursor_point(self, name: str) -> Mapping[str, Any] | None:
        normalized = str(name).strip().upper()
        index = self._cursor_a if normalized == "A" else self._cursor_b
        if 0 <= index < len(self._points):
            return self._points[index]
        return None

    def set_cursor_index(self, name: str, index: int) -> None:
        if not 0 <= index < len(self._points):
            raise IndexError("cursor index outside series")
        normalized = str(name).strip().upper()
        if normalized == "A":
            self._cursor_a = index
        elif normalized == "B":
            self._cursor_b = index
        else:
            raise ValueError("cursor must be A or B")
        self.update()
        self.cursor_changed.emit(normalized, dict(self._points[index]))

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = self.palette()
        text_color = palette.color(QPalette.ColorRole.Text)
        muted = palette.color(QPalette.ColorRole.Mid)
        accent = palette.color(QPalette.ColorRole.Highlight)
        secondary = palette.color(QPalette.ColorRole.Link)

        plot_rect = QRectF(self.rect()).adjusted(64.0, 18.0, -20.0, -44.0)
        painter.setPen(QPen(muted, 1.0))
        painter.drawRect(plot_rect)
        if not self._points:
            painter.setPen(text_color)
            painter.drawText(plot_rect, Qt.AlignmentFlag.AlignCenter, "Brak pełnej serii do wykresu")
            return

        x_min, x_max, y_min, y_max = self._ranges()
        render_limit = max(400, min(8000, int(max(1.0, plot_rect.width())) * 3))
        render_points = decimate_for_render(self._points, render_limit)
        polygon = QPolygonF(
            [self._screen_point(point, plot_rect, x_min, x_max, y_min, y_max) for point in render_points]
        )
        painter.setPen(QPen(accent, 1.4))
        if len(polygon) == 1:
            painter.drawEllipse(polygon[0], 3.0, 3.0)
        else:
            painter.drawPolyline(polygon)

        self._draw_cursor(
            painter,
            "A",
            self._cursor_a,
            accent,
            plot_rect,
            x_min,
            x_max,
            y_min,
            y_max,
        )
        self._draw_cursor(
            painter,
            "B",
            self._cursor_b,
            secondary,
            plot_rect,
            x_min,
            x_max,
            y_min,
            y_max,
        )

        painter.setPen(text_color)
        painter.drawText(4, int(plot_rect.top() + 8), f"{y_max:.6g}")
        painter.drawText(4, int(plot_rect.bottom()), f"{y_min:.6g}")
        duration_s = (x_max - x_min) / 1e9
        painter.drawText(
            plot_rect,
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
            f"pełna seria — zakres {duration_s:.6g} s",
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._points:
            super().mousePressEvent(event)
            return
        plot_rect = QRectF(self.rect()).adjusted(64.0, 18.0, -20.0, -44.0)
        if not plot_rect.contains(event.position()):
            super().mousePressEvent(event)
            return
        x_min = int(self._points[0]["timestamp_ns"])
        x_max = int(self._points[-1]["timestamp_ns"])
        if x_max == x_min:
            target = x_min
        else:
            ratio = (event.position().x() - plot_rect.left()) / max(1.0, plot_rect.width())
            ratio = max(0.0, min(1.0, ratio))
            target = round(x_min + ratio * (x_max - x_min))
        index = nearest_point_index(self._points, target)
        self.set_cursor_index(self._active_cursor, index)

    def _ranges(self) -> tuple[int, int, float, float]:
        x_min = int(self._points[0]["timestamp_ns"])
        x_max = int(self._points[-1]["timestamp_ns"])
        if x_max == x_min:
            x_max = x_min + 1
        values = [float(point["value"]) for point in self._points]
        y_min = min(values)
        y_max = max(values)
        if y_max == y_min:
            padding = max(1.0, abs(y_min) * 0.05)
            y_min -= padding
            y_max += padding
        return x_min, x_max, y_min, y_max

    @staticmethod
    def _screen_point(
        point: Mapping[str, Any],
        rect: QRectF,
        x_min: int,
        x_max: int,
        y_min: float,
        y_max: float,
    ) -> QPointF:
        timestamp = int(point["timestamp_ns"])
        value = float(point["value"])
        x = rect.left() + ((timestamp - x_min) / (x_max - x_min)) * rect.width()
        y = rect.bottom() - ((value - y_min) / (y_max - y_min)) * rect.height()
        return QPointF(x, y)

    def _draw_cursor(
        self,
        painter: QPainter,
        name: str,
        index: int,
        color,
        rect: QRectF,
        x_min: int,
        x_max: int,
        y_min: float,
        y_max: float,
    ) -> None:
        if not 0 <= index < len(self._points):
            return
        point = self._screen_point(self._points[index], rect, x_min, x_max, y_min, y_max)
        painter.setPen(QPen(color, 1.5))
        painter.drawLine(QPointF(point.x(), rect.top()), QPointF(point.x(), rect.bottom()))
        painter.drawEllipse(point, 5.0, 5.0)
        painter.drawText(int(point.x() + 5), int(rect.top() + 14), name)


class SignalPlotterView(QWidget):
    """Full Signal Plotter Stage 1 workspace for one stored CRT session."""

    output_message = Signal(str)

    def __init__(
        self,
        *,
        service: SignalPlotService | None,
        session_record: object | None,
        session_view: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("fullSignalPlotterWorkspace")
        self._service = service
        self._session_record = session_record
        self._task: _PlotTask | None = None
        self._artifacts: tuple[Artifact, ...] = ()
        self._payload: Mapping[str, Any] | None = None
        self._navigator = StoredSearchNavigator(
            session_view,  # type: ignore[arg-type]
            cancel_widget=self,
            parent=self,
        )
        self._build_ui()
        self._set_enabled(service is not None and session_record is not None)
        self._load_artifacts()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        intro = QLabel(
            "Full Signal Plotter skanuje całą zapisaną sesję dla jednego dokładnego klucza CAN. "
            "Artefakt zawiera wszystkie punkty pola bez próbkowania; redukcja może dotyczyć tylko "
            "rysowania. Kursory A/B zawsze wskazują rzeczywiste punkty z source_row.",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root.addWidget(splitter, 1)

        controls_group = QGroupBox("Sygnał", splitter)
        controls_layout = QVBoxLayout(controls_group)
        form = QFormLayout()
        self.channel_spin = QSpinBox(controls_group)
        self.channel_spin.setObjectName("signalPlotterChannel")
        self.channel_spin.setRange(0, 255)
        form.addRow("Kanał:", self.channel_spin)

        self.can_id_edit = QLineEdit("123", controls_group)
        self.can_id_edit.setObjectName("signalPlotterCanId")
        form.addRow("CAN ID [hex]:", self.can_id_edit)

        self.id_format_combo = QComboBox(controls_group)
        self.id_format_combo.setObjectName("signalPlotterIdFormat")
        self.id_format_combo.addItem("STD 11-bit", False)
        self.id_format_combo.addItem("EXT 29-bit", True)
        form.addRow("Format:", self.id_format_combo)

        self.frame_kind_combo = QComboBox(controls_group)
        self.frame_kind_combo.setObjectName("signalPlotterFrameKind")
        self.frame_kind_combo.addItem("Data", "data")
        self.frame_kind_combo.addItem("RTR", "remote")
        self.frame_kind_combo.addItem("Error", "error")
        form.addRow("Ramka:", self.frame_kind_combo)

        self.start_bit_spin = QSpinBox(controls_group)
        self.start_bit_spin.setObjectName("signalPlotterStartBit")
        self.start_bit_spin.setRange(0, 511)
        form.addRow("Start bit:", self.start_bit_spin)

        self.length_spin = QSpinBox(controls_group)
        self.length_spin.setObjectName("signalPlotterLength")
        self.length_spin.setRange(1, 64)
        self.length_spin.setValue(8)
        form.addRow("Length:", self.length_spin)

        self.byte_order_combo = QComboBox(controls_group)
        self.byte_order_combo.setObjectName("signalPlotterByteOrder")
        self.byte_order_combo.addItem("Intel / little endian", "intel")
        self.byte_order_combo.addItem("Motorola / big endian (DBC)", "motorola")
        form.addRow("Byte order:", self.byte_order_combo)

        self.signed_check = QCheckBox("signed", controls_group)
        self.signed_check.setObjectName("signalPlotterSigned")
        form.addRow("Typ:", self.signed_check)

        self.scale_spin = QDoubleSpinBox(controls_group)
        self.scale_spin.setObjectName("signalPlotterScale")
        self.scale_spin.setDecimals(9)
        self.scale_spin.setRange(-1_000_000_000.0, 1_000_000_000.0)
        self.scale_spin.setValue(1.0)
        form.addRow("Scale:", self.scale_spin)

        self.offset_spin = QDoubleSpinBox(controls_group)
        self.offset_spin.setObjectName("signalPlotterOffset")
        self.offset_spin.setDecimals(9)
        self.offset_spin.setRange(-1_000_000_000.0, 1_000_000_000.0)
        self.offset_spin.setValue(0.0)
        form.addRow("Offset:", self.offset_spin)

        self.maximum_points_spin = QSpinBox(controls_group)
        self.maximum_points_spin.setObjectName("signalPlotterMaximumPoints")
        self.maximum_points_spin.setRange(1, MAXIMUM_POINTS_LIMIT)
        self.maximum_points_spin.setValue(DEFAULT_MAXIMUM_POINTS)
        self.maximum_points_spin.setSingleStep(10_000)
        form.addRow("Limit bezpieczeństwa:", self.maximum_points_spin)
        controls_layout.addLayout(form)

        action_row = QHBoxLayout()
        self.run_button = QPushButton("Zbuduj pełną serię", controls_group)
        self.run_button.setObjectName("runFullSignalPlotter")
        self.run_button.clicked.connect(self._start)
        action_row.addWidget(self.run_button)
        self.cancel_button = QPushButton("Anuluj", controls_group)
        self.cancel_button.setObjectName("cancelFullSignalPlotter")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.setEnabled(False)
        action_row.addWidget(self.cancel_button)
        controls_layout.addLayout(action_row)

        self.progress = QProgressBar(controls_group)
        self.progress.setObjectName("signalPlotterProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Oczekiwanie")
        controls_layout.addWidget(self.progress)

        self.status_label = QLabel("Gotowe.", controls_group)
        self.status_label.setObjectName("signalPlotterStatus")
        self.status_label.setWordWrap(True)
        controls_layout.addWidget(self.status_label)

        controls_layout.addWidget(QLabel("Artefakt pełnej serii:", controls_group))
        self.artifact_combo = QComboBox(controls_group)
        self.artifact_combo.setObjectName("signalPlotterArtifact")
        self.artifact_combo.currentIndexChanged.connect(self._artifact_changed)
        controls_layout.addWidget(self.artifact_combo)
        self.refresh_button = QPushButton("Odśwież artefakty", controls_group)
        self.refresh_button.setObjectName("signalPlotterRefreshArtifacts")
        self.refresh_button.clicked.connect(self._load_artifacts)
        controls_layout.addWidget(self.refresh_button)
        controls_layout.addStretch(1)
        splitter.addWidget(controls_group)

        plot_group = QGroupBox("Pełny wykres + kursory A/B", splitter)
        plot_layout = QVBoxLayout(plot_group)
        cursor_row = QHBoxLayout()
        cursor_row.addWidget(QLabel("Aktywny kursor:", plot_group))
        self.cursor_combo = QComboBox(plot_group)
        self.cursor_combo.setObjectName("signalPlotterActiveCursor")
        self.cursor_combo.addItems(("A", "B"))
        self.cursor_combo.currentTextChanged.connect(self.plot_active_cursor_changed)
        cursor_row.addWidget(self.cursor_combo)
        cursor_row.addStretch(1)
        self.open_a_button = QPushButton("Otwórz A w RAW", plot_group)
        self.open_a_button.setObjectName("signalPlotterOpenCursorA")
        self.open_a_button.clicked.connect(lambda: self._open_cursor("A"))
        cursor_row.addWidget(self.open_a_button)
        self.open_b_button = QPushButton("Otwórz B w RAW", plot_group)
        self.open_b_button.setObjectName("signalPlotterOpenCursorB")
        self.open_b_button.clicked.connect(lambda: self._open_cursor("B"))
        cursor_row.addWidget(self.open_b_button)
        plot_layout.addLayout(cursor_row)

        self.plot = FullSignalPlotWidget(plot_group)
        self.plot.cursor_changed.connect(self._cursor_changed)
        plot_layout.addWidget(self.plot, 1)

        self.cursor_label = QLabel(
            "Kliknij wykres, aby ustawić aktywny kursor na najbliższym rzeczywistym punkcie.",
            plot_group,
        )
        self.cursor_label.setObjectName("signalPlotterCursorSummary")
        self.cursor_label.setWordWrap(True)
        self.cursor_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        plot_layout.addWidget(self.cursor_label)

        self.series_label = QLabel("Brak wczytanej serii.", plot_group)
        self.series_label.setObjectName("signalPlotterSeriesSummary")
        self.series_label.setWordWrap(True)
        self.series_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        plot_layout.addWidget(self.series_label)
        splitter.addWidget(plot_group)
        splitter.setSizes((360, 1040))
        self._refresh_cursor_buttons()

    @Slot(str)
    def plot_active_cursor_changed(self, name: str) -> None:
        self.plot.set_active_cursor(name)

    def _set_enabled(self, enabled: bool) -> None:
        for widget in (
            self.channel_spin,
            self.can_id_edit,
            self.id_format_combo,
            self.frame_kind_combo,
            self.start_bit_spin,
            self.length_spin,
            self.byte_order_combo,
            self.signed_check,
            self.scale_spin,
            self.offset_spin,
            self.maximum_points_spin,
            self.run_button,
        ):
            widget.setEnabled(enabled)
        self.refresh_button.setEnabled(enabled)
        if not enabled:
            self.status_label.setText("Full Signal Plotter wymaga zapisanej sesji w projekcie CRT.")

    @Slot()
    def _start(self) -> None:
        service = self._service
        record = self._session_record
        if self._task is not None or service is None or record is None:
            return
        parameters = {
            "channel": self.channel_spin.value(),
            "arbitration_id": self.can_id_edit.text().strip(),
            "is_extended_id": bool(self.id_format_combo.currentData()),
            "frame_kind": str(self.frame_kind_combo.currentData()),
            "start_bit": self.start_bit_spin.value(),
            "length": self.length_spin.value(),
            "byte_order": str(self.byte_order_combo.currentData()),
            "signed": self.signed_check.isChecked(),
            "scale": self.scale_spin.value(),
            "offset": self.offset_spin.value(),
            "maximum_points": self.maximum_points_spin.value(),
        }
        task = _PlotTask(service, str(getattr(record, "id", "")), parameters)
        task.signals.progress.connect(self._progress_changed)
        task.signals.completed.connect(self._completed)
        task.signals.failed.connect(self._failed)
        task.signals.cancelled.connect(self._cancelled)
        self._task = task
        self._set_running(True)
        self.progress.setRange(0, 0)
        self.progress.setFormat("Skanowanie pełnej sesji…")
        self.status_label.setText("Budowanie pełnej, niepróbkowanej serii w tle…")
        QThreadPool.globalInstance().start(task)

    @Slot()
    def _cancel(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Anulowanie… źródłowa sesja pozostaje niezmieniona.")

    @Slot(int, int, str)
    def _progress_changed(self, current: int, total: int, message: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
            self.progress.setFormat(f"{current:,}/{total:,}".replace(",", " "))
        else:
            self.progress.setRange(0, 0)
        self.status_label.setText(message or "Skanowanie…")

    @Slot(object)
    def _completed(self, result: object) -> None:
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("Gotowe — 100%")
        artifacts = tuple(getattr(result, "artifacts", ()) or ())
        preferred = artifacts[0].id if artifacts else ""
        self.status_label.setText("Pełna seria została zapisana bez próbkowania.")
        self.output_message.emit("Full Signal Plotter: zapisano pełną serię")
        self._load_artifacts(preferred)

    @Slot(str)
    def _failed(self, error: str) -> None:
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Błąd")
        self.status_label.setText(f"Full Signal Plotter nie wykonał analizy: {error}")

    @Slot()
    def _cancelled(self) -> None:
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Anulowano")
        self.status_label.setText("Anulowano bez tworzenia częściowego wyniku.")

    def _set_running(self, running: bool) -> None:
        if not running:
            self._task = None
        self.cancel_button.setEnabled(running)
        for widget in (
            self.channel_spin,
            self.can_id_edit,
            self.id_format_combo,
            self.frame_kind_combo,
            self.start_bit_spin,
            self.length_spin,
            self.byte_order_combo,
            self.signed_check,
            self.scale_spin,
            self.offset_spin,
            self.maximum_points_spin,
            self.run_button,
            self.refresh_button,
            self.artifact_combo,
        ):
            widget.setEnabled(not running)

    @Slot()
    @Slot(str)
    def _load_artifacts(self, preferred_artifact_id: str = "") -> None:
        service = self._service
        record = self._session_record
        current = preferred_artifact_id or str(self.artifact_combo.currentData() or "")
        if service is None or record is None:
            self._artifacts = ()
        else:
            try:
                self._artifacts = service.list_artifacts(str(getattr(record, "id", "")))
            except Exception as exc:
                self._artifacts = ()
                self.status_label.setText(f"Nie można odczytać artefaktów plottera: {exc}")
        self.artifact_combo.blockSignals(True)
        self.artifact_combo.clear()
        selected = -1
        for index, artifact in enumerate(self._artifacts):
            key = artifact.metadata.get("message_key", {}) if isinstance(artifact.metadata, Mapping) else {}
            can_id = key.get("arbitration_id_hex", "?") if isinstance(key, Mapping) else "?"
            count = artifact.metadata.get("point_count", "?") if isinstance(artifact.metadata, Mapping) else "?"
            self.artifact_combo.addItem(
                f"{artifact.created_at_utc or 'bez daty'} — {can_id} — {count} pkt — {artifact.sha256[:10]}",
                artifact.id,
            )
            if artifact.id == current:
                selected = index
        if self._artifacts:
            self.artifact_combo.setCurrentIndex(selected if selected >= 0 else 0)
        self.artifact_combo.blockSignals(False)
        self._artifact_changed()

    @Slot()
    @Slot(int)
    def _artifact_changed(self, _index: int = -1) -> None:
        artifact_id = str(self.artifact_combo.currentData() or "")
        artifact = next((item for item in self._artifacts if item.id == artifact_id), None)
        if artifact is None:
            self._payload = None
            self.plot.set_series(())
            self.series_label.setText("Brak wczytanej serii.")
            self._refresh_cursor_summary()
            return
        service = self._service
        if service is None:
            return
        try:
            payload = service.read_series(artifact)
        except Exception as exc:
            self.status_label.setText(f"Nie można otworzyć pełnej serii: {exc}")
            return
        self._payload = payload
        points_value = payload.get("points")
        points = [item for item in points_value if isinstance(item, Mapping)] if isinstance(points_value, list) else []
        self.plot.set_series(points)
        summary = _mapping(payload.get("summary"))
        key = _mapping(payload.get("message_key"))
        bitfield = _mapping(payload.get("bitfield"))
        self.series_label.setText(
            f"CAN {key.get('arbitration_id_hex', '—')} | kanał {key.get('channel', '—')} | "
            f"Bity: start={bitfield.get('start_bit', '—')}, length={bitfield.get('length', '—')}, "
            f"{bitfield.get('byte_order', '—')} | punkty={summary.get('point_count', 0)} | "
            f"matching={summary.get('matching_frame_count', 0)} | missing field={summary.get('field_missing_count', 0)}\n"
            "Kontrakt: complete=true, sampling=none; redukcja dotyczy wyłącznie renderingu."
        )
        if points:
            self.plot.set_cursor_index("A", 0)
            self.plot.set_cursor_index("B", len(points) - 1)
        self.status_label.setText("Wczytano pełną serię. Ustaw kursory A/B klikając wykres.")
        self._refresh_cursor_summary()

    @Slot(str, object)
    def _cursor_changed(self, _name: str, _point: object) -> None:
        self._refresh_cursor_summary()

    def _refresh_cursor_summary(self) -> None:
        a = self.plot.cursor_point("A")
        b = self.plot.cursor_point("B")
        lines = [self._cursor_text("A", a), self._cursor_text("B", b)]
        if a is not None and b is not None:
            delta = cursor_delta(a, b)
            lines.append(
                f"Δt(B-A) = {delta.delta_time_ns} ns = {delta.delta_time_s:.9g} s | "
                f"Δvalue(B-A) = {delta.delta_value:.9g}"
            )
        self.cursor_label.setText("\n".join(lines))
        self._refresh_cursor_buttons()

    @staticmethod
    def _cursor_text(name: str, point: Mapping[str, Any] | None) -> str:
        if point is None:
            return f"{name}: —"
        return (
            f"{name}: t={int(point['timestamp_ns'])} ns | value={float(point['value']):.9g} | "
            f"raw={point.get('raw', '—')} | source_row={int(point['source_row']) + 1}"
        )

    def _refresh_cursor_buttons(self) -> None:
        self.open_a_button.setEnabled(self.plot.cursor_point("A") is not None)
        self.open_b_button.setEnabled(self.plot.cursor_point("B") is not None)

    def _open_cursor(self, name: str) -> None:
        point = self.plot.cursor_point(name)
        if point is None:
            return
        self._navigator.navigate_to_source_row(int(point["source_row"]))

    def shutdown(self) -> None:
        self._cancel()
        self._navigator.close()


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = ["FullSignalPlotWidget", "SignalPlotterView"]
