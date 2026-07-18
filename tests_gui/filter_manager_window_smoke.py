from __future__ import annotations

from tempfile import TemporaryDirectory

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.project import CrtProject
from gui.application_container import ApplicationContainer
from gui.filter_manager_window import FilterManagerWindow, WindowedFilterMainWindow


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTFilterWindowSmoke")
    QSettings().clear()

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(f"{temporary}/project", name="Filter window")
        window = ApplicationContainer().create_main_window()
        assert isinstance(window, WindowedFilterMainWindow)
        window._set_project(project)

        assert window.filters_action.shortcut().toString() == "Ctrl+D"
        actions = window.activity_bar.actions()
        assert actions.index(window.filters_action) < actions.index(window.settings_action)

        tab_count = window.tabs.count()
        window._open_filters()
        app.processEvents()

        filter_window = window._filter_window
        assert isinstance(filter_window, FilterManagerWindow)
        assert filter_window.isWindow()
        assert filter_window.isVisible()
        assert window.tabs.count() == tab_count
        assert "global-filters" not in window.navigator.widgets
        assert window.tabs.indexOf(filter_window.manager) == -1

        # Reopening by the left action/shortcut path activates the same top-level window.
        window.filters_action.trigger()
        app.processEvents()
        assert window._filter_window is filter_window

        filter_window.close()
        app.processEvents()
        assert not filter_window.isVisible()
        window.filters_action.trigger()
        app.processEvents()
        assert window._filter_window is filter_window
        assert filter_window.isVisible()

        window.close()
        app.processEvents()

    QSettings().clear()


if __name__ == "__main__":
    main()
