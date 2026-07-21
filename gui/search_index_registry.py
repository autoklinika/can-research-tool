from __future__ import annotations

from pathlib import Path
from time import perf_counter
from weakref import WeakKeyDictionary

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import QTableView, QWidget

from app.project import CrtProject
from app.project_search_index import ProjectSearchIndex
from app.search_engine import SearchDocument

from .persistent_search_index import PersistentSessionSearchIndex


_INDEX_TIME_BUDGET_MS = 4.0
_MAX_ROWS_PER_SLICE = 512


class QtTableSearchIndex(QObject):
    """Lazy, time-sliced search index associated with one Qt item model.

    The index is dormant until ``start()`` is called. Once activated it keeps
    itself synchronized with later model appends, which is suitable for Live
    Capture without imposing work during normal application startup.
    """

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
        self._activated = False
        self._last_ready_state = self.is_ready

        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._build_slice)

        self._connect(model.rowsInserted, self._rows_inserted)
        self._connect(model.rowsRemoved, self._structure_changed)
        self._connect(model.dataChanged, self._data_changed)
        self._connect(model.modelReset, self._structure_changed)
        self._connect(model.layoutChanged, self._structure_changed)
        self._connect(model.headerDataChanged, self._headers_changed)
        self._connect(model.columnsInserted, self._headers_changed)
        self._connect(model.columnsRemoved, self._headers_changed)
        self._connect(model.destroyed, self._model_destroyed)

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
    def is_active(self) -> bool:
        return self._activated

    @property
    def progress(self) -> tuple[int, int]:
        model = self._model
        return self._next_row, model.rowCount() if model is not None else 0

    def start(self) -> None:
        self._activated = True
        if self._model is not None and not self.is_ready and not self._timer.isActive():
            self._timer.start()

    def snapshot(self) -> tuple[SearchDocument, ...]:
        return tuple(self._documents)

    def close(self) -> None:
        self._activated = False
        self._timer.stop()
        self._disconnect()
        self._model = None
        self._documents.clear()
        self._next_row = 0

    def _build_slice(self) -> None:
        model = self._model
        if model is None or not self._activated:
            self._timer.stop()
            return

        if self._dirty:
            self._headers = _model_headers(model)
            self._documents.clear()
            self._next_row = 0
            self._dirty = False

        row_count = model.rowCount()
        started = perf_counter()
        processed = 0

        while self._next_row < row_count and processed < _MAX_ROWS_PER_SLICE:
            self._documents.append(self._read_document(self._next_row))
            self._next_row += 1
            processed += 1
            if (perf_counter() - started) * 1000.0 >= _INDEX_TIME_BUDGET_MS:
                break

        self.progress_changed.emit(*self.progress)
        self._publish_ready_state()
        if self.is_ready:
            self._timer.stop()

    def _read_document(self, row: int) -> SearchDocument:
        model = self._model
        fields = {
            self._headers[column]: str(model.data(model.index(row, column), Qt.DisplayRole) or "")
            for column in range(model.columnCount())
        }
        return SearchDocument(row=row, fields=fields)

    def _rows_inserted(self, _parent, first: int, _last: int) -> None:
        if self._model is None:
            return
        if first < self._next_row:
            self._mark_dirty()
            return
        self._publish_ready_state()
        if self._activated and not self._timer.isActive():
            self._timer.start()

    def _structure_changed(self, *_args) -> None:
        self._mark_dirty()

    def _headers_changed(self, *_args) -> None:
        self._mark_dirty()

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._publish_ready_state()
        if self._activated and not self._timer.isActive():
            self._timer.start()

    def _data_changed(self, top_left, bottom_right, *_roles) -> None:
        if self._model is None or not self._documents:
            return
        first = max(0, top_left.row())
        last = min(bottom_right.row(), len(self._documents) - 1)
        for row in range(first, last + 1):
            self._documents[row] = self._read_document(row)

    def _publish_ready_state(self) -> None:
        ready = self.is_ready
        if ready != self._last_ready_state:
            self._last_ready_state = ready
            self.ready_changed.emit(ready)

    def _model_destroyed(self, *_args) -> None:
        self._activated = False
        self._timer.stop()
        self._connections.clear()
        self._model = None
        self._documents.clear()
        self._next_row = 0
        self._publish_ready_state()

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


SearchIndex = QtTableSearchIndex | PersistentSessionSearchIndex


class SearchIndexRegistry(QObject):
    """Own lazy memory indexes and durable per-session project indexes."""

    def __init__(self, root: QWidget | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._root = root
        self._indexes: WeakKeyDictionary[object, QtTableSearchIndex] = WeakKeyDictionary()
        self._persistent_indexes: dict[
            tuple[str, str], PersistentSessionSearchIndex
        ] = {}

    def index_for_table(
        self,
        table: QTableView | None,
        *,
        project: CrtProject | None = None,
        session_path: str | Path | None = None,
    ) -> SearchIndex | None:
        if table is None or table.model() is None:
            return None

        if project is not None and session_path is not None:
            session = project.session_by_path(session_path)
            model = table.model()
            if (
                session is not None
                and session.status != "recording"
                and callable(getattr(model, "frame_at", None))
                and int(model.rowCount()) == int(session.frame_count)
            ):
                persistent = self.persistent_index_for_session(
                    project,
                    session_path,
                    activate=True,
                )
                if persistent is not None:
                    return persistent

        return self.ensure_model(table.model(), activate=True)

    def ensure_model(self, model, *, activate: bool = False) -> QtTableSearchIndex:
        index = self._indexes.get(model)
        if index is None:
            index = QtTableSearchIndex(model, self)
            self._indexes[model] = index
        if activate:
            index.start()
        return index

    def persistent_index_for_session(
        self,
        project: CrtProject,
        session_path: str | Path,
        *,
        activate: bool = False,
    ) -> PersistentSessionSearchIndex | None:
        session = project.session_by_path(session_path)
        if session is None or session.status == "recording":
            return None
        path = project.absolute_path(session.relative_path)
        if not path.is_file():
            return None
        key = (project.manifest.id, session.id)
        index = self._persistent_indexes.get(key)
        if index is None:
            index = PersistentSessionSearchIndex(project, session, self)
            self._persistent_indexes[key] = index
        if activate:
            index.start()
        return index

    def remove_session(self, project: CrtProject, session_id: str) -> None:
        key = (project.manifest.id, session_id)
        index = self._persistent_indexes.pop(key, None)
        if index is not None:
            index.close()
            index.deleteLater()
        ProjectSearchIndex(project).remove_session(session_id)

    def close(self) -> None:
        for index in list(self._indexes.values()):
            index.close()
        self._indexes.clear()
        for index in list(self._persistent_indexes.values()):
            index.close()
        self._persistent_indexes.clear()


def _model_headers(model) -> list[str]:
    headers: list[str] = []
    used: dict[str, int] = {}
    for column in range(model.columnCount()):
        base = str(model.headerData(column, Qt.Horizontal, Qt.DisplayRole) or f"Kolumna {column + 1}")
        count = used.get(base, 0)
        used[base] = count + 1
        headers.append(base if count == 0 else f"{base} ({count + 1})")
    return headers
