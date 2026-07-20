from __future__ import annotations

from tempfile import TemporaryDirectory

from PySide6.QtCore import QSettings
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QApplication, QTableWidget

from app.project import CrtProject
from gui.application_container import ApplicationContainer
from gui.engineering_shell import EngineeringShellMainWindow
from gui.engineering_theme import apply_engineering_theme
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
        assert window.activity_bar.maximumWidth() == 46
        assert window.tabs.objectName() == "workspaceTabs"

        menu_names = [action.text() for action in window.menuBar().actions()]
        assert menu_names == ["Plik", "Widok", "Capture", "Analiza", "Narzędzia"]

        assert window.toggle_explorer_action.shortcut().toString() == "Ctrl+B"
        assert window.toggle_inspector_action.shortcut().toString() == "Ctrl+Shift+I"
        assert window.toggle_output_action.shortcut().toString() == "Ctrl+J"

        assert window.explorer.tree.isHeaderHidden()
        assert window.explorer.project_name.text() == "Engineering shell"
        root = window.explorer.model.item(0, 0)
        assert root is not None
        assert _find_node(root, "overview") is not None
        assert _find_node(root, "live") is not None
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

        assert not window.output_dock.isHidden()
        window.toggle_output_action.trigger()
        app.processEvents()
        assert window.output_dock.isHidden()
        window.toggle_output_action.trigger()
        app.processEvents()
        assert not window.output_dock.isHidden()

        # Regression: closing the dock with its title-bar X must not leave the
        # checkable action in a stale state. Menu and Ctrl+Shift+I share this action.
        assert not window.inspector_dock.isHidden()
        window.inspector_dock.close()
        app.processEvents()
        assert window.inspector_dock.isHidden()
        window.toggle_inspector_action.trigger()
        app.processEvents()
        assert not window.inspector_dock.isHidden()
        assert window.toggle_inspector_action.isChecked()

        window._reset_workspace_layout()
        assert not window.output_dock.isHidden()
        assert not window.explorer_dock.isHidden()
        assert not window.inspector_dock.isHidden()

        window.close()
        app.processEvents()

    QSettings().clear()


if __name__ == "__main__":
    main()
