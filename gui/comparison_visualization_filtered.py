from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidgetItem,
)

from .comparison_visualization_dashboard import (
    STATUS_BACKGROUNDS,
    STATUS_COLORS,
    ComparisonVisualizationWidget,
    _format_delta,
)
from .comparison_visualization_model import (
    STATUS_CHANGED,
    STATUS_MISSING,
    STATUS_NEW,
    STATUS_ORDER,
    STATUS_UNCHANGED,
    ComparisonVisualRow,
    format_hz,
    format_integer,
    optional_hex_int,
    payload_summary,
)


class FilteredComparisonVisualizationWidget(ComparisonVisualizationWidget):
    """Comparison dashboard with full-result search, filtering and sorting."""

    def __init__(self, comparison_name: str, parent=None) -> None:
        self._sort_column: int | None = None
        self._sort_order = Qt.SortOrder.AscendingOrder
        super().__init__(comparison_name, parent)
        self._install_filter_toolbar()
        self._install_global_sorting()
        self.table.setHorizontalHeaderLabels(
            (
                "Sesja",
                "CAN ID / Klucz",
                "Status",
                "Ramki bazowe",
                "Ramki porównywane",
                "Częstotliwość",
                "Δ [%]",
                "Payload",
                "Sekwencje",
                "Dowody",
            )
        )
        try:
            self.inspector.evidence_requested.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.inspector.evidence_requested.connect(self._request_selected_evidence)
        self._append_filter_style()

    @property
    def filtered_row_count(self) -> int:
        return len(self._ordered_rows)

    def _install_filter_toolbar(self) -> None:
        panel = self.table.parentWidget()
        layout = None if panel is None else panel.layout()
        if layout is None:
            raise RuntimeError("comparison table panel has no layout")

        toolbar = QHBoxLayout()
        toolbar.setSpacing(7)
        search_label = QLabel("Szukaj:", panel)
        search_label.setObjectName("comparisonTableFilterLabel")
        toolbar.addWidget(search_label)

        self.search_edit = QLineEdit(panel)
        self.search_edit.setObjectName("comparisonTableSearch")
        self.search_edit.setPlaceholderText(
            "CAN ID, klucz wiadomości lub nazwa sesji"
        )
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._filters_changed)
        toolbar.addWidget(self.search_edit, 1)

        status_label = QLabel("Status:", panel)
        status_label.setObjectName("comparisonTableFilterLabel")
        toolbar.addWidget(status_label)

        self.status_filter = QComboBox(panel)
        self.status_filter.setObjectName("comparisonStatusFilter")
        self.status_filter.addItem("Wszystkie", "")
        self.status_filter.addItem(STATUS_NEW, STATUS_NEW)
        self.status_filter.addItem(STATUS_MISSING, STATUS_MISSING)
        self.status_filter.addItem(STATUS_CHANGED, STATUS_CHANGED)
        self.status_filter.addItem(STATUS_UNCHANGED, STATUS_UNCHANGED)
        self.status_filter.currentIndexChanged.connect(self._filters_changed)
        toolbar.addWidget(self.status_filter)

        self.clear_filters_button = QPushButton("Wyczyść", panel)
        self.clear_filters_button.setObjectName("comparisonClearFilters")
        self.clear_filters_button.clicked.connect(self._clear_filters)
        toolbar.addWidget(self.clear_filters_button)
        layout.insertLayout(1, toolbar)

    def _install_global_sorting(self) -> None:
        self.table.setSortingEnabled(False)
        header = self.table.horizontalHeader()
        header.setSortIndicatorShown(False)
        header.sectionClicked.connect(self._sort_by_column)

    def _append_filter_style(self) -> None:
        self.setStyleSheet(
            self.styleSheet()
            + """
            QLineEdit#comparisonTableSearch {
                min-height: 28px;
                padding: 0 9px;
                border: 1px solid #344654;
                border-radius: 4px;
                background: #121920;
                color: #dce6ef;
                selection-background-color: #235b87;
            }
            QLabel#comparisonTableFilterLabel {
                color: #94a7b8;
            }
            """
        )

    def _populate_table(self) -> None:
        self._apply_filters_and_sort()

    def _filters_changed(self, *_args) -> None:
        self._page_index = 0
        self._apply_filters_and_sort()

    def _clear_filters(self) -> None:
        self.search_edit.clear()
        self.status_filter.setCurrentIndex(0)
        self._page_index = 0
        self._apply_filters_and_sort()

    def _apply_filters_and_sort(self) -> None:
        query = self.search_edit.text().strip().casefold()
        status = str(self.status_filter.currentData() or "")
        rows = [
            row
            for row in self._data.rows
            if (not status or row.status == status)
            and (not query or query in _search_text(row))
        ]
        if self._sort_column is None:
            rows.sort(
                key=lambda row: (
                    STATUS_ORDER.get(row.status, 99),
                    -row.magnitude,
                    row.session_name.casefold(),
                    row.message_key,
                )
            )
        else:
            rows.sort(
                key=lambda row: _column_sort_key(row, self._sort_column or 0),
                reverse=self._sort_order == Qt.SortOrder.DescendingOrder,
            )
        self._ordered_rows = rows
        self._refresh_page()

    def _sort_by_column(self, column: int) -> None:
        if self._sort_column == column:
            self._sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._sort_column = column
            self._sort_order = Qt.SortOrder.AscendingOrder
        header = self.table.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSortIndicator(column, self._sort_order)
        self._page_index = 0
        self._apply_filters_and_sort()

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
        self._update_pagination(start, end)
        if self._visible_rows:
            self.table.selectRow(0)
        else:
            self.inspector.clear_selection()
            self.payload_preview.clear_preview()

    def _update_pagination(self, start: int = 0, end: int = 0) -> None:
        super()._update_pagination(start, end)
        all_count = len(self._data.rows)
        if len(self._ordered_rows) != all_count:
            self.rows_label.setText(
                f"{self.rows_label.text()} · wszystkich: {all_count}"
            )

    def _selection_changed(self) -> None:
        super()._selection_changed()
        row = self._selected_row()
        if row is None:
            return
        if row.status == STATUS_MISSING:
            self.inspector.evidence_button.setText(
                f"Otwórz dowody w bazie ({row.evidence_count})"
            )

    def _request_selected_evidence(self, *_args) -> None:
        row = self._selected_row()
        if row is None or row.evidence_count <= 0:
            return
        self.evidence_requested.emit(
            self._evidence_session_id(row),
            row.message_key,
        )

    def _evidence_session_id(self, row: ComparisonVisualRow) -> str:
        if row.status != STATUS_MISSING:
            return row.session_id
        baseline = next(
            (
                str(session.get("id") or "")
                for session in self._data.sessions
                if session.get("role") == "base"
            ),
            "",
        )
        return baseline or row.session_id


def _search_text(row: ComparisonVisualRow) -> str:
    return " ".join(
        (
            row.session_name,
            row.display_key,
            row.message_key,
            row.arbitration_id_hex,
            row.status,
            row.frame_kind,
        )
    ).casefold()


def _column_sort_key(row: ComparisonVisualRow, column: int):
    if column == 0:
        return row.session_name.casefold()
    if column == 1:
        arbitration_id = optional_hex_int(row.arbitration_id_hex)
        return (
            row.channel,
            row.is_extended_id,
            -1 if arbitration_id is None else arbitration_id,
            row.frame_kind,
            row.message_key,
        )
    if column == 2:
        return STATUS_ORDER.get(row.status, 99)
    if column == 3:
        return _number(row.baseline_frame_count)
    if column == 4:
        return _number(row.current_frame_count)
    if column == 5:
        return _number(row.current_frequency_hz)
    if column == 6:
        return _number(row.frequency_delta_percent)
    if column == 7:
        return row.payload_change_count
    if column == 8:
        return row.sequence_change_count
    if column == 9:
        return row.evidence_count
    return row.message_key


def _number(value: int | float | None) -> float:
    return float("-inf") if value is None else float(value)


__all__ = ["FilteredComparisonVisualizationWidget"]
