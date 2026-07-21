from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableView

from .fixed_marker_menu_shell import FixedMarkerMenuMainWindow
from .log_search_window import LogSearchWindow
from .project_preparation_progress import (
    ProjectPreparationProgress,
    ProjectPreparationStatusWidget,
)
from .search_index_registry import SearchIndex, SearchIndexRegistry


class SearchEnabledMainWindow(FixedMarkerMenuMainWindow):
    """Engineering shell with lazy memory and durable project search indexes."""

    def __init__(self, services) -> None:
        self._log_search_window: LogSearchWindow | None = None
        self._search_index_registry: SearchIndexRegistry | None = None
        self._tracked_search_indexes: dict[int, tuple[str, str]] = {}
        super().__init__(services)

        self.project_preparation = ProjectPreparationProgress(self)
        self.project_preparation_status = ProjectPreparationStatusWidget(
            self.project_preparation,
            self.statusBar(),
        )
        self.statusBar().addWidget(self.project_preparation_status)
        self._search_index_registry = SearchIndexRegistry(self.tabs, self)

    def _build_actions(self) -> None:
        super()._build_actions()
        try:
            self.search_action.triggered.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.search_action.setShortcut("Ctrl+F")
        self.search_action.setShortcutContext(Qt.ApplicationShortcut)
        self.search_action.setToolTip("Otwórz wyszukiwanie w aktywnym logu (Ctrl+F)")
        self.search_action.triggered.connect(self._open_log_search)

    def _open_log_search(self) -> None:
        window = self._log_search_window
        if window is None:
            window = LogSearchWindow(self)
            self._log_search_window = window

        table, session_path = self._active_search_context()
        registry = self._search_index_registry
        index = (
            registry.index_for_table(
                table,
                project=self.project,
                session_path=session_path,
            )
            if registry is not None
            else None
        )
        if index is not None:
            self._track_search_index(index)
        window.set_target_index(table, index)

        if window.isMinimized():
            window.showNormal()
        else:
            window.show()
        window.raise_()
        window.activateWindow()
        window.query_edit.selectAll()
        window.query_edit.setFocus(Qt.ShortcutFocusReason)

    def _track_search_index(self, index: SearchIndex, *, label: str | None = None) -> None:
        token = id(index)
        if token in self._tracked_search_indexes:
            return

        tab_title = self.tabs.tabText(self.tabs.currentIndex()).strip()
        resolved_label = label or "Indeks wyszukiwania"
        if label is None and tab_title:
            resolved_label = f"{resolved_label} — {tab_title}"
        key = f"search-index:{token}"
        self._tracked_search_indexes[token] = (key, resolved_label)

        index.progress_changed.connect(
            lambda current, total, source=index: self._search_index_progress(
                source,
                current,
                total,
            )
        )
        index.ready_changed.connect(
            lambda ready, source=index: self._search_index_ready(source, ready)
        )
        failed_signal = getattr(index, "failed", None)
        if failed_signal is not None:
            failed_signal.connect(
                lambda error, source=index: self._search_index_failed(source, error)
            )

        if not index.is_ready:
            current, total = index.progress
            self.project_preparation.begin_task(
                key,
                resolved_label,
                current=current,
                total=total,
                stage_index=1,
                stage_count=4,
                priority=10,
            )

    def _search_index_progress(
        self,
        index: SearchIndex,
        current: int,
        total: int,
    ) -> None:
        tracked = self._tracked_search_indexes.get(id(index))
        if tracked is None:
            return
        key, label = tracked
        if index.is_ready:
            self.project_preparation.complete_task(key)
            return
        self.project_preparation.update_task(
            key,
            current=current,
            total=total,
            label=label,
        )

    def _search_index_ready(self, index: SearchIndex, ready: bool) -> None:
        tracked = self._tracked_search_indexes.get(id(index))
        if tracked is None:
            return
        key, label = tracked
        if ready:
            self.project_preparation.complete_task(key)
            return
        current, total = index.progress
        self.project_preparation.begin_task(
            key,
            label,
            current=current,
            total=total,
            stage_index=1,
            stage_count=4,
            priority=10,
        )

    def _search_index_failed(self, index: SearchIndex, error: str) -> None:
        tracked = self._tracked_search_indexes.get(id(index))
        if tracked is None:
            return
        key, _label = tracked
        self.project_preparation.fail_task(key, error)
        self._append_output(f"Błąd trwałego indeksu wyszukiwania: {error}")

    def _active_search_context(self) -> tuple[QTableView | None, Path | None]:
        current = self.tabs.currentWidget()
        table = self._active_search_table()
        if current is None or table is None:
            return table, None
        frame_table = getattr(current, "frame_table", None)
        path = getattr(current, "path", None)
        if frame_table is table and path is not None:
            return table, Path(path)
        return table, None

    def _active_search_table(self) -> QTableView | None:
        current = self.tabs.currentWidget()
        if current is None:
            return None
        visible_tables = [
            table
            for table in current.findChildren(QTableView)
            if table.isVisible() and table.model() is not None
        ]
        if visible_tables:
            focused = next((table for table in visible_tables if table.hasFocus()), None)
            return focused or visible_tables[0]
        tables = [
            table
            for table in current.findChildren(QTableView)
            if table.model() is not None
        ]
        return tables[0] if tables else None

    def _prepare_persistent_session(self, path: str | Path) -> None:
        project = self.project
        registry = self._search_index_registry
        if project is None or registry is None:
            return
        session = project.session_by_path(path)
        if session is None or session.status == "recording":
            return
        index = registry.persistent_index_for_session(project, path, activate=True)
        if index is None:
            return
        self._track_search_index(
            index,
            label=f"Indeks wyszukiwania — {session.name}",
        )

    def _import_completed(self, source: str, target: str) -> None:
        super()._import_completed(source, target)
        self._prepare_persistent_session(target)

    def _open_live_capture(self) -> None:
        super()._open_live_capture()
        widget = self.navigator.widget("live-capture")
        if widget is None or bool(widget.property("persistentSearchPreparationBound")):
            return

        def prepare_saved_session() -> None:
            path = getattr(widget, "_finalized_session_path", None)
            if path is not None:
                self._prepare_persistent_session(path)

        widget.project_changed.connect(prepare_saved_session)
        widget.setProperty("persistentSearchPreparationBound", True)

    def _set_project(self, project) -> None:
        previous_root = Path(self.project.root).resolve() if self.project is not None else None
        next_root = Path(project.root).resolve()
        super()._set_project(project)

        current_root = Path(self.project.root).resolve() if self.project is not None else None
        project_changed = (
            previous_root is not None
            and previous_root != next_root
            and current_root == next_root
        )
        if not project_changed:
            return
        if self._search_index_registry is not None:
            self._search_index_registry.close()
        self._tracked_search_indexes.clear()
        if hasattr(self, "project_preparation"):
            self.project_preparation.clear()

    def _close_tab(self, index: int) -> None:
        current = self.tabs.widget(index)
        target = self._log_search_window._target_table if self._log_search_window else None
        if target is not None and current is not None and current.isAncestorOf(target):
            self._log_search_window.set_target_index(None, None)
        super()._close_tab(index)

    def closeEvent(self, event) -> None:  # noqa: N802
        super().closeEvent(event)
        if not event.isAccepted():
            return
        if self._search_index_registry is not None:
            self._search_index_registry.close()
        if hasattr(self, "project_preparation"):
            self.project_preparation.clear()
