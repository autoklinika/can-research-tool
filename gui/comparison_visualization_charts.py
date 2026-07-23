from __future__ import annotations

from collections import defaultdict
from math import isfinite

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .comparison_visualization_model import (
    STATUS_CHANGED,
    STATUS_MISSING,
    STATUS_ORDER,
    ComparisonVisualRow,
    format_percent,
    short_key,
)

MAX_HEATMAP_KEYS = 24
MAX_HEATMAP_SESSIONS = 6
MAX_FREQUENCY_BARS = 12


class ComparisonKpiCard(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("comparisonKpiCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumHeight(86)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        self.title_label = QLabel(title, self)
        self.value_label = QLabel("—", self)
        value_font = self.value_label.font()
        value_font.setBold(True)
        value_font.setPointSize(value_font.pointSize() + 7)
        self.value_label.setFont(value_font)
        self.detail_label = QLabel("Brak danych", self)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)

    def set_value(
        self,
        value: str,
        detail: str,
        color: QColor | None = None,
    ) -> None:
        self.value_label.setText(value)
        self.detail_label.setText(detail)
        palette = self.value_label.palette()
        palette.setColor(
            QPalette.ColorRole.WindowText,
            color or self.palette().color(QPalette.ColorRole.WindowText),
        )
        self.value_label.setPalette(palette)


class PresenceHeatmap(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("comparisonPresenceHeatmap")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("Heatmapa obecności wiadomości", self)
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        self.table = QTableWidget(0, 0, self)
        self.table.setObjectName("comparisonPresenceHeatmapTable")
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        layout.addWidget(self.table)
        self.legend = QLabel("● obecne    ● zmienione    ● brakujące", self)
        layout.addWidget(self.legend)
        self.session_count = 0

    def set_data(
        self,
        sessions: list[dict],
        rows: list[ComparisonVisualRow],
    ) -> None:
        sessions = sessions[:MAX_HEATMAP_SESSIONS]
        self.session_count = len(sessions)
        grouped: dict[str, list[ComparisonVisualRow]] = defaultdict(list)
        for row in rows:
            grouped[row.message_key].append(row)
        keys = sorted(
            grouped,
            key=lambda key: (
                min(STATUS_ORDER.get(row.status, 99) for row in grouped[key]),
                -max(row.magnitude for row in grouped[key]),
                key,
            ),
        )[:MAX_HEATMAP_KEYS]
        self.table.clear()
        self.table.setRowCount(len(keys))
        self.table.setColumnCount(len(sessions))
        self.table.setHorizontalHeaderLabels(
            [str(session.get("name") or "Sesja") for session in sessions]
        )
        self.table.setVerticalHeaderLabels([short_key(key) for key in keys])
        colors = {
            "present": QColor("#43A047"),
            "changed": QColor("#F9A825"),
            "missing": QColor("#E53935"),
        }
        for row_index, key in enumerate(keys):
            key_rows = grouped[key]
            baseline_present = bool(
                (key_rows[0].baseline_frame_count or 0) > 0
            )
            for column, session in enumerate(sessions):
                session_id = str(session.get("id") or "")
                state = "present"
                if session.get("role") == "base":
                    state = "present" if baseline_present else "missing"
                else:
                    current = next(
                        (
                            row
                            for row in key_rows
                            if row.session_id == session_id
                        ),
                        None,
                    )
                    if current is None or current.status == STATUS_MISSING:
                        state = "missing"
                    elif current.status == STATUS_CHANGED:
                        state = "changed"
                item = QTableWidgetItem("●")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(colors[state])
                item.setBackground(colors[state].darker(250))
                self.table.setItem(row_index, column, item)


class FrequencyDeltaPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("comparisonFrequencyDeltaPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("Top różnice częstotliwości", self)
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(("CAN ID / Klucz", "Zmiana", "Δ"))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        layout.addWidget(self.table)
        self.rows: list[ComparisonVisualRow] = []

    def set_rows(self, rows: list[ComparisonVisualRow]) -> None:
        candidates = [
            row
            for row in rows
            if row.frequency_delta_percent is not None
            and isfinite(float(row.frequency_delta_percent))
        ]
        self.rows = sorted(
            candidates,
            key=lambda row: abs(float(row.frequency_delta_percent or 0.0)),
            reverse=True,
        )[:MAX_FREQUENCY_BARS]
        maximum = max(
            (abs(float(row.frequency_delta_percent or 0.0)) for row in self.rows),
            default=1.0,
        )
        self.table.setRowCount(len(self.rows))
        for index, row in enumerate(self.rows):
            self.table.setItem(index, 0, QTableWidgetItem(row.display_key))
            delta = float(row.frequency_delta_percent or 0.0)
            bar = QProgressBar(self.table)
            bar.setRange(0, 1000)
            bar.setValue(int(abs(delta) / maximum * 1000))
            bar.setTextVisible(False)
            color = "#F9A825" if delta >= 0 else "#2F7ED8"
            bar.setStyleSheet(
                f"QProgressBar::chunk {{ background: {color}; }}"
            )
            self.table.setCellWidget(index, 1, bar)
            value_item = QTableWidgetItem(format_percent(delta))
            value_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(index, 2, value_item)
