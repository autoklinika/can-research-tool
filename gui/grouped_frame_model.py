from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from app.models import CanFrame


FrameGroupKey = tuple[int, bool, int]


class GroupedFrameTableModel(QAbstractTableModel):
    """Present the latest CAN frame for every channel/format/identifier key.

    The model is intentionally independent from capture and persistence. It stores
    only one frame reference per visible key and preserves the row assigned when a
    key first appears. Later frames update that row in place.
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

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._frames: list[CanFrame] = []
        self._row_by_key: dict[FrameGroupKey, int] = {}

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._frames)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ):  # noqa: N802
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self._HEADERS):
            return self._HEADERS[section]
        return section + 1

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        frame = self.frame_at(index.row()) if index.isValid() else None
        if frame is None:
            return None
        return _frame_data(frame, index.column(), role)

    def clear(self) -> None:
        if not self._frames:
            return
        self.beginResetModel()
        self._frames.clear()
        self._row_by_key.clear()
        self.endResetModel()

    def replace_frames(self, frames: Iterable[CanFrame]) -> None:
        ordered_keys: list[FrameGroupKey] = []
        latest_by_key: dict[FrameGroupKey, CanFrame] = {}
        for frame in frames:
            key = frame_group_key(frame)
            if key not in latest_by_key:
                ordered_keys.append(key)
            latest_by_key[key] = frame

        self.beginResetModel()
        self._frames = [latest_by_key[key] for key in ordered_keys]
        self._row_by_key = {key: row for row, key in enumerate(ordered_keys)}
        self.endResetModel()

    def append_frames(self, frames: Iterable[CanFrame]) -> None:
        ordered_keys: list[FrameGroupKey] = []
        latest_by_key: dict[FrameGroupKey, CanFrame] = {}
        for frame in frames:
            key = frame_group_key(frame)
            if key not in latest_by_key:
                ordered_keys.append(key)
            latest_by_key[key] = frame
        if not ordered_keys:
            return

        updated_rows: list[int] = []
        new_items: list[tuple[FrameGroupKey, CanFrame]] = []
        for key in ordered_keys:
            frame = latest_by_key[key]
            row = self._row_by_key.get(key)
            if row is None:
                new_items.append((key, frame))
                continue
            self._frames[row] = frame
            updated_rows.append(row)

        if updated_rows:
            self._emit_updated_ranges(updated_rows)

        if new_items:
            first_row = len(self._frames)
            last_row = first_row + len(new_items) - 1
            self.beginInsertRows(QModelIndex(), first_row, last_row)
            for key, frame in new_items:
                self._row_by_key[key] = len(self._frames)
                self._frames.append(frame)
            self.endInsertRows()

    def frame_at(self, row: int) -> CanFrame | None:
        if 0 <= row < len(self._frames):
            return self._frames[row]
        return None

    def snapshot_frames(self) -> tuple[CanFrame, ...]:
        return tuple(self._frames)

    def _emit_updated_ranges(self, rows: list[int]) -> None:
        ordered = sorted(set(rows))
        start = previous = ordered[0]
        for row in ordered[1:]:
            if row == previous + 1:
                previous = row
                continue
            self._emit_data_changed(start, previous)
            start = previous = row
        self._emit_data_changed(start, previous)

    def _emit_data_changed(self, first_row: int, last_row: int) -> None:
        self.dataChanged.emit(
            self.index(first_row, 0),
            self.index(last_row, len(self._HEADERS) - 1),
            [Qt.DisplayRole],
        )


def frame_group_key(frame: CanFrame) -> FrameGroupKey:
    """Separate identical numeric IDs by CAN channel and STD/EXT format."""

    return (
        int(frame.channel),
        bool(frame.is_extended_id),
        int(frame.arbitration_id),
    )


def _frame_data(frame: CanFrame, column: int, role: int):
    if role == Qt.TextAlignmentRole:
        if column in (0, 1, 2, 4, 6):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return int(Qt.AlignLeft | Qt.AlignVCenter)
    if role != Qt.DisplayRole:
        return None
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
