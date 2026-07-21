from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableView

from .fixed_marker_menu_shell import FixedMarkerMenuMainWindow
from .log_search_window import LogSearchWindow


class SearchEnabledMainWindow(FixedMarkerMenuMainWindow):
    """Engineering shell with an independent, non-modal log search window."""

    def __init__(self, services) -> None:
        self._log_search_window: LogSearchWindow | None = None
        super().__init__(services)

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
        window.set_target_table(self._active_search_table())
        if window.isMinimized():
            window.showNormal()
        else:
            window.show()
        window.raise_()
        window.activateWindow()
        window.query_edit.selectAll()
        window.query_edit.setFocus(Qt.ShortcutFocusReason)

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

    def _close_tab(self, index: int) -> None:
        current = self.tabs.widget(index)
        target = self._log_search_window._target_table if self._log_search_window else None
        if target is not None and current is not None and current.isAncestorOf(target):
            self._log_search_window.set_target_table(None)
        super()._close_tab(index)
