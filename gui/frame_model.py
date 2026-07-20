from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from app.models import CanFrame


class FrameTableModel(QAbstractTableModel):
    """Bounded table model for the live CAN frame view.

    Rows are inserted and removed in batches. The model never owns more than
    ``capacity`` frames, even if the capture contains millions of records.
    """

    _HEADERS = (
        "Czas [ms]",
        "Sekwencja",
        "CAN ID",
        "Typ",
        "DLC",
        "Dane",
        "Kanał",
        "Flagi",
    )

    def __init__(self, *, capacity: int = 20_000, parent=None) -> None:
        super().__init__(parent)
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")
        self._capacity = capacity
        self._frames: list[CanFrame] = []

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._frames)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):  # noqa: N802,E501
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self._HEADERS):
            return self._HEADERS[section]
        return section + 1

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._frames):
            return None
        if role not in (Qt.DisplayRole, Qt.TextAlignmentRole):
            return None
        if role == Qt.TextAlignmentRole:
            if index.column() in (0, 1, 2, 4, 6):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        frame = self._frames[index.row()]
        column = index.column()
        if column == 0:
            return f"{frame.timestamp_ns / 1_000_000:.3f}"
        if column == 1:
            return frame.sequence
        if column == 2:
            width = 8 if frame.is_extended_id else 3
            return f"0x{frame.arbitration_id:0{width}X}"
        if column == 3:
            return "EXT" if frame.is_extended_id else "STD"
        if column == 4:
            return frame.dlc
        if column == 5:
            return frame.data_hex
        if column == 6:
            return frame.channel
        if column == 7:
            flags: list[str] = []
            if frame.is_remote_frame:
                flags.append("RTR")
            if frame.is_error_frame:
                flags.append("ERR")
            if frame.source_flags:
                flags.append(f"0x{frame.source_flags:X}")
            return ", ".join(flags)
        return None

    def clear(self) -> None:
        if not self._frames:
            return
        self.beginResetModel()
        self._frames.clear()
        self.endResetModel()

    def replace_frames(self, frames: Iterable[CanFrame]) -> None:
        retained = list(frames)[-self._capacity :]
        self.beginResetModel()
        self._frames = retained
        self.endResetModel()

    def append_frames(self, frames: Iterable[CanFrame]) -> None:
        incoming = list(frames)
        if not incoming:
            return
        if len(incoming) >= self._capacity:
            self.replace_frames(incoming[-self._capacity :])
            return

        overflow = max(0, len(self._frames) + len(incoming) - self._capacity)
        if overflow:
            # Removing exactly the overflow on every GUI refresh turns the list
            # into a permanent O(capacity) front-shift once the buffer is full.
            # Drop a chunk instead, so expensive front removals happen only
            # occasionally while the model remains strictly bounded.
            trim_chunk = max(1, self._capacity // 10)
            remove_count = min(len(self._frames), max(overflow, trim_chunk))
            self.beginRemoveRows(QModelIndex(), 0, remove_count - 1)
            del self._frames[:remove_count]
            self.endRemoveRows()

        first_row = len(self._frames)
        last_row = first_row + len(incoming) - 1
        self.beginInsertRows(QModelIndex(), first_row, last_row)
        self._frames.extend(incoming)
        self.endInsertRows()

    def frame_at(self, row: int) -> CanFrame | None:
        if 0 <= row < len(self._frames):
            return self._frames[row]
        return None

    def snapshot_frames(self) -> tuple[CanFrame, ...]:
        """Return an immutable reference snapshot safe for background evaluation."""

        return tuple(self._frames)
