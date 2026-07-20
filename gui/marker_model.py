from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from app.markers import MarkerPreset


class MarkerPresetTableModel(QAbstractTableModel):
    _HEADERS = ("Aktywny", "Nazwa", "Skrót", "Obszar", "Kolor")

    def __init__(self, presets: Iterable[MarkerPreset] = (), parent=None) -> None:
        super().__init__(parent)
        self._presets = list(presets)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._presets)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):  # noqa: N802,E501
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self._HEADERS):
            return self._HEADERS[section]
        return section + 1

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._presets):
            return None
        preset = self._presets[index.row()]
        if index.column() == 0 and role == Qt.CheckStateRole:
            return Qt.Checked if preset.enabled else Qt.Unchecked
        if role == Qt.DisplayRole:
            if index.column() == 1:
                return preset.name
            if index.column() == 2:
                return preset.shortcut
            if index.column() == 3:
                return preset.area or "—"
            if index.column() == 4:
                return preset.color
        if role == Qt.TextAlignmentRole and index.column() in (0, 2):
            return int(Qt.AlignCenter)
        if role == Qt.ToolTipRole:
            return f"{preset.shortcut} — {preset.name}"
        return None

    def flags(self, index: QModelIndex):
        flags = super().flags(index)
        if index.isValid() and index.column() == 0:
            flags |= Qt.ItemIsUserCheckable
        return flags

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:  # noqa: N802
        if (
            not index.isValid()
            or index.column() != 0
            or role != Qt.CheckStateRole
            or not 0 <= index.row() < len(self._presets)
        ):
            return False
        old = self._presets[index.row()]
        self._presets[index.row()] = MarkerPreset(
            id=old.id,
            name=old.name,
            shortcut=old.shortcut,
            color=old.color,
            area=old.area,
            enabled=value == Qt.Checked,
            sort_order=old.sort_order,
        )
        self.dataChanged.emit(index, index, [Qt.CheckStateRole])
        return True

    def presets(self) -> list[MarkerPreset]:
        return list(self._presets)

    def active_presets(self) -> list[MarkerPreset]:
        return [preset for preset in self._presets if preset.enabled]

    def preset_at(self, row: int) -> MarkerPreset | None:
        if 0 <= row < len(self._presets):
            return self._presets[row]
        return None

    def add_preset(self, preset: MarkerPreset) -> None:
        row = len(self._presets)
        self.beginInsertRows(QModelIndex(), row, row)
        self._presets.append(preset)
        self.endInsertRows()

    def replace_preset(self, row: int, preset: MarkerPreset) -> None:
        if not 0 <= row < len(self._presets):
            raise IndexError(row)
        self._presets[row] = preset
        left = self.index(row, 0)
        right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(left, right)

    def remove_row(self, row: int) -> None:
        if not 0 <= row < len(self._presets):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._presets[row]
        self.endRemoveRows()
