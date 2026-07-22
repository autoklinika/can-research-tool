from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .session_analysis_view import AnalysisEnabledSessionViewWidget


@dataclass(frozen=True, slots=True)
class SessionMessageStatistics:
    channel: int
    arbitration_id: int
    arbitration_id_hex: str
    is_extended_id: bool
    frame_kind: str
    frame_count: int
    payload_bytes: int
    min_dlc: int | None
    max_dlc: int | None
    mean_interval_ns: float | None
    frequency_hz: float | None
    stddev_ns: float | None
    min_interval_ns: int | None
    max_interval_ns: int | None
    zero_interval_count: int
    negative_interval_count: int
    first_source_row: int | None
    last_source_row: int | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SessionMessageStatistics":
        timing = payload.get("timing") if isinstance(payload.get("timing"), dict) else {}
        arbitration_id = _required_int(payload, "arbitration_id")
        is_extended = bool(payload.get("is_extended_id", False))
        width = 8 if is_extended else 3
        identifier_text = str(payload.get("arbitration_id_hex") or "").strip().upper()
        if not identifier_text:
            identifier_text = f"{arbitration_id:0{width}X}"
        return cls(
            channel=_required_int(payload, "channel"),
            arbitration_id=arbitration_id,
            arbitration_id_hex=identifier_text,
            is_extended_id=is_extended,
            frame_kind=str(payload.get("frame_kind") or "data").strip().lower(),
            frame_count=_required_int(payload, "frame_count"),
            payload_bytes=_required_int(payload, "payload_bytes"),
            min_dlc=_optional_int(payload.get("min_dlc")),
            max_dlc=_optional_int(payload.get("max_dlc")),
            mean_interval_ns=_optional_float(timing.get("mean_positive_interval_ns")),
            frequency_hz=_optional_float(timing.get("mean_positive_frequency_hz")),
            stddev_ns=_optional_float(timing.get("population_stddev_positive_interval_ns")),
            min_interval_ns=_optional_int(timing.get("min_positive_interval_ns")),
            max_interval_ns=_optional_int(timing.get("max_positive_interval_ns")),
            zero_interval_count=_optional_int(timing.get("zero_interval_count")) or 0,
            negative_interval_count=_optional_int(timing.get("negative_interval_count")) or 0,
            first_source_row=_optional_int(payload.get("first_source_row")),
            last_source_row=_optional_int(payload.get("last_source_row")),
        )


