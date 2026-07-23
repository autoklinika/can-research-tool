from __future__ import annotations

from math import ceil

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
STATUS_COLORS = {
    STATUS_NEW: QColor("#4CAF50"),
    STATUS_MISSING: QColor("#E53935"),
    STATUS_CHANGED: QColor("#F9A825"),
    "Bez zmian": QColor("#78909C"),
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
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        self.overview_label = QLabel(self)
        self.overview_label.setWordWrap(True)
        root.addWidget(self.overview_label)

        cards = QHBoxLayout()
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

        charts = QSplitter(Qt.Orientation.Horizontal, self)
        self.heatmap = PresenceHeatmap(charts)
        self.frequency_panel = FrequencyDeltaPanel(charts)
        charts.addWidget(self.heatmap)
        charts.addWidget(self.frequency_panel)
        charts.setSizes((560, 560))
        root.addWidget(charts, 1)

        details = QSplitter(Qt.Orientation.Horizontal, self)
        table_panel = QWidget(details)
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(4)
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
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        self.table.itemSelectionChanged.connect(self._selection_changed)
        table_layout.addWidget(self.table, 1)

        pagination = QHBoxLayout()
        self.rows_label = QLabel(self)
        self.rows_label.setObjectName("comparisonVisualizationRowsLabel")
        pagination.addWidget(self.rows_label)
        pagination.addStretch(1)
        pagination.addWidget(QLabel("Wierszy na stronę:", self))
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

        details.addWidget(table_panel)
        self.inspector = ComparisonInspector(details)
        self.inspector.evidence_requested.connect(self.evidence_requested.emit)
        details.addWidget(self.inspector)
        details.setSizes((900, 300))
        root.addWidget(details, 2)
        self.payload_preview = PayloadDiffPreview(self)
        root.addWidget(self.payload_preview)
        self.clear()

    @property
    def data(self) -> ComparisonDashboardData:
        return self._data

    def clear(self) -> None:
        self._data = ComparisonDashboardData(self._comparison_name)
        self._ordered_rows = []
        self._visible_rows = []
        self._page_index = 0
        self.overview_label.setText(
            "Uruchom providery porównawcze. Dashboard korzysta wyłącznie z "
            "trwałych artefaktów i nie skanuje sesji ponownie w GUI."
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
        schemas = ", ".join(data.artifact_schemas) or "brak"
        self.overview_label.setText(
            f"Zestaw: {data.comparison_name}. Sesje porównywane: {compared}. "
            f"Źródła dashboardu: {schemas}. Wszystkie różnice są dostępne "
            "strona po stronie; GUI nie ucina wyniku analizy."
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
            "ranking zmian sekwencji",
            STATUS_COLORS[STATUS_CHANGED],
        )
        if data.largest_frequency_delta is None:
            self.frequency_card.set_value(
                "—",
                "brak porównywalnej częstotliwości",
            )
        else:
            delta = data.largest_frequency_delta
            self.frequency_card.set_value(
                format_percent(delta),
                data.largest_frequency_key,
                QColor("#F9A825") if delta >= 0 else QColor("#2F7ED8"),
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
                format_percent(row.frequency_delta_percent),
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
                    if color is not None:
                        item.setForeground(color)
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
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            self.inspector.clear_selection()
            self.payload_preview.clear_preview()
            return
        item = self.table.item(selected[0].row(), 0)
        if item is None:
            return
        source_index = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(source_index, int):
            return
        if not 0 <= source_index < len(self._visible_rows):
            return
        row = self._visible_rows[source_index]
        self.inspector.set_row(row)
        self.payload_preview.set_row(row)
