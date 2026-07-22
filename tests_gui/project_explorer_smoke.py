from __future__ import annotations

import gc
import os
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QPushButton

from app.project import CrtProject
from gui.application_container import ApplicationContainer


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTProjectExplorerSmoke")

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(
            f"{temporary}/project",
            name="Projekt testowy",
        )

        window = ApplicationContainer().create_main_window()
        window._set_project(project)
        app.processEvents()

        explorer = window.explorer

        # projectTree exists
        assert explorer.tree is not None
        assert explorer.tree.objectName() == "projectTree"

        # Removed widgets must not exist
        assert explorer.findChild(QFrame, "projectExplorerHeader") is None
        assert explorer.findChild(QPushButton, "addStudyAreaButton") is None
        assert explorer.findChild(QPushButton, "importProjectLogButton") is None

        # Removed attributes must not be present
        assert not hasattr(explorer, "project_name")
        assert not hasattr(explorer, "project_path")
        assert not hasattr(explorer, "add_area_button")
        assert not hasattr(explorer, "import_button")

        # Removed signals must not be present
        assert not hasattr(explorer, "import_requested")
        assert not hasattr(explorer, "add_area_requested")

        # Root tree node carries the project name and path as tooltip
        root = explorer.model.item(0, 0)
        assert root is not None
        assert root.text() == "Projekt testowy"
        assert str(project.root) in root.toolTip()

        # After renaming via update_manifest + refresh the root node updates
        project.update_manifest(name="Projekt zmieniony")
        explorer.refresh()
        app.processEvents()

        root = explorer.model.item(0, 0)
        assert root is not None
        assert root.text() == "Projekt zmieniony"

        window._close_project_tabs()
        window.close()
        window.deleteLater()
        app.sendPostedEvents()
        app.processEvents()

        root = None
        explorer = None
        window = None
        project = None
        gc.collect()

    print("Project explorer smoke: OK")


if __name__ == "__main__":
    main()
