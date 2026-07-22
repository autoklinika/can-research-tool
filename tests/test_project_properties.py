from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QLabel

from app.project import CrtProject
from gui.application_container import ApplicationContainer


def test_project_manifest_edit_preserves_project_identity_and_data(tmp_path: Path) -> None:
    root = tmp_path / "project"
    project = CrtProject.create(
        root,
        name="DAF MX13",
        description="Initial description",
        default_bitrate=250_000,
        default_receive_mode="bench",
    )
    area = project.add_study_area("EGR")
    original_id = project.manifest.id
    original_created_at = project.manifest.created_at_utc
    database_path = project.database_path

    project.update_manifest(
        name="DAF MX13 — stanowisko 2",
        description="Updated description",
        default_bitrate=500_000,
        default_receive_mode="listen-only",
    )

    reopened = CrtProject.open(root)
    assert reopened.root == root.resolve()
    assert reopened.database_path == database_path
    assert reopened.database_path.is_file()
    assert reopened.manifest.id == original_id
    assert reopened.manifest.created_at_utc == original_created_at
    assert reopened.manifest.name == "DAF MX13 — stanowisko 2"
    assert reopened.manifest.description == "Updated description"
    assert reopened.manifest.default_bitrate == 500_000
    assert reopened.manifest.default_receive_mode == "listen-only"
    assert [item.id for item in reopened.list_study_areas()] == [area.id]


def test_project_properties_shell_updates_visible_project_context(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTProjectPropertiesTest")
    settings = QSettings()
    settings.clear()

    window = ApplicationContainer().create_main_window()
    project = CrtProject.create(
        tmp_path / "project",
        name="Initial project",
        description="Initial description",
        default_bitrate=250_000,
        default_receive_mode="bench",
    )
    original_root = project.root
    original_database_path = project.database_path
    original_id = project.manifest.id

    window._set_project(project)
    action = window.findChild(QAction, "projectPropertiesAction")
    assert action is not None
    assert action.isEnabled()

    dialog = window.services.create_project_properties_dialog(window, project)
    dialog.name_edit.setText("Edited project")
    dialog.description_edit.setPlainText("Edited description")
    dialog.bitrate_combo.setCurrentIndex(dialog.bitrate_combo.findData(500_000))
    dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("listen-only"))

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
    window.close()
    app.processEvents()
    settings.clear()
