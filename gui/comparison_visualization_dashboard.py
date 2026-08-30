from __future__ import annotations

from math import ceil

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .comparison_visualization_charts import (
    ComparisonKpiCard,
    FrequencyDeltaPanel,
    PresenceHeatmap,
)
from .comparison_visualization_details import (
    ComparisonInspector,
    PayloadDiffPreview,
)
from .comparison_visualization_model import (
    SCHEMA_PAYLOAD,
    SCHEMA_SEQUENCE,
    SCHEMA_STATISTICS,
    STATUS_CHANGED,
    STATUS_MISSING,
    STATUS_NEW,
    STATUS_ORDER,
    ComparisonDashboardData,
    ComparisonVisualRow,
    build_dashboard_data,
    format_hz,
    format_integer,
    format_percent,
    payload_summary,
)

DEFAULT_PAGE_SIZE = 100
PAGE_SIZE_OPTIONS = (50, 100, 250, 500)
MIN_VISIBLE_FREQUENCY_DELTA = 0.05
STATUS_COLORS = {
    STATUS_NEW: QColor("#55d187"),
    STATUS_MISSING: QColor("#ff6b6b"),
    STATUS_CHANGED: QColor("#ffbf47"),
    "Bez zmian": QColor("#91a4b7"),
}
STATUS_BACKGROUNDS = {
    STATUS_NEW: QColor("#173a2a"),
    STATUS_MISSING: QColor("#432124"),
    STATUS_CHANGED: QColor("#44351b"),
    "Bez zmian": QColor("#25303a"),
}
_SOURCE_NAMES = {
    SCHEMA_STATISTICS: "statystyki CAN ID",
    SCHEMA_PAYLOAD: "różnice payloadów",
    SCHEMA_SEQUENCE: "sekwencje wiadomości",
}


