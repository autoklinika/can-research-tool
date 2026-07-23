from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .comparison_visualization_model import (
    ComparisonVisualRow,
    byte_delta,
    byte_positions,
    dominant_value,
    format_hz,
    format_integer,
    format_percent,
)

MAX_PAYLOAD_BYTES = 16
STATUS_COLORS = {
    "Nowe": QColor("#4CAF50"),
    "Brakujące": QColor("#E53935"),
    "Zmienione": QColor("#F9A825"),
    "Bez zmian": QColor("#78909C"),
}


class PayloadDiffPreview(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("comparisonPayloadDiffPreview")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.title = QLabel("Podgląd różnicy payloadu", self)
        title_font = self.title.font()
        title_font.setBold(True)
        self.title.setFont(title_font)
        layout.addWidget(self.title)
        self.table = QTableWidget(3, 0, self)
        self.table.setObjectName("comparisonPayloadPreviewTable")
        self.table.setVerticalHeaderLabels(("Baza", "Porównywana", "Różnica"))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.setMaximumHeight(145)
        layout.addWidget(self.table)
        self.note = QLabel("Wybierz wiadomość w tabeli różnic.", self)
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

    def clear_preview(self) -> None:
        self.title.setText("Podgląd różnicy payloadu")
        self.table.clearContents()
        self.table.setColumnCount(0)
        self.note.setText("Wybierz wiadomość w tabeli różnic.")

    def set_row(self, row: ComparisonVisualRow) -> None:
        self.title.setText(f"Podgląd różnicy payloadu — {row.display_key}")
        baseline = byte_positions(row.baseline_payload_profile)
        current = byte_positions(row.current_payload_profile)
        total = max(len(baseline), len(current))
        count = min(total, MAX_PAYLOAD_BYTES)
        if count == 0:
            self.clear_preview()
            self.note.setText(
                "Brak profilu bajtów. Uruchom analizę różnic payloadów."
            )
            return
        self.table.setColumnCount(count)
        self.table.setHorizontalHeaderLabels([str(index) for index in range(count)])
        changed = []
        for index in range(count):
            base_value = dominant_value(baseline, index)
            current_value = dominant_value(current, index)
            different = base_value != current_value
            values = (
                base_value,
                current_value,
                "=" if not different else byte_delta(base_value, current_value),
            )
            for table_row, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if different:
                    item.setBackground(QColor("#6D4C1D"))
                    item.setForeground(QColor("#FFE0B2"))
                self.table.setItem(table_row, index, item)
            if different:
                changed.append(index)
        suffix = ""
        if total > count:
            suffix = f" Pokazano pierwsze {count} z {total} bajtów."
        if changed:
            self.note.setText(
                f"Zmienione pozycje: {', '.join(map(str, changed))}.{suffix}"
            )
        else:
            self.note.setText(f"Dominujące wartości są zgodne.{suffix}")


class ComparisonInspector(QFrame):
    evidence_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("comparisonInspectorPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(260)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        heading = QLabel("INSPEKTOR", self)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading.setFont(heading_font)
        layout.addWidget(heading)
        self.key_label = QLabel("Brak wyboru", self)
        key_font = self.key_label.font()
        key_font.setBold(True)
        key_font.setPointSize(key_font.pointSize() + 2)
        self.key_label.setFont(key_font)
        layout.addWidget(self.key_label)
        self.status_label = QLabel("—", self)
        layout.addWidget(self.status_label)
        self.details = QLabel("Wybierz wiersz w tabeli różnic.", self)
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.details)
        layout.addStretch(1)
        self.evidence_button = QPushButton("Otwórz dowody", self)
        self.evidence_button.setEnabled(False)
        self.evidence_button.clicked.connect(self._emit_evidence)
        layout.addWidget(self.evidence_button)
        self._session_id = ""
        self._message_key = ""

    def clear_selection(self) -> None:
        self.key_label.setText("Brak wyboru")
        self.status_label.setText("—")
        self.details.setText("Wybierz wiersz w tabeli różnic.")
        self.evidence_button.setEnabled(False)
        self._session_id = ""
        self._message_key = ""

    def set_row(self, row: ComparisonVisualRow) -> None:
        self._session_id = row.session_id
        self._message_key = row.message_key
        self.key_label.setText(row.display_key)
        self.status_label.setText(row.status)
        palette = self.status_label.palette()
        palette.setColor(
            QPalette.ColorRole.WindowText,
            STATUS_COLORS.get(row.status, QColor("#78909C")),
        )
        self.status_label.setPalette(palette)
        self.details.setText(
            "\n".join(
                (
                    f"Sesja: {row.session_name}",
                    f"Typ: {'EXT' if row.is_extended_id else 'STD'} / {row.frame_kind}",
                    f"Ramki bazowe: {format_integer(row.baseline_frame_count)}",
                    f"Ramki porównywane: {format_integer(row.current_frame_count)}",
                    f"Częstotliwość bazowa: {format_hz(row.baseline_frequency_hz)}",
                    f"Częstotliwość porównywana: {format_hz(row.current_frequency_hz)}",
                    f"Zmiana: {format_percent(row.frequency_delta_percent)}",
                    f"Zmiany payloadu: {row.payload_change_count}",
                    f"Zmiany sekwencji: {row.sequence_change_count}",
                    f"Dowody: {row.evidence_count}",
                )
            )
        )
        self.evidence_button.setText(f"Otwórz dowody ({row.evidence_count})")
        self.evidence_button.setEnabled(row.evidence_count > 0)

    def _emit_evidence(self) -> None:
        if self._session_id and self._message_key:
            self.evidence_requested.emit(self._session_id, self._message_key)