class SessionStatisticsTableModel(QAbstractTableModel):
    HEADERS = (
        "Kanał",
        "CAN ID",
        "Format",
        "Typ",
        "Ramki",
        "Udział [%]",
        "Payload [B]",
        "DLC min–max",
        "Śr. okres [ms]",
        "Częstotliwość [Hz]",
        "Jitter σ [ms]",
        "Okres min–max [ms]",
        "Δt zero / ujemne",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._all_rows: tuple[SessionMessageStatistics, ...] = ()
        self._rows: list[SessionMessageStatistics] = []
        self._total_frames = 0
        self._filter_text = ""
        self._channel_filter: int | None = None
        self._sort_column = 4
        self._sort_order = Qt.SortOrder.DescendingOrder

    @property
    def total_rows(self) -> int:
        return len(self._all_rows)

    @property
    def visible_rows(self) -> int:
        return len(self._rows)

    @property
    def channels(self) -> tuple[int, ...]:
        return tuple(sorted({row.channel for row in self._all_rows}))

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return section + 1

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_value(row, column)
        if role == Qt.ItemDataRole.UserRole:
            return self._sort_value(row, column)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if column in {0, 2, 3, 7, 12}:
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(row)
        return None

    def set_payload(self, payload: object) -> None:
        rows: list[SessionMessageStatistics] = []
        total_frames = 0
        if isinstance(payload, dict) and payload.get("schema") == "crt.session_statistics":
            totals = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
            total_frames = _optional_int(totals.get("frame_count")) or 0
            messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
            for item in messages:
                if not isinstance(item, dict):
                    continue
                try:
                    rows.append(SessionMessageStatistics.from_payload(item))
                except (KeyError, TypeError, ValueError):
                    continue
        self.beginResetModel()
        self._all_rows = tuple(rows)
        self._total_frames = total_frames
        self._filter_text = ""
        self._channel_filter = None
        self._rows = list(self._all_rows)
        self._sort_in_place()
        self.endResetModel()

    def clear(self) -> None:
        self.set_payload(None)

    def set_filter_text(self, value: str) -> None:
        normalized = value.strip().upper().replace("0X", "").replace(" ", "")
        if normalized == self._filter_text:
            return
        self._filter_text = normalized
        self._apply_filters()

    def set_channel_filter(self, channel: int | None) -> None:
        if channel == self._channel_filter:
            return
        self._channel_filter = channel
        self._apply_filters()

    def row_at(self, row: int) -> SessionMessageStatistics | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if not 0 <= column < len(self.HEADERS):
            return
        self.layoutAboutToBeChanged.emit()
        self._sort_column = column
        self._sort_order = order
        self._sort_in_place()
        self.layoutChanged.emit()

    def _apply_filters(self) -> None:
        self.beginResetModel()
        rows = []
        for row in self._all_rows:
            if self._channel_filter is not None and row.channel != self._channel_filter:
                continue
            if self._filter_text:
                searchable = (
                    row.arbitration_id_hex,
                    str(row.arbitration_id),
                    row.frame_kind.upper(),
                    "EXT" if row.is_extended_id else "STD",
                )
                if not any(self._filter_text in value.replace(" ", "") for value in searchable):
                    continue
            rows.append(row)
        self._rows = rows
        self._sort_in_place()
        self.endResetModel()

    def _sort_in_place(self) -> None:
        available: list[SessionMessageStatistics] = []
        missing: list[SessionMessageStatistics] = []
        for row in self._rows:
            if self._sort_value(row, self._sort_column) is None:
                missing.append(row)
            else:
                available.append(row)
        available.sort(
            key=lambda row: self._sort_value(row, self._sort_column),
            reverse=self._sort_order == Qt.SortOrder.DescendingOrder,
        )
        self._rows = available + missing

    def _display_value(self, row: SessionMessageStatistics, column: int) -> str:
        share = (row.frame_count * 100.0 / self._total_frames) if self._total_frames else 0.0
        values = (
            str(row.channel),
            f"0x{row.arbitration_id_hex}",
            "EXT" if row.is_extended_id else "STD",
            row.frame_kind.upper(),
            _integer_text(row.frame_count),
            f"{share:.3f}",
            _integer_text(row.payload_bytes),
            _range_text(row.min_dlc, row.max_dlc, decimals=0),
            _milliseconds_text(row.mean_interval_ns),
            _float_text(row.frequency_hz, 3),
            _milliseconds_text(row.stddev_ns),
            _range_text(_to_milliseconds(row.min_interval_ns), _to_milliseconds(row.max_interval_ns)),
            f"{_integer_text(row.zero_interval_count)} / {_integer_text(row.negative_interval_count)}",
        )
        return values[column]

    def _sort_value(self, row: SessionMessageStatistics, column: int) -> object:
        share = (row.frame_count * 100.0 / self._total_frames) if self._total_frames else 0.0
        values: tuple[object, ...] = (
            row.channel,
            row.arbitration_id,
            1 if row.is_extended_id else 0,
            row.frame_kind,
            row.frame_count,
            share,
            row.payload_bytes,
            row.min_dlc,
            row.mean_interval_ns,
            row.frequency_hz,
            row.stddev_ns,
            row.min_interval_ns,
            row.zero_interval_count + row.negative_interval_count,
        )
        return values[column]

    @staticmethod
    def _tooltip(row: SessionMessageStatistics) -> str:
        return "\n".join(
            (
                f"CAN ID: 0x{row.arbitration_id_hex}",
                f"Kanał: {row.channel}",
                f"Typ: {row.frame_kind.upper()} / {'EXT' if row.is_extended_id else 'STD'}",
                f"Zakres source_row: {row.first_source_row if row.first_source_row is not None else '—'}"
                f"–{row.last_source_row if row.last_source_row is not None else '—'}",
            )
        )


class SessionStatisticsTableSessionViewWidget(AnalysisEnabledSessionViewWidget):
    """Analysis workspace with a structured table rendered from a stored artifact."""

    def __init__(self, *args, **kwargs) -> None:
        self.statistics_model: SessionStatisticsTableModel | None = None
        self.statistics_table: QTableView | None = None
        self.statistics_filter: QLineEdit | None = None
        self.statistics_channel: QComboBox | None = None
        self.statistics_status: QLabel | None = None
        self.artifact_detail_tabs: QTabWidget | None = None
        self.statistics_tab_index = -1
        super().__init__(*args, **kwargs)
        self._install_statistics_table()
        self._show_artifact_details(self.artifact_table.currentRow())

    def _install_statistics_table(self) -> None:
        splitter = self.artifact_details.parentWidget()
        if not isinstance(splitter, QSplitter):
            raise RuntimeError("artifact detail splitter was not found")
        detail_index = splitter.indexOf(self.artifact_details)
        if detail_index < 0:
            raise RuntimeError("artifact detail editor is not owned by the splitter")

        tabs = QTabWidget()
        tabs.setObjectName("sessionArtifactDetailTabs")
        tabs.setDocumentMode(True)
        summary = splitter.replaceWidget(detail_index, tabs)
        if summary is None:
            raise RuntimeError("artifact summary widget could not be replaced")
        tabs.addTab(summary, "Podsumowanie")

        page = QWidget(tabs)
        page.setObjectName("sessionStatisticsTablePage")
        root = QVBoxLayout(page)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("CAN ID / typ:"))
        filter_edit = QLineEdit(page)
        filter_edit.setObjectName("sessionStatisticsIdFilter")
        filter_edit.setPlaceholderText("np. 18DAF900, 100, DATA, EXT")
        filter_edit.setClearButtonEnabled(True)
        filter_edit.setMinimumWidth(220)
        filters.addWidget(filter_edit)

        filters.addWidget(QLabel("Kanał:"))
        channel_combo = QComboBox(page)
        channel_combo.setObjectName("sessionStatisticsChannelFilter")
        channel_combo.addItem("Wszystkie", None)
        filters.addWidget(channel_combo)

        status = QLabel(page)
        status.setObjectName("sessionStatisticsTableStatus")
        status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        filters.addWidget(status, 1)
        root.addLayout(filters)

        model = SessionStatisticsTableModel(page)
        table = QTableView(page)
        table.setObjectName("sessionStatisticsTable")
        table.setModel(model)
        table.setSortingEnabled(True)
        table.sortByColumn(4, Qt.SortOrder.DescendingOrder)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(False)
        table.setShowGrid(True)
        table.setWordWrap(False)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(24)
        table.horizontalHeader().setStretchLastSection(True)
        widths = (58, 105, 62, 70, 90, 88, 105, 90, 115, 125, 105, 145)
        for column, width in enumerate(widths):
            table.setColumnWidth(column, width)
        root.addWidget(table, 1)

        self.statistics_model = model
        self.statistics_table = table
        self.statistics_filter = filter_edit
        self.statistics_channel = channel_combo
        self.statistics_status = status
        self.artifact_detail_tabs = tabs
        self.statistics_tab_index = tabs.addTab(page, "Statystyki CAN ID")

        filter_edit.textChanged.connect(self._statistics_filter_changed)
        channel_combo.currentIndexChanged.connect(self._statistics_channel_changed)
        self._update_statistics_status()

    def _load_artifacts(self, *, preferred_artifact_id: str = "") -> None:
        super()._load_artifacts(preferred_artifact_id=preferred_artifact_id)
        if self.statistics_model is not None and not self._analysis_artifacts:
            self._clear_statistics("Brak artefaktu statystyk dla tej sesji.")

    def _show_artifact_details(self, row: int) -> None:
        super()._show_artifact_details(row)
        model = self.statistics_model
        service = self._analysis_service
        if model is None or service is None:
            return
        if not 0 <= row < len(self._analysis_artifacts):
            self._clear_statistics("Wybierz artefakt statystyk sesji.")
            return
        artifact = self._analysis_artifacts[row]
        try:
            payload = service.artifacts.read_json(artifact)
        except Exception as exc:
            self._clear_statistics(f"Nie można odczytać statystyk: {exc}")
            return
        if not isinstance(payload, dict) or payload.get("schema") != "crt.session_statistics":
            self._clear_statistics("Wybrany artefakt nie zawiera statystyk sesji.")
            return

        model.set_payload(payload)
        self._populate_channels(model.channels)
        if self.statistics_filter is not None:
            self.statistics_filter.clear()
        self._update_statistics_status()
        if self.artifact_detail_tabs is not None:
            self.artifact_detail_tabs.setTabEnabled(self.statistics_tab_index, model.total_rows > 0)

    @Slot(str)
    def _statistics_filter_changed(self, value: str) -> None:
        model = self.statistics_model
        if model is None:
            return
        model.set_filter_text(value)
        self._update_statistics_status()

    @Slot(int)
    def _statistics_channel_changed(self, _index: int) -> None:
        model = self.statistics_model
        combo = self.statistics_channel
        if model is None or combo is None:
            return
        value = combo.currentData()
        model.set_channel_filter(None if value is None else int(value))
        self._update_statistics_status()

    def _populate_channels(self, channels: tuple[int, ...]) -> None:
        combo = self.statistics_channel
        if combo is None:
            return
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Wszystkie", None)
        for channel in channels:
            combo.addItem(str(channel), channel)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _clear_statistics(self, message: str) -> None:
        if self.statistics_model is not None:
            self.statistics_model.clear()
        self._populate_channels(())
        if self.statistics_filter is not None:
            self.statistics_filter.clear()
        if self.statistics_status is not None:
            self.statistics_status.setText(message)
        if self.artifact_detail_tabs is not None:
            self.artifact_detail_tabs.setTabEnabled(self.statistics_tab_index, False)

    def _update_statistics_status(self) -> None:
        model = self.statistics_model
        label = self.statistics_status
        if model is None or label is None:
            return
        label.setText(
            f"Widoczne klucze wiadomości: {model.visible_rows:,} z {model.total_rows:,}".replace(
                ",", " "
            )
        )


def _required_int(payload: dict[str, Any], key: str) -> int:
    if key not in payload:
        raise KeyError(key)
    value = payload[key]
    if isinstance(value, bool):
        raise TypeError(key)
    return int(value)


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
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


def _to_milliseconds(value_ns: int | float | None) -> float | None:
    return None if value_ns is None else float(value_ns) / 1_000_000.0


def _milliseconds_text(value_ns: int | float | None) -> str:
    value_ms = _to_milliseconds(value_ns)
    return _float_text(value_ms, 3)


def _range_text(
    minimum: int | float | None,
    maximum: int | float | None,
    *,
    decimals: int = 3,
) -> str:
    if minimum is None and maximum is None:
        return "—"
    if decimals == 0:
        left = "—" if minimum is None else str(int(minimum))
        right = "—" if maximum is None else str(int(maximum))
    else:
        left = _float_text(None if minimum is None else float(minimum), decimals)
        right = _float_text(None if maximum is None else float(maximum), decimals)
    return f"{left}–{right}"


__all__ = [
    "SessionMessageStatistics",
    "SessionStatisticsTableModel",
    "SessionStatisticsTableSessionViewWidget",
]
