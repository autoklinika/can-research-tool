from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.project import CrtProject


class ProjectOverviewWidget(QWidget):
    open_live_requested = Signal()
    add_area_requested = Signal()
    import_requested = Signal()

    def __init__(self, project: CrtProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel(project.manifest.name)
        font = title.font()
        font.setPointSize(font.pointSize() + 8)
        font.setBold(True)
        title.setFont(font)
        root.addWidget(title)

        path = QLabel(str(project.root))
        path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(path)

        description = QTextEdit()
        description.setReadOnly(True)
        description.setMaximumHeight(110)
        description.setPlainText(project.manifest.description or "Brak opisu projektu.")
        root.addWidget(description)

        summary = QFrame()
        summary.setFrameShape(QFrame.StyledPanel)
        form = QFormLayout(summary)
        sessions = project.list_sessions()
        areas = project.list_study_areas()
        form.addRow("Sesje CAN:", QLabel(str(len(sessions))))
        form.addRow("Obszary badań:", QLabel(str(len(areas))))
        form.addRow(
            "Domyślny bitrate:",
            QLabel(f"{project.manifest.default_bitrate:,} bit/s".replace(",", " ")),
        )
        form.addRow("Tryb odbioru:", QLabel(project.manifest.default_receive_mode.upper()))
        form.addRow("Utworzono:", QLabel(project.manifest.created_at_utc))
        root.addWidget(summary)

        actions = QHBoxLayout()
        live = QPushButton("Otwórz Live Capture")
        live.clicked.connect(self.open_live_requested)
        actions.addWidget(live)
        add_area = QPushButton("Dodaj obszar badań")
        add_area.clicked.connect(self.add_area_requested)
        actions.addWidget(add_area)
        import_button = QPushButton("Importuj zapisany log")
        import_button.clicked.connect(self.import_requested)
        actions.addWidget(import_button)
        actions.addStretch(1)
        root.addLayout(actions)
        root.addStretch(1)
