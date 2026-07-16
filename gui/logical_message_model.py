from __future__ import annotations

import json
from collections.abc import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from app.logical_records import LogicalMessageRecord


class LogicalMessageTableModel(QAbstractTableModel):
    _HEADERS = (
        "Czas [ms]",
        "Protokół",
        "Transport",
        "Kierunek",
        "PGN / CAN ID",
        "Źródło",
        "Cel",
        "Usługa / PGN",
        "Długość",
        "Ramki",
        "Składanie [ms]",
        "Stan",
        "Nazwa",
        "Payload",
    )

    def __init__(self, *, capacity: int = 5_000, parent=None) -> None:
        super().__init__(parent)
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")
        self._capacity = capacity
        self._messages: list[LogicalMessageRecord] = []

    @property
    def message_count(self) -> int:
        return len(self._messages)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._messages)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):  # noqa: N802,E501
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self._HEADERS):
            return self._HEADERS[section]
        return section + 1

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._messages):
            return None
        if role == Qt.TextAlignmentRole:
            if index.column() in (0, 4, 5, 6, 8, 9, 10):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.ToolTipRole:
            message = self._messages[index.row()]
            return format_logical_message_inspector(message)
        if role != Qt.DisplayRole:
            return None

        message = self._messages[index.row()]
        fields = message.fields or {}
        column = index.column()
        if column == 0:
            return f"{message.first_timestamp_ns / 1_000_000:.3f}"
        if column == 1:
            return message.protocol.upper()
        if column == 2:
            return message.transport.upper()
        if column == 3:
            return str(fields.get("direction") or "—")
        if column == 4:
            if message.pgn is not None:
                return f"PGN 0x{message.pgn:05X}"
            if message.arbitration_id is None:
                return "—"
            width = 8 if message.is_extended_id else 3
            return f"0x{message.arbitration_id:0{width}X}"
        if column == 5:
            return "—" if message.source_address is None else f"0x{message.source_address:02X}"
        if column == 6:
            return "—" if message.destination_address is None else f"0x{message.destination_address:02X}"
        if column == 7:
            return _service_or_pgn_text(message)
        if column == 8:
            return len(message.payload)
        if column == 9:
            return message.frame_count
        if column == 10:
            return f"{(message.last_timestamp_ns - message.first_timestamp_ns) / 1_000_000:.3f}"
        if column == 11:
            return "COMPLETE" if message.complete else "INCOMPLETE"
        if column == 12:
            return message.name or "—"
        if column == 13:
            return message.payload_hex
        return None

    def clear(self) -> None:
        if not self._messages:
            return
        self.beginResetModel()
        self._messages.clear()
        self.endResetModel()

    def replace_messages(self, messages: Iterable[LogicalMessageRecord]) -> None:
        retained = list(messages)[-self._capacity :]
        self.beginResetModel()
        self._messages = retained
        self.endResetModel()

    def append_messages(self, messages: Iterable[LogicalMessageRecord]) -> None:
        incoming = list(messages)
        if not incoming:
            return
        if len(incoming) >= self._capacity:
            self.replace_messages(incoming[-self._capacity :])
            return

        overflow = max(0, len(self._messages) + len(incoming) - self._capacity)
        if overflow:
            self.beginRemoveRows(QModelIndex(), 0, overflow - 1)
            del self._messages[:overflow]
            self.endRemoveRows()

        first_row = len(self._messages)
        last_row = first_row + len(incoming) - 1
        self.beginInsertRows(QModelIndex(), first_row, last_row)
        self._messages.extend(incoming)
        self.endInsertRows()

    def message_at(self, row: int) -> LogicalMessageRecord | None:
        if 0 <= row < len(self._messages):
            return self._messages[row]
        return None

    def protocol_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for message in self._messages:
            key = message.protocol.upper()
            counts[key] = counts.get(key, 0) + 1
        return counts


def _service_or_pgn_text(message: LogicalMessageRecord) -> str:
    fields = message.fields or {}
    if message.protocol == "uds":
        service = str(
            fields.get("requested_service_name")
            or fields.get("service_name")
            or "UDS"
        )
        if fields.get("did_hex"):
            return f"{service} {fields['did_hex']}"
        if fields.get("routine_id_hex"):
            return f"{service} {fields['routine_id_hex']}"
        if fields.get("negative_response_name"):
            return f"{service} / {fields['negative_response_name']}"
        return service
    if message.protocol == "j1939":
        return str(fields.get("pgn_name") or (f"PGN 0x{message.pgn:05X}" if message.pgn is not None else "J1939"))
    return message.name or "—"


def format_logical_message_inspector(message: LogicalMessageRecord) -> str:
    fields = message.fields or {}
    lines = [
        "WIADOMOŚĆ LOGICZNA",
        "",
        f"Czas początku: {message.first_timestamp_ns / 1_000_000:.6f} ms",
        f"Czas końca: {message.last_timestamp_ns / 1_000_000:.6f} ms",
        f"Czas składania: {(message.last_timestamp_ns - message.first_timestamp_ns) / 1_000_000:.6f} ms",
        f"Sekwencja: {message.sequence}",
        f"Protokół: {message.protocol.upper()}",
        f"Transport: {message.transport.upper()}",
        f"Kierunek: {fields.get('direction', '—')}",
        f"Nazwa: {message.name or '—'}",
        f"Kompletność: {'COMPLETE' if message.complete else 'INCOMPLETE'}",
    ]
    if message.pgn is not None:
        lines.append(f"PGN: 0x{message.pgn:05X}")
    if message.arbitration_id is not None:
        width = 8 if message.is_extended_id else 3
        lines.append(f"CAN ID: 0x{message.arbitration_id:0{width}X}")
    lines.extend(
        (
            f"Źródło: {'—' if message.source_address is None else f'0x{message.source_address:02X}'}",
            f"Cel: {'—' if message.destination_address is None else f'0x{message.destination_address:02X}'}",
            f"Długość payloadu: {len(message.payload)} B",
            f"Liczba ramek: {message.frame_count}",
            f"Sekwencje ramek: {', '.join(str(value) for value in message.frame_sequences)}",
            f"Pewność klasyfikacji: {message.confidence:.3f}",
            "",
            "PAYLOAD",
            message.payload_hex or "—",
        )
    )
    if fields:
        lines.extend(("", "POLA PROTOKOŁU"))
        preferred = (
            "service_name",
            "response_type",
            "requested_service_name",
            "negative_response_code",
            "negative_response_name",
            "subfunction",
            "security_level",
            "security_access_type",
            "did_hex",
            "routine_id_hex",
            "pgn_name",
            "priority",
            "pdu_type",
            "addressing",
            "declared_payload_length",
            "declared_packet_count",
            "received_packet_count",
        )
        emitted: set[str] = set()
        for key in preferred:
            if key in fields:
                lines.append(f"{key}: {_format_field_value(fields[key])}")
                emitted.add(key)
        for key in sorted(fields):
            if key not in emitted:
                lines.append(f"{key}: {_format_field_value(fields[key])}")
    if message.error:
        lines.extend(("", "BŁĄD TRANSPORTU", message.error))
    return "\n".join(lines)


def _format_field_value(value: object) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
