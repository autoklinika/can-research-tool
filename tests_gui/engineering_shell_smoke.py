from __future__ import annotations

import gc
import time
from tempfile import TemporaryDirectory

from PySide6.QtCore import QEvent, QSettings, QThreadPool, Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QApplication, QTableView, QTableWidget, QToolButton

from app.project import CrtProject
from gui.application_container import ApplicationContainer
import gui.async_dbc_manager as async_dbc_manager
from gui.async_dbc_manager import AsyncDbcManagerWidget
from gui.engineering_shell import EngineeringShellMainWindow
from gui.engineering_theme import apply_engineering_theme
from gui.logical_message_model import LogicalMessageTableModel
from gui.project_explorer import ROLE_NODE_TYPE


def _find_node(item: QStandardItem, node_type: str) -> QStandardItem | None:
    if item.data(ROLE_NODE_TYPE) == node_type:
        return item
    for row in range(item.rowCount()):
        child = item.child(row)
        if child is None:
            continue
        found = _find_node(child, node_type)
        if found is not None:
            return found
    return None


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTEngineeringShellSmoke")
    QSettings().clear()
    apply_engineering_theme(app)

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(
            f"{temporary}/project",
            name="Engineering shell",
            default_bitrate=250_000,
            default_receive_mode="bench",
        )

        window = ApplicationContainer().create_main_window()
        assert isinstance(window, EngineeringShellMainWindow)
        window._set_project(project)
        window.show()
        app.processEvents()

        assert window.objectName() == "engineeringMainWindow"
        assert window.primary_toolbar.objectName() == "primaryToolBar"
        assert window.activity_bar.objectName() == "activityBar"
        assert window.activity_bar.isHidden()
        assert window.tabs.objectName() == "workspaceTabs"

        menu_names = [action.text() for action in window.menuBar().actions()]
        assert menu_names == ["Plik", "Widok", "Capture", "Analiza", "Narzędzia"]

        assert window.toggle_explorer_action.shortcut().toString() == "Ctrl+B"
        assert window.toggle_inspector_action.shortcut().toString() == "Ctrl+Shift+I"
        assert window.toggle_output_action.shortcut().toString() == ""
        assert window.toggle_output_action.isVisible() is False
        assert window.toggle_output_action.isEnabled() is False
        assert window.output_dock.isHidden()
        assert (
            window.dockWidgetArea(window.output_dock)
            == Qt.DockWidgetArea.NoDockWidgetArea
        )

        # Inspector is opt-in: opening a project and resetting the workspace keep it hidden.
        assert window.inspector_dock.isHidden()
        assert not window.toggle_inspector_action.isChecked()

        # Project uses a custom title bar with native-style float, collapse and close buttons.
        title_bar = window.explorer_dock.titleBarWidget()
        assert title_bar is not None
        assert title_bar.objectName() == "projectDockTitleBar"
        float_button = title_bar.findChild(QToolButton, "projectDockFloatButton")
        collapse_button = title_bar.findChild(QToolButton, "projectDockCollapseButton")
        close_button = title_bar.findChild(QToolButton, "projectDockCloseButton")
        assert float_button is not None
        assert collapse_button is not None
        assert close_button is not None

        assert window.explorer.tree.isHeaderHidden()
        assert window.explorer.project_name.text() == "Engineering shell"
        root = window.explorer.model.item(0, 0)
        assert root is not None
        assert _find_node(root, "overview") is None
        assert _find_node(root, "live") is None
        assert _find_node(root, "filters") is not None

        assert window.transport_status.text() == "CAN: 250 kbit/s"
        assert window.mode_status.text() == "TRYB: BENCH"
        assert "Engineering shell" in window.project_context_label.text()
        assert window.capture_indicator.property("state") == "stopped"

        overview = window.navigator.widget("project-overview")
        assert overview is not None
        recent = overview.findChild(QTableWidget, "recentSessionsTable")
        assert recent is not None
        assert recent.columnCount() == 5

        # Logical-message details belong to a dedicated window, not a native tooltip.
        logical_table = QTableView(window)
        logical_table.setModel(LogicalMessageTableModel(capacity=1, parent=logical_table))
        tooltip_event = QEvent(QEvent.Type.ToolTip)
        assert window._table_tooltip_suppressor.eventFilter(
            logical_table.viewport(),
            tooltip_event,
        )

        # Force a slow metadata read. Opening the workspace must still return
        # immediately because the read belongs to a QThreadPool worker.
        original_list_project_dbc = async_dbc_manager.list_project_dbc
        decoder_workspace = None

        def slow_list_project_dbc(_project):
            time.sleep(0.5)
            return []

        async_dbc_manager.list_project_dbc = slow_list_project_dbc
        try:
            started = time.monotonic()
            window._open_decoders()
            elapsed = time.monotonic() - started
            assert elapsed < 0.2
            decoder_workspace = window.navigator.widget("decoders")
            assert isinstance(decoder_workspace, AsyncDbcManagerWidget)

            deadline = time.monotonic() + 5.0
            while decoder_workspace.manager is None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
            assert decoder_workspace.manager is not None
        finally:
            async_dbc_manager.list_project_dbc = original_list_project_dbc

        # Menu and Ctrl+Shift+I show the opt-in Inspector; title-bar X hides it cleanly.
        window.toggle_inspector_action.trigger()
        app.processEvents()
        assert not window.inspector_dock.isHidden()
        assert window.toggle_inspector_action.isChecked()
        window.inspector_dock.close()
        app.processEvents()
        assert window.inspector_dock.isHidden()
        assert not window.toggle_inspector_action.isChecked()
        window.toggle_inspector_action.trigger()
        app.processEvents()
        assert not window.inspector_dock.isHidden()

        # The arrow hides Project immediately; Ctrl+B restores the unchanged dock.
        normal_width = window.explorer_dock.width()
        normal_minimum_width = window.explorer_dock.minimumWidth()
        normal_maximum_width = window.explorer_dock.maximumWidth()
        assert not window.explorer_dock.isHidden()
        collapse_button.click()
        app.processEvents()
        assert window.explorer_dock.isHidden()
        assert not window.toggle_explorer_action.isChecked()
        assert window.explorer_dock.minimumWidth() == normal_minimum_width
        assert window.explorer_dock.maximumWidth() == normal_maximum_width

        window.toggle_explorer_action.trigger()
        app.processEvents()
        assert not window.explorer_dock.isHidden()
        assert window.toggle_explorer_action.isChecked()
        assert window.explorer_dock.minimumWidth() == normal_minimum_width
        assert window.explorer_dock.maximumWidth() == normal_maximum_width
        assert window.explorer_dock.width() > 0
        assert normal_width > 0

        window._reset_workspace_layout()
        assert window.output_dock.isHidden()
        assert (
            window.dockWidgetArea(window.output_dock)
            == Qt.DockWidgetArea.NoDockWidgetArea
        )
        assert not window.explorer_dock.isHidden()
        assert window.inspector_dock.isHidden()
        assert not window.toggle_inspector_action.isChecked()
        assert window.activity_bar.isHidden()

        window._close_project_tabs()
        window.close()
        window.deleteLater()
        assert QThreadPool.globalInstance().waitForDone(5_000)
        app.sendPostedEvents()
        app.processEvents()
        decoder_workspace = None
        overview = None
        recent = None
        logical_table = None
        title_bar = None
        float_button = None
        collapse_button = None
        close_button = None
        window = None
        project = None
        gc.collect()

    QSettings().clear()


if __name__ == "__main__":
    main()
