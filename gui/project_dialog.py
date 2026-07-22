from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.project_catalog import ProjectProfile


class NewProjectDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nowy projekt CRT")
        self.resize(760, 650)

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_vehicle_tab(), "Pojazd / maszyna")
        tabs.addTab(self._build_ecu_tab(), "Sterownik ECU")
        tabs.addTab(self._build_project_tab(), "Projekt")
        root.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_vehicle_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.vehicle_brand_edit = QLineEdit()
        self.vehicle_brand_edit.setPlaceholderText("np. MAN")
        form.addRow("Marka:", self.vehicle_brand_edit)

        self.vehicle_model_edit = QLineEdit()
        self.vehicle_model_edit.setPlaceholderText("np. TGX")
        form.addRow("Model:", self.vehicle_model_edit)

        self.production_year_spin = QSpinBox()
        self.production_year_spin.setRange(0, 2200)
        self.production_year_spin.setSpecialValueText("Nie podano")
        self.production_year_spin.setValue(0)
        form.addRow("Rok produkcji:", self.production_year_spin)

        self.vehicle_type_combo = QComboBox()
        self.vehicle_type_combo.addItem("Nie określono", "")
        self.vehicle_type_combo.addItem("Samochód ciężarowy", "truck")
        self.vehicle_type_combo.addItem("Maszyna rolnicza", "agricultural")
        self.vehicle_type_combo.addItem("Maszyna budowlana", "construction")
        self.vehicle_type_combo.addItem("Maszyna przemysłowa", "industrial")
        self.vehicle_type_combo.addItem("Samochód osobowy / dostawczy", "passenger")
        self.vehicle_type_combo.addItem("Inny", "other")
        form.addRow("Typ pojazdu:", self.vehicle_type_combo)

        self.vin_edit = QLineEdit()
        self.vin_edit.setPlaceholderText("VIN lub numer seryjny maszyny")
        form.addRow("VIN / numer seryjny:", self.vin_edit)

        self.registration_edit = QLineEdit()
        form.addRow("Numer rejestracyjny:", self.registration_edit)

        self.customer_edit = QLineEdit()
        form.addRow("Klient / właściciel:", self.customer_edit)

        self.vehicle_notes_edit = QTextEdit()
        self.vehicle_notes_edit.setPlaceholderText("Dodatkowe informacje o pojeździe lub maszynie")
        self.vehicle_notes_edit.setMaximumHeight(120)
        form.addRow("Notatka:", self.vehicle_notes_edit)
        return page

    def _build_ecu_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.ecu_manufacturer_edit = QLineEdit()
        self.ecu_manufacturer_edit.setPlaceholderText("np. Bosch, Continental, ZF")
        form.addRow("Producent ECU:", self.ecu_manufacturer_edit)

        self.ecu_type_edit = QLineEdit()
        self.ecu_type_edit.setPlaceholderText("np. MD1CE101, MCM, ETC3")
        form.addRow("Typ / nazwa ECU:", self.ecu_type_edit)

        self.ecu_function_edit = QLineEdit()
        self.ecu_function_edit.setPlaceholderText("np. silnik, skrzynia, SCR, EGR")
        form.addRow("Funkcja ECU:", self.ecu_function_edit)

        self.part_number_edit = QLineEdit()
        form.addRow("Numer części:", self.part_number_edit)

        self.secondary_part_number_edit = QLineEdit()
        form.addRow("Dodatkowy numer części:", self.secondary_part_number_edit)

        self.hardware_number_edit = QLineEdit()
        form.addRow("Numer HW:", self.hardware_number_edit)

        self.hardware_version_edit = QLineEdit()
        form.addRow("Wersja HW:", self.hardware_version_edit)

        self.software_number_edit = QLineEdit()
        form.addRow("Numer SW:", self.software_number_edit)

        self.software_version_edit = QLineEdit()
        form.addRow("Wersja SW:", self.software_version_edit)

        self.calibration_edit = QLineEdit()
        form.addRow("Kalibracja:", self.calibration_edit)

        self.bootloader_edit = QLineEdit()
        form.addRow("Bootloader:", self.bootloader_edit)

        self.ecu_serial_edit = QLineEdit()
        form.addRow("Numer seryjny ECU:", self.ecu_serial_edit)

        self.processor_edit = QLineEdit()
        form.addRow("Procesor:", self.processor_edit)

        self.ecu_status_combo = QComboBox()
        self.ecu_status_combo.addItem("Nie określono", "")
        self.ecu_status_combo.addItem("Przed naprawą", "before-repair")
        self.ecu_status_combo.addItem("Po naprawie", "after-repair")
        self.ecu_status_combo.addItem("Sprawny", "working")
        self.ecu_status_combo.addItem("Uszkodzony", "faulty")
        self.ecu_status_combo.addItem("Badawczy", "research")
        form.addRow("Status ECU:", self.ecu_status_combo)

        self.fault_description_edit = QTextEdit()
        self.fault_description_edit.setPlaceholderText("Opis usterki, wykonanej naprawy lub celu badań")
        self.fault_description_edit.setMaximumHeight(100)
        form.addRow("Usterka / cel badań:", self.fault_description_edit)
        return page

    def _build_project_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        location_row = QHBoxLayout()
        self.location_edit = QLineEdit(str((Path.home() / "CRT_Projects").resolve()))
        browse = QPushButton("Wybierz…")
        browse.clicked.connect(self._browse)
        location_row.addWidget(self.location_edit, 1)
        location_row.addWidget(browse)
        location = QWidget()
        location.setLayout(location_row)
        form.addRow("Folder nadrzędny:", location)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("np. MAN TGX 2021 — MD1CE101")
        form.addRow("Nazwa projektu:", self.name_edit)

        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("Opis całej kartoteki badawczej ECU")
        self.description_edit.setMaximumHeight(100)
        form.addRow("Opis projektu:", self.description_edit)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("np. Euro 6, EGR, po naprawie")
        form.addRow("Tagi:", self.tags_edit)

        self.bitrate_combo = QComboBox()
        for bitrate in (125_000, 250_000, 500_000, 1_000_000):
            self.bitrate_combo.addItem(f"{bitrate:,}".replace(",", " "), bitrate)
        self.bitrate_combo.setCurrentIndex(1)
        form.addRow("Domyślny bitrate:", self.bitrate_combo)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("BENCH — ACK aktywny", "bench")
        self.mode_combo.addItem("LISTEN ONLY — bez ACK", "listen-only")
        form.addRow("Domyślny tryb:", self.mode_combo)
        return page

    def project_root(self) -> Path:
        name = _safe_directory_name(self.project_name())
        return Path(self.location_edit.text()).expanduser().resolve() / name

    def project_name(self) -> str:
        entered = self.name_edit.text().strip()
        if entered:
            return entered
        parts = [
            self.vehicle_brand_edit.text().strip(),
            self.vehicle_model_edit.text().strip(),
            str(self.production_year_spin.value()) if self.production_year_spin.value() else "",
            self.ecu_type_edit.text().strip(),
            self.part_number_edit.text().strip(),
        ]
        return " — ".join(part for part in parts if part)

    def description(self) -> str:
        return self.description_edit.toPlainText().strip()

    def bitrate(self) -> int:
        return int(self.bitrate_combo.currentData())

    def receive_mode(self) -> str:
        return str(self.mode_combo.currentData())

    def profile(self) -> ProjectProfile:
        return ProjectProfile(
            vehicle_brand=self.vehicle_brand_edit.text(),
            vehicle_model=self.vehicle_model_edit.text(),
            production_year=self.production_year_spin.value() or None,
            vehicle_type=str(self.vehicle_type_combo.currentData()),
            vin=self.vin_edit.text(),
            registration_number=self.registration_edit.text(),
            customer_name=self.customer_edit.text(),
            vehicle_notes=self.vehicle_notes_edit.toPlainText(),
            ecu_manufacturer=self.ecu_manufacturer_edit.text(),
            ecu_type=self.ecu_type_edit.text(),
            ecu_function=self.ecu_function_edit.text(),
            part_number=self.part_number_edit.text(),
            secondary_part_number=self.secondary_part_number_edit.text(),
            hardware_number=self.hardware_number_edit.text(),
            hardware_version=self.hardware_version_edit.text(),
            software_number=self.software_number_edit.text(),
            software_version=self.software_version_edit.text(),
            calibration_number=self.calibration_edit.text(),
            bootloader_version=self.bootloader_edit.text(),
            ecu_serial_number=self.ecu_serial_edit.text(),
            processor_type=self.processor_edit.text(),
            ecu_status=str(self.ecu_status_combo.currentData()),
            fault_description=self.fault_description_edit.toPlainText(),
            tags=tuple(part.strip() for part in self.tags_edit.text().split(",") if part.strip()),
        ).normalized()

    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Folder dla projektów CRT",
            self.location_edit.text(),
        )
        if directory:
            self.location_edit.setText(directory)

    def _validate(self) -> None:
        if not self.project_name():
            QMessageBox.warning(
                self,
                "CRT",
                "Podaj nazwę projektu albo uzupełnij markę, model lub typ ECU.",
            )
            self.name_edit.setFocus()
            return
        try:
            self.profile()
        except ValueError as exc:
            QMessageBox.warning(self, "CRT", str(exc))
            return
        root = self.project_root()
        if root.exists() and any(root.iterdir()):
            QMessageBox.warning(
                self,
                "CRT",
                "Folder projektu już istnieje i nie jest pusty.",
            )
            return
        self.accept()


def _safe_directory_name(value: str) -> str:
    result = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in value.strip()
    )
    return result.strip("._") or "CRT_Project"
