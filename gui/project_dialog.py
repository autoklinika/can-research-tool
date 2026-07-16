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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class NewProjectDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nowy projekt CRT")
        self.resize(560, 330)

        root = QVBoxLayout(self)
        form = QFormLayout()

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
        self.name_edit.setPlaceholderText("np. DAF_MX13_EGR")
        form.addRow("Nazwa projektu:", self.name_edit)

        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("ECU, stanowisko, cel badań…")
        self.description_edit.setMaximumHeight(100)
        form.addRow("Opis:", self.description_edit)

        self.bitrate_combo = QComboBox()
        for bitrate in (125_000, 250_000, 500_000, 1_000_000):
            self.bitrate_combo.addItem(f"{bitrate:,}".replace(",", " "), bitrate)
        self.bitrate_combo.setCurrentIndex(1)
        form.addRow("Domyślny bitrate:", self.bitrate_combo)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("BENCH — ACK aktywny", "bench")
        self.mode_combo.addItem("LISTEN ONLY — bez ACK", "listen-only")
        form.addRow("Domyślny tryb:", self.mode_combo)

        root.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def project_root(self) -> Path:
        name = _safe_directory_name(self.name_edit.text())
        return Path(self.location_edit.text()).expanduser().resolve() / name

    def project_name(self) -> str:
        return self.name_edit.text().strip()

    def description(self) -> str:
        return self.description_edit.toPlainText().strip()

    def bitrate(self) -> int:
        return int(self.bitrate_combo.currentData())

    def receive_mode(self) -> str:
        return str(self.mode_combo.currentData())

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
            QMessageBox.warning(self, "CRT", "Podaj nazwę projektu.")
            self.name_edit.setFocus()
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
    result = "".join(character if character.isalnum() or character in "._-" else "_" for character in value.strip())
    return result.strip("._") or "CRT_Project"
