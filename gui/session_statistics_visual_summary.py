from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .session_statistics_table_view import (
    SessionMessageStatistics,
    SessionStatisticsTableSessionViewWidget,
)


class ShareBarDelegate(QStyledItemDelegate):
    """Draw a subtle, theme-derived share bar behind the numeric value."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        display_text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        try:
            share = float(index.data(Qt.ItemDataRole.UserRole) or 0.0)
        except (TypeError, ValueError):
            share = 0.0
        share = min(100.0, max(0.0, share))

        base_option = QStyleOptionViewItem(option)
        self.initStyleOption(base_option, index)
        base_option.text = ""
        style = option.widget.style() if option.widget is not None else QApplication.style()
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem,
            base_option,
            painter,
            option.widget,
        )

        bar_rect = option.rect.adjusted(4, 5, -4, -5)
        bar_rect.setWidth(round(bar_rect.width() * share / 100.0))
        if bar_rect.width() > 0:
            bar_color = option.palette.highlight().color()
            selected = bool(option.state & QStyle.StateFlag.State_Selected)
            bar_color.setAlpha(105 if selected else 62)
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bar_color)
            painter.drawRoundedRect(bar_rect, 3, 3)
            painter.restore()

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        text_color = (
            option.palette.highlightedText().color()
            if selected
            else option.palette.text().color()
        )
        painter.save()
        painter.setPen(text_color)
        painter.drawText(
            option.rect.adjusted(5, 0, -5, 0),
            Qt.AlignmentFlag.AlignCenter,
            display_text,
        )
        painter.restore()


class StatisticsKpiCard(QFrame):
    def __init__(self, key: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self.setObjectName("sessionStatisticsKpiCard")
        self.setProperty("metricKey", key)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setMinimumHeight(72)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(1)

        title_label = QLabel(title, self)
        title_label.setObjectName("sessionStatisticsKpiTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        self.value_label = QLabel("—", self)
        self.value_label.setObjectName("sessionStatisticsKpiValue")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_font = self.value_label.font()
        value_font.setPointSize(max(value_font.pointSize() + 4, 13))
        value_font.setBold(True)
        self.value_label.setFont(value_font)
        layout.addWidget(self.value_label)

        self.hint_label = QLabel("", self)
        self.hint_label.setObjectName("sessionStatisticsKpiHint")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint_label)

    def set_metric(self, value: str, hint: str = "") -> None:
        self.value_label.setText(value)
        self.hint_label.setText(hint)
        self.hint_label.setVisible(bool(hint))


class VisualSessionStatisticsViewWidget(SessionStatisticsTableSessionViewWidget):
    """Stage 6 visual layer rendered only from the persisted statistics artifact."""

    def __init__(self, *args, **kwargs) -> None:
        self.statistics_kpi_cards: dict[str, StatisticsKpiCard] = {}
        self.statistics_top_table: QTableWidget | None = None
        self.statistics_share_delegate: ShareBarDelegate | None = None
        self.statistics_visual_page: QWidget | None = None
        self._visual_summary_ready = False
        super().__init__(*args, **kwargs)
        self._install_visual_summary()
        self._visual_summary_ready = True
        self._show_artifact_details(self.artifact_table.currentRow())

    def _install_visual_summary(self) -> None:
        tabs = self.artifact_detail_tabs
        table = self.statistics_table
        if tabs is None or table is None:
            raise RuntimeError("statistics artifact workspace is not available")

        old_summary_index = tabs.indexOf(self.artifact_details)
        if old_summary_index < 0:
            raise RuntimeError("technical artifact summary tab was not found")
        tabs.removeTab(old_summary_index)

        page = QWidget(tabs)
        page.setObjectName("sessionStatisticsVisualSummaryPage")
        root = QVBoxLayout(page)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(7)

        kpi_grid = QGridLayout()
        kpi_grid.setContentsMargins(0, 0, 0, 0)
        kpi_grid.setHorizontalSpacing(6)
        kpi_grid.setVerticalSpacing(6)
        definitions = (
            ("frames", "Ramki"),
            ("ids", "CAN ID"),
            ("duration", "Czas sesji"),
            ("frequency", "Śr. częstotliwość"),
            ("anomalies", "Anomalie czasu"),
        )
        positions = ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1))
        for (key, title), (row, column) in zip(definitions, positions, strict=True):
            card = StatisticsKpiCard(key, title, page)
            self.statistics_kpi_cards[key] = card
            kpi_grid.addWidget(card, row, column)
        kpi_grid.setColumnStretch(0, 1)
        kpi_grid.setColumnStretch(1, 1)
        kpi_grid.setColumnStretch(2, 1)
        root.addLayout(kpi_grid)

        top_title = QLabel("Najaktywniejsze CAN ID", page)
        top_title.setObjectName("sessionStatisticsTopTitle")
        top_font = top_title.font()
        top_font.setBold(True)
        top_title.setFont(top_font)
        root.addWidget(top_title)

        top_table = QTableWidget(0, 4, page)
        top_table.setObjectName("sessionStatisticsTopTable")
        top_table.setHorizontalHeaderLabels(("CAN ID / klucz", "Ramki", "Udział", "Hz"))
        top_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        top_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        top_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        top_table.setShowGrid(False)
        top_table.setWordWrap(False)
        top_table.verticalHeader().hide()
        top_table.verticalHeader().setDefaultSectionSize(25)
        header = top_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        top_table.setColumnWidth(2, 120)
        top_table.setFixedHeight(176)
        root.addWidget(top_table)
        self.statistics_top_table = top_table

        technical_title = QLabel("Szczegóły techniczne artefaktu", page)
        technical_title.setObjectName("sessionStatisticsTechnicalTitle")
        technical_font = technical_title.font()
        technical_font.setBold(True)
        technical_title.setFont(technical_font)
        root.addWidget(technical_title)
        root.addWidget(self.artifact_details, 1)

        self.statistics_visual_page = page
        tabs.insertTab(0, page, "Podsumowanie")
        tabs.setCurrentIndex(0)

        delegate = ShareBarDelegate(table)
        table.setItemDelegateForColumn(5, delegate)
        self.statistics_share_delegate = delegate

    def _show_artifact_details(self, row: int) -> None:
        super()._show_artifact_details(row)
        if not self._visual_summary_ready:
            return
        service = self._analysis_service
        if service is None or not 0 <= row < len(self._analysis_artifacts):
            self._clear_visual_summary()
            return
        artifact = self._analysis_artifacts[row]
        try:
            payload = service.artifacts.read_json(artifact)
        except Exception:
            self._clear_visual_summary()
            return
        if not isinstance(payload, dict) or payload.get("schema") != "crt.session_statistics":
            self._clear_visual_summary()
            return
        self._update_visual_summary(payload)

    def _clear_statistics(self, message: str) -> None:
        super()._clear_statistics(message)
        if self._visual_summary_ready:
            self._clear_visual_summary()

    def _update_visual_summary(self, payload: dict[str, Any]) -> None:
        totals = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
        timing = (
            payload.get("capture_timing")
            if isinstance(payload.get("capture_timing"), dict)
            else {}
        )
        frame_count = _as_int(totals.get("frame_count")) or 0
        unique_ids = _as_int(totals.get("unique_arbitration_id_count")) or 0
        duration = _as_float(totals.get("timestamp_span_s"))
        mean_frequency = _as_float(timing.get("mean_positive_frequency_hz"))
        zero_count = _as_int(timing.get("zero_interval_count")) or 0
        negative_count = _as_int(timing.get("negative_interval_count")) or 0

        self.statistics_kpi_cards["frames"].set_metric(_integer_text(frame_count))
        self.statistics_kpi_cards["ids"].set_metric(_integer_text(unique_ids))
        self.statistics_kpi_cards["duration"].set_metric(_unit_text(duration, "s", 3))
        self.statistics_kpi_cards["frequency"].set_metric(
            _unit_text(mean_frequency, "Hz", 3)
        )
        self.statistics_kpi_cards["anomalies"].set_metric(
            _integer_text(zero_count + negative_count),
            f"zero {zero_count} · ujemne {negative_count}",
        )
        self._populate_top_messages(payload, frame_count)

    def _populate_top_messages(self, payload: dict[str, Any], total_frames: int) -> None:
        table = self.statistics_top_table
        if table is None:
            return
        messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
        rows: list[SessionMessageStatistics] = []
        for item in messages:
            if not isinstance(item, dict):
                continue
            try:
                rows.append(SessionMessageStatistics.from_payload(item))
            except (KeyError, TypeError, ValueError):
                continue
        rows.sort(key=lambda item: item.frame_count, reverse=True)
        rows = rows[:5]
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            key_text = (
                f"0x{row.arbitration_id_hex} · CH{row.channel} · "
                f"{row.frame_kind.upper()} · {'EXT' if row.is_extended_id else 'STD'}"
            )
            table.setItem(row_index, 0, QTableWidgetItem(key_text))
            frames_item = QTableWidgetItem(_integer_text(row.frame_count))
            frames_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row_index, 1, frames_item)

            share = row.frame_count * 100.0 / total_frames if total_frames else 0.0
            progress = QProgressBar(table)
            progress.setObjectName("sessionStatisticsTopShareBar")
            progress.setRange(0, 10_000)
            progress.setValue(round(share * 100.0))
            progress.setFormat(f"{share:.2f}%")
            progress.setTextVisible(True)
            table.setCellWidget(row_index, 2, progress)

            frequency_item = QTableWidgetItem(_float_text(row.frequency_hz, 3))
            frequency_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row_index, 3, frequency_item)

    def _clear_visual_summary(self) -> None:
        for card in self.statistics_kpi_cards.values():
            card.set_metric("—")
        if self.statistics_top_table is not None:
            self.statistics_top_table.setRowCount(0)


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer_text(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _float_text(value: float | None, decimals: int) -> str:
    return "—" if value is None else f"{value:.{decimals}f}"


def _unit_text(value: float | None, unit: str, decimals: int) -> str:
    return "—" if value is None else f"{value:.{decimals}f} {unit}"


__all__ = [
    "ShareBarDelegate",
    "StatisticsKpiCard",
    "VisualSessionStatisticsViewWidget",
]
