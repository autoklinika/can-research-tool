from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QModelIndex, QObject, Qt
from PySide6.QtWidgets import QTableView, QWidget

from .live_capture import LiveCaptureWidget
from .log_search_window import LogSearchWindow
from .search_index_registry import SearchIndex, SearchIndexRegistry
from .stored_search_navigation import StoredSearchNavigator
from .window_fullscreen import enable_full_screen

if TYPE_CHECKING:
    from .main_window import MainWindow


class LogSearchController(QObject):
    """Ctrl+F search over the active tab with lazy and durable project indexes."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._window = window
        self._search_window: LogSearchWindow | None = None
        self._registry = SearchIndexRegistry(window.tabs, window)
        self._tracked_indexes: dict[int, tuple[str, str]] = {}
        self._stored_navigator: StoredSearchNavigator | None = None

    @property
    def search_window(self) -> LogSearchWindow | None:
        return self._search_window

    def open(self) -> None:
        window = self._search_window
        if window is None:
            window = LogSearchWindow(self._window)
            window.full_screen_controller = enable_full_screen(
                window,
                action_object_name="logSearchFullScreenAction",
            )
            window.full_screen_action = window.full_screen_controller.action
            window.results.selectionModel().currentChanged.connect(
                self._stored_result_changed
            )
            self._search_window = window

        table, session_path = self._active_search_context()
        index = self._registry.index_for_table(
            table,
            project=self._window.project,
            session_path=session_path,
        )
        if index is not None:
            self._track_index(index)
        window.set_target_index(table, index)
        self._configure_stored_navigator(window, table, index)

        if window.isMinimized():
            window.showNormal()
        else:
            window.show()
        window.raise_()
        window.activateWindow()
        window.query_edit.selectAll()
        window.query_edit.setFocus(Qt.ShortcutFocusReason)

    def bind_live_capture(self, widget: LiveCaptureWidget) -> None:
        """Index a Live session once it has been finalized as a project session."""

        def prepare_saved_session() -> None:
            path = widget.finalized_session_path
            if path is not None:
                self.prepare_persistent_session(path)

        widget.project_changed.connect(prepare_saved_session)

    def prepare_persistent_session(self, path: str | Path) -> None:
        project = self._window.project
        if project is None:
            return
        session = project.session_by_path(path)
        if session is None or session.status == "recording":
            return
        index = self._registry.persistent_index_for_session(project, path, activate=True)
        if index is None:
            return
        self._track_index(index, label=f"Indeks wyszukiwania — {session.name}")

    def detach_from(self, tab: QWidget | None) -> None:
        """Release the search target before ``tab`` is closed."""

        window = self._search_window
        if window is None or tab is None:
            return
        target = window.target_table
        if target is None or not tab.isAncestorOf(target):
            return
        self._replace_stored_navigator(None)
        window.set_builtin_navigation_enabled(True)
        window.set_target_index(None, None)

    def reset(self) -> None:
        """Drop all indexes and progress after the active project changed."""

        self._replace_stored_navigator(None)
        self._registry.close()
        self._tracked_indexes.clear()
        self._window.project_preparation.clear()

    def _configure_stored_navigator(
        self,
        window: LogSearchWindow,
        table: QTableView | None,
        index: SearchIndex | None,
    ) -> None:
        self._replace_stored_navigator(None)
        current = self._window.tabs.currentWidget()
        persistent_raw_target = (
            current is not None
            and table is not None
            and index is not None
            and getattr(index, "source_id", None) is not None
            and getattr(current, "frame_table", None) is table
            and hasattr(current, "_stored_session_controller")
            and hasattr(current, "_stored_session_integration")
        )
        window.set_builtin_navigation_enabled(not persistent_raw_target)
        if not persistent_raw_target:
            return
        self._stored_navigator = StoredSearchNavigator(
            current,
            cancel_widget=window,
            parent=self._window,
        )

    def _stored_result_changed(
        self,
        current: QModelIndex,
        _previous: QModelIndex,
    ) -> None:
        navigator = self._stored_navigator
        window = self._search_window
        if navigator is None or window is None:
            return
        position = current.row()
        row = window.hit_row(position) if current.isValid() else None
        if row is None:
            window.position_label.clear()
            navigator.cancel()
            return
        window.position_label.setText(f"{position + 1} / {window.hit_count}")
        navigator.navigate_to_source_row(row)

    def _replace_stored_navigator(
        self,
        navigator: StoredSearchNavigator | None,
    ) -> None:
        previous = self._stored_navigator
        self._stored_navigator = navigator
        if previous is not None:
            previous.close()
            previous.deleteLater()

    def _track_index(self, index: SearchIndex, *, label: str | None = None) -> None:
        token = id(index)
        if token in self._tracked_indexes:
            return

        tabs = self._window.tabs
        tab_title = tabs.tabText(tabs.currentIndex()).strip()
        resolved_label = label or "Indeks wyszukiwania"
        if label is None and tab_title:
            resolved_label = f"{resolved_label} — {tab_title}"
        key = f"search-index:{token}"
        self._tracked_indexes[token] = (key, resolved_label)

        index.progress_changed.connect(
            lambda current, total, source=index: self._index_progress(
                source,
                current,
                total,
            )
        )
        index.ready_changed.connect(
            lambda ready, source=index: self._index_ready(source, ready)
        )
        failed_signal = getattr(index, "failed", None)
        if failed_signal is not None:
            failed_signal.connect(
                lambda error, source=index: self._index_failed(source, error)
            )

        if not index.is_ready:
            self._begin_progress(key, resolved_label, index)

    def _begin_progress(self, key: str, label: str, index: SearchIndex) -> None:
        current, total = index.progress
        self._window.project_preparation.begin_task(
            key,
            label,
            current=current,
            total=total,
            stage_index=1,
            stage_count=4,
            priority=10,
        )

    def _index_progress(self, index: SearchIndex, current: int, total: int) -> None:
        tracked = self._tracked_indexes.get(id(index))
        if tracked is None:
            return
        key, label = tracked
        preparation = self._window.project_preparation
        if index.is_ready:
            preparation.complete_task(key)
            return
        preparation.update_task(key, current=current, total=total, label=label)

    def _index_ready(self, index: SearchIndex, ready: bool) -> None:
        tracked = self._tracked_indexes.get(id(index))
        if tracked is None:
            return
        key, label = tracked
        if ready:
            self._window.project_preparation.complete_task(key)
            return
        self._begin_progress(key, label, index)

    def _index_failed(self, index: SearchIndex, error: str) -> None:
        tracked = self._tracked_indexes.get(id(index))
        if tracked is None:
            return
        key, _label = tracked
        self._window.project_preparation.fail_task(key, error)
        self._window.append_output(f"Błąd trwałego indeksu wyszukiwania: {error}")

    def _active_search_context(self) -> tuple[QTableView | None, Path | None]:
        current = self._window.tabs.currentWidget()
        table = self._active_search_table(current)
        if current is None or table is None:
            return table, None
        frame_table = getattr(current, "frame_table", None)
        path = getattr(current, "path", None)
        if frame_table is table and path is not None:
            return table, Path(path)
        return table, None

    @staticmethod
    def _active_search_table(current: QWidget | None) -> QTableView | None:
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
