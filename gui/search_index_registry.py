from __future__ import annotations

from weakref import WeakKeyDictionary

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import QTableView, QWidget

from app.search_engine import SearchDocument


_INDEX_CHUNK_ROWS = 2_000
_DISCOVERY_INTERVAL_MS = 250


class QtTableSearchIndex(QObject):
    """Incremental search document index associated with one Qt item model."""

    progress_changed = Signal(int, int)
    ready_changed = Signal(bool)

    def __init__(self, model, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model = model
        self._headers = _model_headers(model)
        self._documents: list[SearchDocument] = []
        self._connections: list[tuple[object, object]] = []
        self._next_row = 0
        self._dirty = False

        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._build_chunk)

        self._connect(model.rowsInserted, self._rows_inserted)
        self._connect(model.rowsRemoved, self._structure_changed)
        self._connect(model.dataChanged, self._data_changed)
        self._connect(model.modelReset, self._structure_changed)
        self._connect(model.layoutChanged, self._structure_changed)
        self._connect(model.headerDataChanged, self._headers_changed)
        self._connect(model.columnsInserted, self._headers_changed)
        self._connect(model.columnsRemoved, self._headers_changed)
        self._connect(model.destroyed, self._model_destroyed)
        self.start()

    @property
    def model(self):
        return self._model

    @property
    def headers(self) -> list[str]:
        return list(self._headers)

    @property
    def is_ready(self) -> bool:
        model = self._model
        return model is not None and not self._dirty and self._next_row >= model.rowCount()

    @property
    def progress(self) -> tuple[int, int]:
        model = self._model
        return self._next_row, model.rowCount() if model is not None else 0

    def start(self) -> None:
        if self._model is not None and not self.is_ready and not self._timer.isActive():
            self._timer.start()

    def snapshot(self) -> tuple[SearchDocument, ...]:
        return tuple(self._documents)

    def close(self) -> None:
        self._timer.stop()
        self._disconnect()
        self._model = None
        self._documents.clear()
        self._next_row = 0

    def _build_chunk(self) -> None:
        model = self._model
        if model is None:
            self._timer.stop()
            return
        was_ready = self.is_ready
        if self._dirty:
            self._headers = _model_headers(model)
            self._documents.clear()
            self._next_row = 0
            self._dirty = False

        stop = min(model.rowCount(), self._next_row + _INDEX_CHUNK_ROWS)
        for row in range(self._next_row, stop):
            self._documents.append(self._read_document(row))
        self._next_row = stop
        current, total = self.progress
        self.progress_changed.emit(current, total)

        ready = self.is_ready
        if ready:
            self._timer.stop()
        if ready != was_ready:
            self.ready_changed.emit(ready)

    def _read_document(self, row: int) -> SearchDocument:
        model = self._model
        fields = {
            self._headers[column]: str(model.data(model.index(row, column), Qt.DisplayRole) or "")
            for column in range(model.columnCount())
        }
        return SearchDocument(row=row, fields=fields)

    def _rows_inserted(self, _parent, first: int, last: int) -> None:
        model = self._model
        if model is None:
            return

        # Appends beyond the already indexed prefix never invalidate that prefix.
        if first >= self._next_row:
            if first == self._next_row and self._next_row == len(self._documents):
                for row in range(first, last + 1):
                    self._documents.append(self._read_document(row))
                self._next_row = last + 1
                self.progress_changed.emit(*self.progress)
                self.ready_changed.emit(self.is_ready)
            else:
                self.start()
            return

        self._mark_dirty()

    def _structure_changed(self, *_args) -> None:
        self._mark_dirty()

    def _headers_changed(self, *_args) -> None:
        self._mark_dirty()

    def _mark_dirty(self) -> None:
        self._dirty = True
        self.ready_changed.emit(False)
        self.start()

    def _data_changed(self, top_left, bottom_right, *_roles) -> None:
        if self._model is None:
            return
        first = max(0, top_left.row())
        last = min(bottom_right.row(), len(self._documents) - 1)
        for row in range(first, last + 1):
            self._documents[row] = self._read_document(row)

    def _model_destroyed(self, *_args) -> None:
        self._timer.stop()
        self._connections.clear()
        self._model = None
        self._documents.clear()
        self._next_row = 0
        self.ready_changed.emit(False)

    def _connect(self, signal, slot) -> None:
        signal.connect(slot)
        self._connections.append((signal, slot))

    def _disconnect(self) -> None:
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._connections.clear()


class SearchIndexRegistry(QObject):
    """Discovers CRT tables and prepares their indexes before Ctrl+F is used."""

    def __init__(self, root: QWidget, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._root = root
        self._indexes: WeakKeyDictionary[object, QtTableSearchIndex] = WeakKeyDictionary()
        self._discovery_timer = QTimer(self)
        self._discovery_timer.setInterval(_DISCOVERY_INTERVAL_MS)
        self._discovery_timer.timeout.connect(self.discover_tables)
        self._discovery_timer.start()
        QTimer.singleShot(0, self.discover_tables)

    def index_for_table(self, table: QTableView | None) -> QtTableSearchIndex | None:
        if table is None or table.model() is None:
            return None
        return self.ensure_model(table.model())

    def ensure_model(self, model) -> QtTableSearchIndex:
        index = self._indexes.get(model)
        if index is None:
            index = QtTableSearchIndex(model, self)
            self._indexes[model] = index
        else:
            index.start()
        return index

    def discover_tables(self) -> None:
        root = self._root
        if root is None:
            return
        for table in root.findChildren(QTableView):
            model = table.model()
            if model is not None:
                self.ensure_model(model)

    def close(self) -> None:
        self._discovery_timer.stop()
        for index in list(self._indexes.values()):
            index.close()
        self._indexes.clear()


def _model_headers(model) -> list[str]:
    headers: list[str] = []
    used: dict[str, int] = {}
    for column in range(model.columnCount()):
        base = str(model.headerData(column, Qt.Horizontal, Qt.DisplayRole) or f"Kolumna {column + 1}")
        count = used.get(base, 0)
        used[base] = count + 1
        headers.append(base if count == 0 else f"{base} ({count + 1})")
    return headers
