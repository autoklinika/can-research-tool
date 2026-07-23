from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from app.project import CrtProject
from app.project_catalog import load_project_profile

from .project_dialog import NewProjectDialog


class ProjectPropertiesDialog(NewProjectDialog):
    """Edit the manifest and complete portable profile of an existing CRT project."""

    def __init__(
        self,
        project: CrtProject,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.setObjectName("projectPropertiesDialog")
        self.setWindowTitle("Właściwości projektu CRT")
        self.resize(760, 650)

        profile = load_project_profile(project.root)

        self.location_edit.setText(str(project.root))
        self.location_edit.setReadOnly(True)
        self.location_edit.setToolTip(
            "Folder projektu jest stały. Zmiana lokalizacji odbywa się w katalogu Projekty CRT."
        )
        self.location_browse_button.hide()

        self.name_edit.setText(project.manifest.name)
        self.description_edit.setPlainText(project.manifest.description)
        self._select_or_add_bitrate(
            self.bitrate_combo,
            project.manifest.default_bitrate,
        )
        self._select_combo_data(
            self.mode_combo,
            str(project.manifest.default_receive_mode),
        )

        self.vehicle_brand_edit.setText(profile.vehicle_brand)
        self.vehicle_model_edit.setText(profile.vehicle_model)
        self.production_year_spin.setValue(profile.production_year or 0)
        self._select_combo_data(self.vehicle_type_combo, profile.vehicle_type)
        self.vin_edit.setText(profile.vin)
        self.registration_edit.setText(profile.registration_number)
        self.customer_edit.setText(profile.customer_name)
        self.vehicle_notes_edit.setPlainText(profile.vehicle_notes)

        self.ecu_manufacturer_edit.setText(profile.ecu_manufacturer)
        self.ecu_type_edit.setText(profile.ecu_type)
        self.ecu_function_edit.setText(profile.ecu_function)
        self.part_number_edit.setText(profile.part_number)
        self.secondary_part_number_edit.setText(profile.secondary_part_number)
        self.hardware_number_edit.setText(profile.hardware_number)
        self.hardware_version_edit.setText(profile.hardware_version)
        self.software_number_edit.setText(profile.software_number)
        self.software_version_edit.setText(profile.software_version)
        self.calibration_edit.setText(profile.calibration_number)
        self.bootloader_edit.setText(profile.bootloader_version)
        self.ecu_serial_edit.setText(profile.ecu_serial_number)
        self.processor_edit.setText(profile.processor_type)
        self._select_combo_data(self.ecu_status_combo, profile.ecu_status)
        self.fault_description_edit.setPlainText(profile.fault_description)
        self.tags_edit.setText(", ".join(profile.tags))

    def _validate(self) -> None:
        if not self.project_name():
            QMessageBox.warning(self, "CRT", "Podaj nazwę projektu.")
            self.name_edit.setFocus()
            return
        try:
            self.profile()
        except ValueError as exc:
            QMessageBox.warning(self, "CRT", str(exc))
            return
        self.accept()

    @staticmethod
    def _select_or_add_bitrate(combo, value: object) -> None:
        bitrate = int(value)
        index = combo.findData(bitrate)
        if index < 0:
            combo.addItem(
                f"{bitrate:,}".replace(",", " "),
                bitrate,
            )
            index = combo.findData(bitrate)
        combo.setCurrentIndex(index)

    @staticmethod
    def _select_combo_data(combo, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