class ComparisonVisualizationWidget(QWidget):
    evidence_requested = Signal(str, str)

    def __init__(
        self,
        comparison_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("comparisonVisualizationDashboard")
        self._comparison_name = comparison_name
        self._data = ComparisonDashboardData(comparison_name)
        self._ordered_rows: list[ComparisonVisualRow] = []
        self._visible_rows: list[ComparisonVisualRow] = []
        self._page_index = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        self.overview_label = QLabel(self)
        self.overview_label.setObjectName("comparisonOverviewHeader")
        self.overview_label.setWordWrap(True)
        root.addWidget(self.overview_label)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.new_card = ComparisonKpiCard("Nowe ID", self)
        self.missing_card = ComparisonKpiCard("Brakujące ID", self)
        self.payload_card = ComparisonKpiCard("Zmienione payloady", self)
        self.sequence_card = ComparisonKpiCard("Zmienione sekwencje", self)
        self.frequency_card = ComparisonKpiCard(
            "Największa zmiana częstotliwości",
            self,
        )
        for card in (
            self.new_card,
            self.missing_card,
            self.payload_card,
            self.sequence_card,
            self.frequency_card,
        ):
            cards.addWidget(card)
        root.addLayout(cards)

        self.charts_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.charts_splitter.setObjectName("comparisonChartsSplitter")
        self.charts_splitter.setChildrenCollapsible(False)
        self.heatmap = PresenceHeatmap(self.charts_splitter)
        self.frequency_panel = FrequencyDeltaPanel(self.charts_splitter)
        self.charts_splitter.addWidget(self.heatmap)
        self.charts_splitter.addWidget(self.frequency_panel)
        self.charts_splitter.setStretchFactor(0, 1)
        self.charts_splitter.setStretchFactor(1, 1)
        self.charts_splitter.setSizes((620, 620))
        self.charts_splitter.setMinimumHeight(235)
        root.addWidget(self.charts_splitter, 1)

        self.details_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.details_splitter.setObjectName("comparisonDetailsSplitter")
        self.details_splitter.setChildrenCollapsible(False)
        table_panel = QFrame(self.details_splitter)
        table_panel.setObjectName("comparisonDiffTablePanel")
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(10, 10, 10, 8)
        table_layout.setSpacing(8)
        table_title = QLabel("Tabela różnic", table_panel)
        table_title.setObjectName("comparisonSectionTitle")
        table_layout.addWidget(table_title)

        self.table = QTableWidget(0, 10, table_panel)
        self.table.setObjectName("comparisonVisualizationDiffTable")
        self.table.setHorizontalHeaderLabels(
            (
                "Sesja",
                "CAN ID / Klucz",
                "Status",
                "Ramki bazowa",
                "Ramki porównywana",
                "Częstotliwość",
                "Δ [%]",
                "Payload",
                "Sekwencje",
                "Dowody",
            )
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)
        self.table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.table.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.horizontalHeader().setMinimumHeight(32)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemDoubleClicked.connect(self._request_selected_evidence)
        table_layout.addWidget(self.table, 1)

        pagination = QHBoxLayout()
        pagination.setSpacing(6)
        self.rows_label = QLabel(self)
        self.rows_label.setObjectName("comparisonVisualizationRowsLabel")
        pagination.addWidget(self.rows_label)
        pagination.addStretch(1)
        page_size_label = QLabel("Wierszy na stronę:", self)
        page_size_label.setObjectName("comparisonPaginationLabel")
        pagination.addWidget(page_size_label)
        self.page_size_combo = QComboBox(self)
        self.page_size_combo.setObjectName("comparisonVisualizationPageSize")
        for size in PAGE_SIZE_OPTIONS:
            self.page_size_combo.addItem(str(size), size)
        default_index = self.page_size_combo.findData(DEFAULT_PAGE_SIZE)
        self.page_size_combo.setCurrentIndex(max(0, default_index))
        self.page_size_combo.currentIndexChanged.connect(self._page_size_changed)
        pagination.addWidget(self.page_size_combo)
        self.previous_page_button = QPushButton("Poprzednia", self)
        self.previous_page_button.setObjectName(
            "comparisonVisualizationPreviousPage"
        )
        self.previous_page_button.clicked.connect(self._previous_page)
        pagination.addWidget(self.previous_page_button)
        self.page_label = QLabel(self)
        self.page_label.setObjectName("comparisonVisualizationPageLabel")
        pagination.addWidget(self.page_label)
        self.next_page_button = QPushButton("Następna", self)
        self.next_page_button.setObjectName("comparisonVisualizationNextPage")
        self.next_page_button.clicked.connect(self._next_page)
        pagination.addWidget(self.next_page_button)
        table_layout.addLayout(pagination)

        self.details_splitter.addWidget(table_panel)
        self.inspector = ComparisonInspector(self.details_splitter)
        self.inspector.evidence_requested.connect(self.evidence_requested.emit)
        self.details_splitter.addWidget(self.inspector)
        self.details_splitter.setStretchFactor(0, 1)
        self.details_splitter.setStretchFactor(1, 0)
        self.details_splitter.setSizes((980, 330))
        self.details_splitter.setMinimumHeight(300)
        root.addWidget(self.details_splitter, 2)

        self.payload_preview = PayloadDiffPreview(self)
        root.addWidget(self.payload_preview)
        self._apply_style()
        self.clear()

    @property
    def data(self) -> ComparisonDashboardData:
        return self._data

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget#comparisonVisualizationDashboard {
                background: #111820;
                color: #dce6ef;
            }
            QLabel#comparisonOverviewHeader {
                min-height: 34px;
                padding: 8px 12px;
                border: 1px solid #2a3a48;
                border-radius: 7px;
                background: #17212a;
                color: #c9d8e5;
                font-size: 12px;
            }
            QLabel#comparisonSectionTitle {
                color: #f2f7fb;
                font-size: 13px;
                font-weight: 700;
            }
            QFrame#comparisonKpiCard,
            QFrame#comparisonPresenceHeatmap,
            QFrame#comparisonFrequencyDeltaPanel,
            QFrame#comparisonInspectorPanel,
            QFrame#comparisonPayloadDiffPreview,
            QFrame#comparisonDiffTablePanel {
                background: #171f28;
                border: 1px solid #2a3743;
                border-radius: 8px;
            }
            QTableWidget {
                background: #121920;
                alternate-background-color: #151e27;
                border: 1px solid #283541;
                border-radius: 4px;
                color: #dce6ef;
                selection-background-color: #235b87;
                selection-color: white;
            }
            QHeaderView::section {
                background: #202b35;
                color: #dce6ef;
                border: 0;
                border-right: 1px solid #2d3b47;
                border-bottom: 1px solid #344552;
                padding: 6px;
                font-weight: 700;
            }
            QComboBox, QPushButton {
                min-height: 28px;
                padding: 0 9px;
                border: 1px solid #344654;
                border-radius: 4px;
                background: #1b2630;
                color: #dce6ef;
            }
            QPushButton:hover:enabled {
                background: #243543;
                border-color: #4c6578;
            }
            QPushButton:disabled {
                color: #667583;
                background: #171f26;
            }
            QLabel#comparisonVisualizationRowsLabel,
            QLabel#comparisonVisualizationPageLabel,
            QLabel#comparisonPaginationLabel {
                color: #94a7b8;
            }
            """
        )

    def clear(self) -> None:
        self._data = ComparisonDashboardData(self._comparison_name)
        self._ordered_rows = []
        self._visible_rows = []
        self._page_index = 0
        self.overview_label.setText(
            "Brak gotowych analiz. Użyj przycisku „Uruchom komplet analiz”, "
            "aby utworzyć pełny dashboard porównania."
        )
        for card in (
            self.new_card,
            self.missing_card,
            self.payload_card,
            self.sequence_card,
            self.frequency_card,
        ):
            card.set_value("—", "Brak danych")
        self.heatmap.set_data([], [])
        self.frequency_panel.set_rows([])
        self.table.setRowCount(0)
        self._update_pagination()
        self.inspector.clear_selection()
        self.payload_preview.clear_preview()

    def set_payloads(self, payloads: dict[str, dict]) -> None:
        self._data = build_dashboard_data(self._comparison_name, payloads)
        self._update_cards()
        self.heatmap.set_data(self._data.sessions, self._data.rows)
        self.frequency_panel.set_rows(self._data.rows)
        self._populate_table()

    def _update_cards(self) -> None:
        data = self._data
        compared = sum(
            1 for session in data.sessions if session.get("role") != "base"
        )
        available = set(data.artifact_schemas)
        ready = [
            label for schema, label in _SOURCE_NAMES.items() if schema in available
        ]
        missing = [
            label for schema, label in _SOURCE_NAMES.items() if schema not in available
        ]
        ready_text = ", ".join(ready) or "brak"
        missing_text = ", ".join(missing) or "brak"
        self.overview_label.setText(
            f"Zestaw: {data.comparison_name} · sesje porównywane: {compared} · "
            f"gotowe: {ready_text} · brakuje: {missing_text}. "
            "Tabela zawiera pełny wynik strona po stronie."
        )
        self.new_card.set_value(
            str(data.new_count),
            "klucze obecne poza bazą",
            STATUS_COLORS[STATUS_NEW],
        )
        self.missing_card.set_value(
            str(data.missing_count),
            "klucze brakujące względem bazy",
            STATUS_COLORS[STATUS_MISSING],
        )
        self.payload_card.set_value(
            str(data.changed_payload_count),
            "wiadomości ze zmianami payloadu",
            STATUS_COLORS[STATUS_CHANGED],
        )
        self.sequence_card.set_value(
            str(data.changed_sequence_count),
            "zmiany kolejności wiadomości",
            STATUS_COLORS[STATUS_CHANGED],
        )
        delta = data.largest_frequency_delta
        if delta is None or abs(float(delta)) < MIN_VISIBLE_FREQUENCY_DELTA:
            self.frequency_card.set_value(
                "—",
                "brak istotnej zmiany częstotliwości",
            )
        else:
            self.frequency_card.set_value(
                _format_delta(delta),
                data.largest_frequency_key,
                QColor("#ffbf47") if delta >= 0 else QColor("#5da9ff"),
            )

    def _populate_table(self) -> None:
        self._ordered_rows = sorted(
            self._data.rows,
            key=lambda row: (
                STATUS_ORDER.get(row.status, 99),
                -row.magnitude,
                row.session_name.casefold(),
                row.message_key,
            ),
        )
        self._page_index = 0
        self._refresh_page()

    def _refresh_page(self) -> None:
        page_size = self._page_size()
        page_count = self._page_count(page_size)
        if page_count == 0:
            self._page_index = 0
            start = 0
            end = 0
        else:
            self._page_index = min(self._page_index, page_count - 1)
            start = self._page_index * page_size
            end = min(start + page_size, len(self._ordered_rows))
        self._visible_rows = self._ordered_rows[start:end]
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        self.table.clearContents()
        self.table.setRowCount(len(self._visible_rows))
        for row_index, row in enumerate(self._visible_rows):
            values = (
                row.session_name,
                row.display_key,
                row.status,
                format_integer(row.baseline_frame_count),
                format_integer(row.current_frame_count),
                f"{format_hz(row.baseline_frequency_hz)} → "
                f"{format_hz(row.current_frequency_hz)}",
                _format_delta(row.frequency_delta_percent),
                payload_summary(row),
                str(row.sequence_change_count),
                str(row.evidence_count),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, row_index)
                if column in {3, 4, 6, 8, 9}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter
                    )
                if column == 2:
                    color = STATUS_COLORS.get(row.status)
                    background = STATUS_BACKGROUNDS.get(row.status)
                    if color is not None:
                        item.setForeground(color)
                    if background is not None:
                        item.setBackground(background)
                    item_font = item.font()
                    item_font.setBold(True)
                    item.setFont(item_font)
                self.table.setItem(row_index, column, item)
        self.table.blockSignals(False)
        self.table.setSortingEnabled(True)
        self._update_pagination(start, end)
        if self._visible_rows:
            self.table.selectRow(0)
        else:
            self.inspector.clear_selection()
            self.payload_preview.clear_preview()

    def _update_pagination(self, start: int = 0, end: int = 0) -> None:
        total = len(self._ordered_rows)
        page_count = self._page_count(self._page_size())
        shown_start = start + 1 if end > start else 0
        self.rows_label.setText(f"Wyświetlanie {shown_start}–{end} z {total}")
        current_page = self._page_index + 1 if page_count else 0
        self.page_label.setText(f"Strona {current_page} z {page_count}")
        self.previous_page_button.setEnabled(self._page_index > 0)
        self.next_page_button.setEnabled(
            page_count > 0 and self._page_index + 1 < page_count
        )

    def _page_size(self) -> int:
        value = self.page_size_combo.currentData()
        return value if isinstance(value, int) and value > 0 else DEFAULT_PAGE_SIZE

    def _page_count(self, page_size: int) -> int:
        if not self._ordered_rows:
            return 0
        return ceil(len(self._ordered_rows) / page_size)

    def _page_size_changed(self) -> None:
        self._page_index = 0
        self._refresh_page()

    def _previous_page(self) -> None:
        if self._page_index <= 0:
            return
        self._page_index -= 1
        self._refresh_page()

    def _next_page(self) -> None:
        if self._page_index + 1 >= self._page_count(self._page_size()):
            return
        self._page_index += 1
        self._refresh_page()

    def _selection_changed(self) -> None:
        row = self._selected_row()
        if row is None:
            self.inspector.clear_selection()
            self.payload_preview.clear_preview()
            return
        self.inspector.set_row(row)
        self.payload_preview.set_row(row)

    def _request_selected_evidence(self, *_args) -> None:
        row = self._selected_row()
        if row is not None and row.evidence_count > 0:
            self.evidence_requested.emit(row.session_id, row.message_key)

    def _selected_row(self) -> ComparisonVisualRow | None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        item = self.table.item(selected[0].row(), 0)
        if item is None:
            return None
        source_index = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(source_index, int):
            return None
        if not 0 <= source_index < len(self._visible_rows):
            return None
        return self._visible_rows[source_index]


def _format_delta(value: float | None) -> str:
    if value is None:
        return "—"
    if abs(float(value)) < MIN_VISIBLE_FREQUENCY_DELTA:
        return "0,0%"
    return format_percent(value)
