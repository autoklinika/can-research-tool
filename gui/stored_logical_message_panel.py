from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QRunnable, Qt, Signal, Slot
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.logical_records import LogicalMessageRecord


FILTER_YIELD_EVERY = 2_048
FILTER_YIELD_SECONDS = 0.001
MESSAGE_ROLE = int(Qt.ItemDataRole.UserRole) + 1


_PROTOCOL_LABELS = {
    "j1939": "J1939",
    "uds": "UDS",
    "canopen": "CANopen",
    "dbc": "DBC",
    "unknown": "Proprietary",
    "proprietary": "Proprietary",
}

_PROTOCOL_COLORS = {
    "J1939": (QColor("#2d4357"), QColor("#d8ebff")),
    "UDS": (QColor("#244f58"), QColor("#d6f3f5")),
    "CANopen": (QColor("#405a2a"), QColor("#e1f4ca")),
    "DBC": (QColor("#6a4b26"), QColor("#ffe5be")),
    "Proprietary": (QColor("#51396b"), QColor("#eadcff")),
}


@dataclass(frozen=True, slots=True)
class StoredLogicalCriteria:
    protocol: str = ""
    sender: str = ""
    identity_text: str = ""
    time_from_ns: int | None = None
    time_to_ns: int | None = None
    data_offset: int | None = None
    data_pattern: bytes = b""
    only_errors: bool = False
    hide_periodic: bool = False


class StoredLogicalFilterSignals(QObject):
    completed = Signal(int, object, int)
    failed = Signal(int, str)


class StoredLogicalFilterTask(QRunnable):
    """Filter a complete stored logical-message snapshot outside the GUI thread."""

    def __init__(
        self,
        generation: int,
        messages: tuple[LogicalMessageRecord, ...],
        criteria: StoredLogicalCriteria,
        project_filter_set: object | None,
    ) -> None:
        super().__init__()
        self.generation = generation
        self.messages = messages
        self.criteria = criteria
        self.project_filter_set = project_filter_set
        self.signals = StoredLogicalFilterSignals()

    @Slot()
    def run(self) -> None:
        try:
            accepted: list[LogicalMessageRecord] = []
            seen_periodic: set[tuple[object, ...]] = set()
            for index, message in enumerate(self.messages, start=1):
                if not _passes_project_filter(message, self.project_filter_set):
                    continue
                if not _matches_criteria(message, self.criteria, seen_periodic):
                    continue
                accepted.append(message)
                if index % FILTER_YIELD_EVERY == 0:
                    sleep(FILTER_YIELD_SECONDS)
            self.signals.completed.emit(self.generation, accepted, len(self.messages))
        except Exception as exc:
            self.signals.failed.emit(self.generation, str(exc))


class StoredLogicalDisplayModel(QAbstractTableModel):
    """Eight-column operator view used by the stored logical-message workspace."""

    HEADERS = (
        "Czas [s]",
        "ID",
        "Nazwa",
        "Nadawca",
        "Protokół",
        "DLC",
        "Dane",
        "Wartości (zdekodowane)",
    )

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._messages: list[LogicalMessageRecord] = []

    @property
    def message_count(self) -> int:
        return len(self._messages)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._messages)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return section + 1

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._messages):
            return None
        message = self._messages[index.row()]
        if role == MESSAGE_ROLE:
            return message
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() in (0, 1, 5):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        values = (
            format_logical_time(message.first_timestamp_ns),
            format_message_id(message),
            message.name or "—",
            sender_text(message),
            protocol_label(message.protocol),
            len(message.payload),
            message.payload_hex or "—",
            decoded_values_text(message),
        )
        return values[index.column()]

    def replace_messages(self, messages: Iterable[LogicalMessageRecord]) -> None:
        self.beginResetModel()
        self._messages = list(messages)
        self.endResetModel()

    def clear(self) -> None:
        self.replace_messages(())

    def message_at(self, row: int) -> LogicalMessageRecord | None:
        return self._messages[row] if 0 <= row < len(self._messages) else None

    def snapshot_messages(self) -> tuple[LogicalMessageRecord, ...]:
        return tuple(self._messages)


