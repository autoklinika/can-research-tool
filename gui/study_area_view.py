from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QVBoxLayout, QWidget

from app.project import CrtProject


class StudyAreaViewWidget(QWidget):
    def __init__(self, project: CrtProject, area_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        area = next((item for item in project.list_study_areas() if item.id == area_id), None)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        if area is None:
            root.addWidget(QLabel("Nie znaleziono obszaru badań."))
            return

        title = QLabel(area.name)
        font = title.font()
        font.setPointSize(font.pointSize() + 7)
        font.setBold(True)
        title.setFont(font)
        root.addWidget(title)
        root.addWidget(QLabel(area.description or "Brak opisu obszaru badań."))

        root.addWidget(QLabel("Powiązane sesje:"))
        sessions = {session.id: session for session in project.list_sessions()}
        linked = project.area_session_ids(area.id)
        listing = QListWidget()
        for session_id in sorted(linked):
            session = sessions.get(session_id)
            if session is not None:
                listing.addItem(f"{session.name} — {session.frame_count} ramek")
        if listing.count() == 0:
            listing.addItem("Brak powiązanych sesji")
        root.addWidget(listing)

        root.addWidget(QLabel("Hipotezy, sygnały, eksperymenty i notatki będą rozwijane w tym miejscu."))
        root.addStretch(1)
