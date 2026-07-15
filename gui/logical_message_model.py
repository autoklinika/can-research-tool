from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from app.logical_records import LogicalMessageRecord


class LogicalMessageTableModel(QAbstractTableModel):
    _HEADERS = (
        "Czas [ms]",
        "Protokół",
        "Transport",
        "PGN / CAN ID",
        "Źródło",
        "Cel",
        "Długość",
        "Ramki",
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
            if index.column() in (0, 3, 4, 5, 6, 7):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role != Qt.DisplayRole:
            return None

        message = self._messages[index.row()]
        column = index.column()
        if column == 0:
            return f"{message.first_timestamp_ns / 1_000_000:.3f}"
        if column == 1:
            return message.protocol.upper()
        if column == 2:
            return message.transport.upper()
        if column == 3:
            if message.pgn is not None:
                return f"PGN 0x{message.pgn:X}"
            if message.arbitration_id is None:
                return "—"
            width = 8 if message.is_extended_id else 3
            return f"0x{message.arbitration_id:0{width}X}"
        if column == 4:
            return "—" if message.source_address is None else f"0x{message.source_address:02X}"
        if column == 5:
            return "—" if message.destination_address is None else f"0x{message.destination_address:02X}"
        if column == 6:
            return len(message.payload)
        if column == 7:
            return message.frame_count
        if column == 8:
            return "COMPLETE" if message.complete else "INCOMPLETE"
        if column == 9:
            return message.name or "—"
        if column == 10:
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


def format_logical_message_inspector(message: LogicalMessageRecord) -> str:
    lines = [
        "WIADOMOŚĆ LOGICZNA",
        "",
        f"Czas początku: {message.first_timestamp_ns / 1_000_000:.6f} ms",
        f"Czas końca: {message.last_timestamp_ns / 1_000_000:.6f} ms",
        f"Sekwencja: {message.sequence}",
        f"Protokół: {message.protocol.upper()}",
        f"Transport: {message.transport.upper()}",
        f"Nazwa: {message.name or '—'}",
        f"Kompletność: {'COMPLETE' if message.complete else 'INCOMPLETE'}",
    ]
    if message.pgn is not None:
        lines.append(f"PGN: 0x{message.pgn:X}")
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
    if message.fields:
        lines.extend(("", "POLA PROTOKOŁU"))
        for key, value in sorted(message.fields.items()):
            lines.append(f"{key}: {value}")
    if message.error:
        lines.extend(("", "BŁĄD", message.error))
    return "\n".join(lines)
