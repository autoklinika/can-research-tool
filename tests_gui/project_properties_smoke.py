from __future__ import annotations

import gc
import os
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QThreadPool, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QMessageBox, QWidget

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

        fake_live = QWidget(window)
        fake_live.bitrate_combo = QComboBox(fake_live)
        for bitrate in (125_000, 250_000, 500_000, 1_000_000):
            fake_live.bitrate_combo.addItem(str(bitrate), bitrate)
        fake_live.bitrate_combo.setCurrentIndex(
            fake_live.bitrate_combo.findData(250_000)
        )
        fake_live.mode_combo = QComboBox(fake_live)
        fake_live.mode_combo.addItem("BENCH", "bench")
        fake_live.mode_combo.addItem("LISTEN ONLY", "listen-only")
        fake_live.mode_combo.setCurrentIndex(fake_live.mode_combo.findData("bench"))
        window.navigator.widgets["live-capture"] = fake_live

        dialog = window.services.create_project_properties_dialog(window, project)
        dialog.name_edit.setText("Edited project")
        dialog.description_edit.setPlainText("Edited description")
        dialog.bitrate_combo.setCurrentIndex(
            dialog.bitrate_combo.findData(500_000)
        )
        dialog.mode_combo.setCurrentIndex(
            dialog.mode_combo.findData("listen-only")
        )

        original_factory = window.services.create_project_properties_dialog
        window.services.create_project_properties_dialog = (
            lambda _parent, _project: dialog
        )
        try:
            QTimer.singleShot(0, dialog.accept)
            action.trigger()
        finally:
            window.services.create_project_properties_dialog = original_factory
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
        assert fake_live.bitrate_combo.currentData() == 500_000
        assert fake_live.mode_combo.currentData() == "listen-only"

        explorer_root = window.explorer.model.item(0, 0)
        assert explorer_root is not None
        assert explorer_root.text() == "Edited project"
        assert explorer_root.toolTip() == str(original_root)

        overview = window.navigator.widget("project-overview")
        assert overview is not None
        overview_title = overview.findChild(QLabel, "projectOverviewTitle")
        assert overview_title is not None
        assert overview_title.text() == "Edited project"

        project.update_manifest(default_bitrate=666_000)
        custom_dialog = original_factory(window, project)
        assert custom_dialog.bitrate_combo.currentData() == 666_000
        custom_dialog.description_edit.setPlainText("Custom bitrate description")
        window.services.create_project_properties_dialog = (
            lambda _parent, _project: custom_dialog
        )
        try:
            QTimer.singleShot(0, custom_dialog.accept)
            action.trigger()
        finally:
            window.services.create_project_properties_dialog = original_factory
        app.processEvents()

        assert project.manifest.default_bitrate == 666_000
        assert project.manifest.description == "Custom bitrate description"
        assert fake_live.bitrate_combo.findData(666_000) >= 0
        assert fake_live.bitrate_combo.currentData() == 666_000
        assert "666 kbit/s" in window.project_context_label.text()

        saved_manifest = project.manifest
        failing_dialog = original_factory(window, project)
        failing_dialog.name_edit.setText("Unsaved project")
        original_write_manifest = project._write_manifest
        original_critical = QMessageBox.critical

        def fail_write_manifest() -> None:
            raise OSError("simulated manifest write failure")

        project._write_manifest = fail_write_manifest
        QMessageBox.critical = lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok
        try:
            window._apply_project_properties_from_dialog(failing_dialog)
        finally:
            project._write_manifest = original_write_manifest
            QMessageBox.critical = original_critical

        assert project.manifest == saved_manifest
        assert window.windowTitle() == "Edited project — CAN Research Tool"
        assert window.explorer.model.item(0, 0).text() == "Edited project"

        reopened = CrtProject.open(original_root)
        assert reopened.manifest.name == "Edited project"
        assert reopened.manifest.default_bitrate == 666_000
        assert reopened.database_path == original_database_path

        failing_dialog.close()
        custom_dialog.close()
        dialog.close()
        window.navigator.widgets.pop("live-capture", None)
        fake_live.deleteLater()
        window._close_project_tabs()
        window.close()
        window.deleteLater()
        assert QThreadPool.globalInstance().waitForDone(5_000)
        app.sendPostedEvents()
        app.processEvents()

        saved_manifest = None
        failing_dialog = None
        custom_dialog = None
        fake_live = None
        explorer_root = None
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
