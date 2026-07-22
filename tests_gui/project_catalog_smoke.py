from __future__ import annotations

import gc
import os
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtWidgets import QApplication

from app.project_catalog import ProjectCatalog, load_project_profile
from gui.application_container import ApplicationContainer
from gui.project_catalog_dialog import ProjectCatalogDialog


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTProjectCatalogSmoke")
    settings = QSettings()
    settings.clear()

    with TemporaryDirectory() as temporary:
        os.environ["CRT_APP_DATA_DIR"] = f"{temporary}/app-data"
        window = ApplicationContainer().create_main_window()
        dialog = window.services.create_project_dialog(window)
        dialog.location_edit.setText(f"{temporary}/projects")
        dialog.vehicle_brand_edit.setText("MAN")
        dialog.vehicle_model_edit.setText("TGX")
        dialog.production_year_spin.setValue(2021)
        dialog.vehicle_type_combo.setCurrentIndex(
            dialog.vehicle_type_combo.findData("truck")
        )
        dialog.vin_edit.setText("WMA06XZZ9MP123456")
        dialog.customer_edit.setText("Autoklinika")
        dialog.ecu_manufacturer_edit.setText("Bosch")
        dialog.ecu_type_edit.setText("MD1CE101")
        dialog.ecu_function_edit.setText("engine")
        dialog.part_number_edit.setText("0281039999")
        dialog.hardware_number_edit.setText("H21")
        dialog.software_number_edit.setText("1039S99999")
        dialog.ecu_status_combo.setCurrentIndex(
            dialog.ecu_status_combo.findData("after-repair")
        )
        dialog.tags_edit.setText("Euro 6, EGR")
        dialog.description_edit.setPlainText("EGR bench investigation")

        generated_name = dialog.project_name()
        assert generated_name == "MAN — TGX — 2021 — MD1CE101 — 0281039999"
        window._create_project_from_dialog(dialog)
        app.processEvents()

        project = window.project
        assert project is not None
        assert project.root.name == "MAN___TGX___2021___MD1CE101___0281039999"
        profile = load_project_profile(project.root)
        assert profile.vehicle_brand == "MAN"
        assert profile.vehicle_model == "TGX"
        assert profile.production_year == 2021
        assert profile.ecu_type == "MD1CE101"
        assert profile.part_number == "0281039999"
        assert profile.tags == ("Euro 6", "EGR")

        catalog = ProjectCatalog(f"{temporary}/app-data/projects.sqlite")
        matches = catalog.list_projects(query="man md1 2021 egr")
        assert len(matches) == 1
        assert matches[0].project_id == project.manifest.id
        assert matches[0].last_opened_at_utc

        picker = ProjectCatalogDialog(catalog, window)
        assert picker.windowTitle() == "Projekty CRT"
        assert picker.table.rowCount() == 1
        assert picker.open_button.isEnabled()
        assert picker.selected_project_path() == str(project.root)

        picker.search_edit.setText("bosch h21")
        app.processEvents()
        assert picker.table.rowCount() == 1
        picker.search_edit.setText("scania s8")
        app.processEvents()
        assert picker.table.rowCount() == 0
        assert not picker.open_button.isEnabled()

        picker.search_edit.clear()
        picker.time_tabs.setCurrentIndex(4)
        app.processEvents()
        assert picker.table.rowCount() == 1

        project.manifest_path.rename(project.manifest_path.with_suffix(".missing"))
        picker._refresh_catalog()
        app.processEvents()
        assert picker.table.rowCount() == 1
        assert picker.selected_project() is not None
        assert not picker.selected_project().available
        assert not picker.open_button.isEnabled()
        project.manifest_path.with_suffix(".missing").rename(project.manifest_path)

        picker.close()
        dialog.close()
        window._close_project_tabs()
        window.close()
        window.deleteLater()
        assert QThreadPool.globalInstance().waitForDone(5_000)
        app.sendPostedEvents()
        app.processEvents()

        matches = None
        catalog = None
        profile = None
        project = None
        picker = None
        dialog = None
        window = None
        gc.collect()

    settings.clear()
    os.environ.pop("CRT_APP_DATA_DIR", None)
    print("Project catalog GUI smoke: OK")


if __name__ == "__main__":
    main()
