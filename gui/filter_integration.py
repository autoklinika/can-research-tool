from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMessageBox

from .filter_manager import FilterManagerWidget
from .main_window import MainWindow


_installed = False
_original_init = MainWindow.__init__


def install_filter_integration() -> None:
    """Attach the filter workspace to the existing CRT MainWindow.

    Kept in a small adapter so the feature can be developed without rewriting the
    mature main-window module. Once the activity registry becomes data-driven this
    adapter can be replaced by a normal workspace registration.
    """

    global _installed
    if _installed:
        return
    _installed = True

    def integrated_init(self: MainWindow) -> None:
        _original_init(self)
        self.filters_action = QAction("Filtry", self)
        self.filters_action.setObjectName("globalFiltersAction")
        self.filters_action.triggered.connect(lambda: _open_filters(self))
        actions = self.activity_bar.actions()
        insert_before = self.settings_action if self.settings_action in actions else None
        if insert_before is None:
            self.activity_bar.addAction(self.filters_action)
        else:
            self.activity_bar.insertAction(insert_before, self.filters_action)
        view_menu = next(
            (menu for menu in self.menuBar().findChildren(type(self.menuBar().addMenu("__probe__"))) if menu.title() == "Widok"),
            None,
        )
        probe = next((menu for menu in self.menuBar().actions() if menu.text() == "__probe__"), None)
        if probe is not None:
            self.menuBar().removeAction(probe)
        if view_menu is not None:
            view_menu.addAction(self.filters_action)

    MainWindow.__init__ = integrated_init


def _open_filters(window: MainWindow) -> None:
    if window.project is None:
        QMessageBox.information(window, "CRT", "Najpierw otwórz lub utwórz projekt.")
        return
    key = "global-filters"
    if window._activate_tab(key):
        return
    widget = FilterManagerWidget(window.project)
    widget.output_message.connect(window._append_output)
    widget.changed.connect(window.explorer.refresh)
    window._add_tab(key, widget, "Filtry")