class ProtocolBadgeDelegate(QStyledItemDelegate):
    """Paint compact rounded protocol badges matching the target engineering UI."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        if index.column() != 4:
            super().paint(painter, option, index)
            return

        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        background, foreground = _PROTOCOL_COLORS.get(
            text,
            (QColor("#34404a"), QColor("#d9e0e6")),
        )
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())
        metrics = option.fontMetrics
        width = min(option.rect.width() - 8, metrics.horizontalAdvance(text) + 12)
        badge = option.rect.adjusted(4, 5, 4 - max(0, option.rect.width() - width - 4), -5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(badge, 3, 3)
        painter.setPen(foreground)
        painter.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), text)
        painter.restore()



def protocol_label(protocol: str) -> str:
    normalized = str(protocol or "unknown").strip().lower()
    return _PROTOCOL_LABELS.get(normalized, normalized.upper() or "Proprietary")



def sender_text(message: LogicalMessageRecord) -> str:
    fields = message.fields or {}
    for key in ("sender_name", "source_name", "ecu_name", "node_name"):
        value = fields.get(key)
        if value not in (None, ""):
            return str(value)
    if message.source_address is not None:
        return f"0x{message.source_address:02X}"
    return "—"



def format_message_id(message: LogicalMessageRecord) -> str:
    if message.arbitration_id is not None:
        width = 8 if message.is_extended_id else 3
        return f"0x{message.arbitration_id:0{width}X}"
    if message.pgn is not None:
        return f"PGN 0x{message.pgn:05X}"
    return "—"



def format_logical_time(timestamp_ns: int) -> str:
    total_us = max(0, int(timestamp_ns) // 1_000)
    seconds, micros = divmod(total_us, 1_000_000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{micros:06d}"



def decoded_values_text(message: LogicalMessageRecord) -> str:
    fields = message.fields or {}
    excluded = {
        "addressing",
        "complete",
        "direction",
        "frame_count",
        "payload_length",
        "source_address",
        "destination_address",
        "j1939_identifier_candidate",
        "transport",
        "response_type",
        "base_service_id",
        "service_id",
        "requested_service_id",
        "subfunction_raw",
        "suppress_positive_response",
    }
    preferred = (
        "rpm",
        "speed",
        "torque",
        "temperature",
        "coolant_temperature",
        "gear",
        "mode",
        "service_name",
        "requested_service_name",
        "did_hex",
        "routine_id_hex",
        "negative_response_name",
        "pgn_name",
        "security_access_type",
        "security_level",
        "block_sequence_counter",
    )
    labels = {
        "coolant_temperature": "TempCoolant",
        "service_name": "Service",
        "requested_service_name": "Requested",
        "did_hex": "DID",
        "routine_id_hex": "RID",
        "negative_response_name": "NRC",
        "pgn_name": "PGN",
        "security_access_type": "Security",
        "security_level": "Level",
        "block_sequence_counter": "Block",
    }
    parts: list[str] = []
    emitted: set[str] = set()
    for key in preferred:
        if key not in fields or key in excluded:
            continue
        parts.append(f"{labels.get(key, _display_key(key))}: {_format_value(fields[key])}")
        emitted.add(key)
        if len(parts) >= 6:
            return "    ".join(parts)
    for key in sorted(fields):
        if key in emitted or key in excluded:
            continue
        value = fields[key]
        if isinstance(value, (dict, list, tuple, bytes, bytearray)):
            continue
        parts.append(f"{_display_key(key)}: {_format_value(value)}")
        if len(parts) >= 6:
            break
    return "    ".join(parts) if parts else "—"



def parse_time_filter(text: str) -> int | None:
    value = text.strip()
    if not value:
        return None
    if ":" not in value:
        return max(0, int(round(float(value.replace(",", ".")) * 1_000_000_000)))
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError("czas musi mieć format HH:MM:SS.ffffff lub liczbę sekund")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2].replace(",", "."))
    return max(0, int(round((hours * 3600 + minutes * 60 + seconds) * 1_000_000_000)))



def parse_data_pattern(text: str) -> bytes:
    value = text.strip()
    if not value:
        return b""
    compact = value.replace("0x", "").replace("0X", "").replace(" ", "")
    if compact and all(character in "0123456789abcdefABCDEF" for character in compact):
        if len(compact) % 2:
            compact = "0" + compact
        return bytes.fromhex(compact)
    number = int(value, 10)
    if not 0 <= number <= 255:
        raise ValueError("wartość dziesiętna danych musi mieścić się w zakresie 0–255")
    return bytes((number,))



def _passes_project_filter(message: LogicalMessageRecord, filter_set: object | None) -> bool:
    if filter_set is None or not getattr(filter_set, "active_count", 0):
        return True
    decision = filter_set.decide_logical_message(
        message,
        relative_time_us=int(message.first_timestamp_ns // 1_000),
    )
    return bool(decision.visible)



def _matches_criteria(
    message: LogicalMessageRecord,
    criteria: StoredLogicalCriteria,
    seen_periodic: set[tuple[object, ...]],
) -> bool:
    if criteria.protocol and str(message.protocol).lower() != criteria.protocol.lower():
        return False
    if criteria.sender and sender_text(message) != criteria.sender:
        return False
    identity = criteria.identity_text.casefold()
    if identity:
        haystack = f"{format_message_id(message)} {message.name}".casefold()
        if identity not in haystack:
            return False
    if criteria.time_from_ns is not None and message.first_timestamp_ns < criteria.time_from_ns:
        return False
    if criteria.time_to_ns is not None and message.first_timestamp_ns > criteria.time_to_ns:
        return False
    if criteria.only_errors:
        fields = message.fields or {}
        is_negative = str(fields.get("response_type", "")) == "negative-response"
        if message.complete and not message.error and not is_negative:
            return False
    if criteria.data_pattern:
        payload = message.payload
        if criteria.data_offset is None:
            if criteria.data_pattern not in payload:
                return False
        else:
            start = criteria.data_offset
            end = start + len(criteria.data_pattern)
            if start < 0 or payload[start:end] != criteria.data_pattern:
                return False
    if criteria.hide_periodic:
        signature = (
            message.arbitration_id,
            message.pgn,
            message.name,
            message.payload,
            message.source_address,
            message.destination_address,
        )
        if signature in seen_periodic:
            return False
        seen_periodic.add(signature)
    return True



def _display_key(key: str) -> str:
    return "".join(part.capitalize() for part in str(key).split("_"))



def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "Tak" if value else "Nie"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)
