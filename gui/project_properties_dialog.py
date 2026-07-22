from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.project import CrtProject


_DEFAULT_BITRATES = (125_000, 250_000, 500_000, 1_000_000)


class ProjectPropertiesDialog(QDialog):
    """Edit mutable CRT project metadata without moving the project directory."""

    def __init__(
        self,
        project: CrtProject,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.setObjectName("projectPropertiesDialog")
        self.setWindowTitle("Właściwości projektu CRT")
        self.resize(580, 360)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.path_edit = QLineEdit(str(project.root), self)
        self.path_edit.setObjectName("projectPropertiesPath")
        self.path_edit.setReadOnly(True)
        form.addRow("Folder projektu:", self.path_edit)

        self.name_edit = QLineEdit(project.manifest.name, self)
        self.name_edit.setObjectName("projectPropertiesName")
        form.addRow("Nazwa projektu:", self.name_edit)

        self.description_edit = QTextEdit(self)
        self.description_edit.setObjectName("projectPropertiesDescription")
        self.description_edit.setPlainText(project.manifest.description)
        self.description_edit.setPlaceholderText("ECU, stanowisko, cel badań…")
        self.description_edit.setMaximumHeight(110)
        form.addRow("Opis:", self.description_edit)

        self.bitrate_combo = QComboBox(self)
        self.bitrate_combo.setObjectName("projectPropertiesBitrate")
        current_bitrate = int(project.manifest.default_bitrate)
        bitrates = list(_DEFAULT_BITRATES)
        if current_bitrate not in bitrates:
            bitrates.append(current_bitrate)
            bitrates.sort()
        for bitrate in bitrates:
            label = f"{bitrate:,}".replace(",", " ")
            self.bitrate_combo.addItem(label, bitrate)
        self._select_combo_data(self.bitrate_combo, current_bitrate)
        form.addRow("Domyślny bitrate:", self.bitrate_combo)

        self.mode_combo = QComboBox(self)
        self.mode_combo.setObjectName("projectPropertiesReceiveMode")
        self.mode_combo.addItem("BENCH — ACK aktywny", "bench")
        self.mode_combo.addItem("LISTEN ONLY — bez ACK", "listen-only")
        current_mode = str(project.manifest.default_receive_mode)
        if self.mode_combo.findData(current_mode) < 0:
            self.mode_combo.addItem(current_mode, current_mode)
        self._select_combo_data(self.mode_combo, current_mode)
        form.addRow("Domyślny tryb:", self.mode_combo)

        root.addLayout(form)

        scope_note = QLabel(
            "Folder, identyfikator projektu, sesje i baza .crt/project.sqlite "
            "nie są przenoszone ani przebudowywane.",
            self,
        )
        scope_note.setObjectName("projectPropertiesScopeNote")
        scope_note.setWordWrap(True)
        root.addWidget(scope_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.setObjectName("projectPropertiesButtons")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def project_name(self) -> str:
        return self.name_edit.text().strip()

    def description(self) -> str:
        return self.description_edit.toPlainText().strip()

    def bitrate(self) -> int:
        return int(self.bitrate_combo.currentData())

    def receive_mode(self) -> str:
        return str(self.mode_combo.currentData())

    def _validate(self) -> None:
        if not self.project_name():
            QMessageBox.warning(self, "CRT", "Podaj nazwę projektu.")
            self.name_edit.setFocus()
            return
        self.accept()

    @staticmethod
    def _select_combo_data(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
