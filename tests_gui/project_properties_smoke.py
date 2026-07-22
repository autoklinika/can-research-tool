from __future__ import annotations

import gc
import os
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QLabel

from app.project import CrtProject
from gui.application_container import ApplicationContainer


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTProjectPropertiesSmoke")
    settings = QSettings()
    settings.clear()

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(
            f"{temporary}/project",
            name="Initial project",
            description="Initial description",
            default_bitrate=250_000,
            default_receive_mode="bench",
        )
        original_root = project.root
        original_database_path = project.database_path
        original_id = project.manifest.id

        window = ApplicationContainer().create_main_window()
        window._set_project(project)
        window.show()
        app.processEvents()

        action = window.findChild(QAction, "projectPropertiesAction")
        assert action is not None
        assert action.isEnabled()

        dialog = window.services.create_project_properties_dialog(window, project)
        dialog.name_edit.setText("Edited project")
        dialog.description_edit.setPlainText("Edited description")
        dialog.bitrate_combo.setCurrentIndex(
            dialog.bitrate_combo.findData(500_000)
        )
        dialog.mode_combo.setCurrentIndex(
            dialog.mode_combo.findData("listen-only")
        )

        window._apply_project_properties_from_dialog(dialog)
        app.processEvents()

        assert project.root == original_root
        assert project.database_path == original_database_path
        assert project.manifest.id == original_id
        assert project.manifest.name == "Edited project"
        assert project.manifest.description == "Edited description"
        assert project.manifest.default_bitrate == 500_000
        assert project.manifest.default_receive_mode == "listen-only"
        assert window.windowTitle() == "Edited project — CAN Research Tool"
        assert "Edited project" in window.project_status.text()
        assert "500 kbit/s" in window.project_context_label.text()
        assert "LISTEN-ONLY" in window.project_context_label.text()

        overview = window.navigator.widget("project-overview")
        assert overview is not None
        overview_title = overview.findChild(QLabel, "projectOverviewTitle")
        assert overview_title is not None
        assert overview_title.text() == "Edited project"

        reopened = CrtProject.open(original_root)
        assert reopened.manifest.name == "Edited project"
        assert reopened.database_path == original_database_path

        dialog.close()
        window._close_project_tabs()
        window.close()
        window.deleteLater()
        assert QThreadPool.globalInstance().waitForDone(5_000)
        app.sendPostedEvents()
        app.processEvents()

        overview_title = None
        overview = None
        action = None
        dialog = None
        window = None
        reopened = None
        project = None
        gc.collect()

    settings.clear()
    print("Project properties GUI smoke: OK")


if __name__ == "__main__":
    main()
