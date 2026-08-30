from __future__ import annotations

from collections import defaultdict

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
        self.setMinimumHeight(102)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(3)
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("comparisonKpiTitle")
        self.value_label = QLabel("—", self)
        self.value_label.setObjectName("comparisonKpiValue")
        value_font = self.value_label.font()
        value_font.setBold(True)
        value_font.setPointSize(value_font.pointSize() + 8)
        self.value_label.setFont(value_font)
        self.detail_label = QLabel("Brak danych", self)
        self.detail_label.setObjectName("comparisonKpiDetail")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)
        self.set_value("—", "Brak danych")

    def set_value(
        self,
        value: str,
        detail: str,
        color: QColor | None = None,
    ) -> None:
        accent = color or QColor("#607d8b")
        self.value_label.setText(value)
        self.detail_label.setText(detail)
        palette = self.value_label.palette()
        palette.setColor(QPalette.ColorRole.WindowText, accent)
        self.value_label.setPalette(palette)
        self.setStyleSheet(
            "QFrame#comparisonKpiCard {"
            "background: #171f28;"
            "border: 1px solid #2a3743;"
            f"border-left: 4px solid {accent.name()};"
            "border-radius: 8px;"
            "}"
            "QLabel#comparisonKpiTitle {"
            "color: #aebdcc; font-size: 11px; font-weight: 600;"
            "}"
            "QLabel#comparisonKpiDetail {"
            "color: #8396a8; font-size: 10px;"
            "}"
        )


class PresenceHeatmap(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("comparisonPresenceHeatmap")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumHeight(225)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 9)
        layout.setSpacing(7)
        title = QLabel("Heatmapa obecności wiadomości", self)
        title.setObjectName("comparisonPanelTitle")
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        self.table = QTableWidget(0, 0, self)
        self.table.setObjectName("comparisonPresenceHeatmapTable")
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.horizontalHeader().setMinimumHeight(30)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        layout.addWidget(self.table)
        self.legend = QLabel(
            "<span style='color:#55d187'>✓</span> obecne &nbsp;&nbsp; "
            "<span style='color:#ffbf47'>△</span> zmienione &nbsp;&nbsp; "
            "<span style='color:#ff6b6b'>×</span> brakujące",
            self,
        )
        self.legend.setObjectName("comparisonChartLegend")
        self.legend.setAccessibleName(
            "Legenda: znak wyboru oznacza obecne, trójkąt zmienione, "
            "krzyżyk brakujące."
        )
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
        foregrounds = {
            "present": QColor("#55d187"),
            "changed": QColor("#ffbf47"),
            "missing": QColor("#ff6b6b"),
        }
        backgrounds = {
            "present": QColor("#18382a"),
            "changed": QColor("#49391d"),
            "missing": QColor("#452124"),
        }
        symbols = {
            "present": "✓",
            "changed": "△",
            "missing": "×",
        }
        labels = {
            "present": "obecne",
            "changed": "zmienione",
            "missing": "brakujące",
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
                item = QTableWidgetItem(symbols[state])
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(foregrounds[state])
                item.setBackground(backgrounds[state])
                item.setToolTip(labels[state])
                item.setData(
                    Qt.ItemDataRole.AccessibleTextRole,
                    f"{short_key(key)}: {labels[state]}",
                )
                self.table.setItem(row_index, column, item)


class FrequencyDeltaPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("comparisonFrequencyDeltaPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumHeight(225)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 9)
        layout.setSpacing(7)
        title = QLabel("Top różnice częstotliwości", self)
        title.setObjectName("comparisonPanelTitle")
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        self.empty_label = QLabel(
            "Brak istotnych zmian częstotliwości.",
            self,
        )
        self.empty_label.setObjectName("comparisonChartEmptyState")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)
        self.table = QTableWidget(0, 3, self)
        self.table.setObjectName("comparisonFrequencyDeltaTable")
        self.table.setHorizontalHeaderLabels(("CAN ID / Klucz", "Zmiana", "Δ"))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.horizontalHeader().setMinimumHeight(30)
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
            row for row in rows if row.has_significant_frequency_change
        ]
        self.rows = sorted(
            candidates,
            key=lambda row: abs(float(row.frequency_delta_percent or 0.0)),
            reverse=True,
        )[:MAX_FREQUENCY_BARS]
        self.empty_label.setVisible(not self.rows)
        self.table.setVisible(bool(self.rows))
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
            color = "#ffbf47" if delta >= 0 else "#5da9ff"
            bar.setStyleSheet(
                "QProgressBar {"
                "border: 1px solid #31414f;"
                "border-radius: 3px;"
                "background: #10171e;"
                "}"
                f"QProgressBar::chunk {{ background: {color}; }}"
            )
            self.table.setCellWidget(index, 1, bar)
            value_item = QTableWidgetItem(format_percent(delta))
            value_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(index, 2, value_item)
