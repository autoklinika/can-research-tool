from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from app.project import CrtProject, SessionRecord, StudyArea


ROLE_NODE_TYPE = Qt.UserRole + 1
ROLE_NODE_VALUE = Qt.UserRole + 2


class ProjectExplorer(QWidget):
    open_overview = Signal()
    open_live_capture = Signal()
    open_session = Signal(str)
    open_area = Signal(str)
    import_requested = Signal()
    add_area_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: CrtProject | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        toolbar = QHBoxLayout()
        self.add_area_button = QPushButton("+ Obszar")
        self.add_area_button.setToolTip("Dodaj obszar badań, np. EGR lub VGT")
        self.add_area_button.clicked.connect(self.add_area_requested)
        toolbar.addWidget(self.add_area_button)

        self.import_button = QPushButton("Importuj log")
        self.import_button.clicked.connect(self.import_requested)
        toolbar.addWidget(self.import_button)
        root.addLayout(toolbar)

        self.model = QStandardItemModel(self)
        self.model.setHorizontalHeaderLabels(["EXPLORER CRT"])
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(False)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setUniformRowHeights(True)
        self.tree.doubleClicked.connect(self._activate_index)
        root.addWidget(self.tree, 1)

        self.set_project(None)

    def set_project(self, project: CrtProject | None) -> None:
        self._project = project
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["EXPLORER CRT"])
        enabled = project is not None
        self.add_area_button.setEnabled(enabled)
        self.import_button.setEnabled(enabled)
        if project is None:
            item = QStandardItem("Brak otwartego projektu")
            item.setEnabled(False)
            self.model.appendRow(item)
            return
        self._build_tree(project)
        self.tree.expandToDepth(1)

    def refresh(self) -> None:
        self.set_project(self._project)

    def _build_tree(self, project: CrtProject) -> None:
        root = self._item(project.manifest.name, "project", str(project.root))
        root.setToolTip(str(project.root))
        self.model.appendRow(root)

        root.appendRow(self._item("Przegląd projektu", "overview", ""))
        root.appendRow(self._item("Live Capture", "live", ""))

        areas_root = self._item("Obszary badań", "section", "areas")
        for area in project.list_study_areas():
            area_item = self._item(area.name, "area", area.id)
            linked = project.area_session_ids(area.id)
            if linked:
                sessions_by_id = {session.id: session for session in project.list_sessions()}
                linked_root = self._item("Powiązane sesje", "section", "area-sessions")
                for session_id in sorted(linked):
                    session = sessions_by_id.get(session_id)
                    if session is not None:
                        linked_root.appendRow(self._session_item(project, session))
                area_item.appendRow(linked_root)
            areas_root.appendRow(area_item)
        root.appendRow(areas_root)

        experiments = self._item("Eksperymenty", "section", "experiments")
        experiments.appendRow(self._placeholder("Brak eksperymentów"))
        root.appendRow(experiments)

        sessions_root = self._item("Sesje CAN", "section", "sessions")
        live_root = self._item("Live", "section", "sessions-live")
        imported_root = self._item("Importowane", "section", "sessions-imported")
        for session in project.list_sessions():
            target = imported_root if session.source.startswith("imported") else live_root
            target.appendRow(self._session_item(project, session))
        if live_root.rowCount() == 0:
            live_root.appendRow(self._placeholder("Brak sesji"))
        if imported_root.rowCount() == 0:
            imported_root.appendRow(self._placeholder("Brak sesji"))
        sessions_root.appendRow(live_root)
        sessions_root.appendRow(imported_root)
        root.appendRow(sessions_root)

        for name, key in (
            ("Porównania", "comparisons"),
            ("Sygnały", "signals"),
            ("Hipotezy", "hypotheses"),
            ("Dekodery", "decoders"),
            ("Notatki", "notes"),
            ("Załączniki", "attachments"),
            ("Raporty", "reports"),
        ):
            section = self._item(name, "section", key)
            section.appendRow(self._placeholder("W przygotowaniu"))
            root.appendRow(section)

    def _session_item(self, project: CrtProject, session: SessionRecord) -> QStandardItem:
        label = session.name
        if session.status == "recording":
            label += "  ●"
        elif session.status == "error":
            label += "  ⚠"
        item = self._item(label, "session", str(project.absolute_path(session.relative_path)))
        item.setToolTip(
            f"{session.relative_path}\nRamki: {session.frame_count:,}\n"
            f"Znaczniki: {session.marker_count:,}\nStatus: {session.status}".replace(",", " ")
        )
        return item

    @staticmethod
    def _placeholder(text: str) -> QStandardItem:
        item = QStandardItem(text)
        item.setEnabled(False)
        return item

    @staticmethod
    def _item(text: str, node_type: str, value: str) -> QStandardItem:
        item = QStandardItem(text)
        item.setData(node_type, ROLE_NODE_TYPE)
        item.setData(value, ROLE_NODE_VALUE)
        return item

    def _activate_index(self, index) -> None:
        item = self.model.itemFromIndex(index)
        if item is None:
            return
        node_type = item.data(ROLE_NODE_TYPE)
        value = item.data(ROLE_NODE_VALUE)
        if node_type == "overview":
            self.open_overview.emit()
        elif node_type == "live":
            self.open_live_capture.emit()
        elif node_type == "session" and value:
            self.open_session.emit(str(Path(value)))
        elif node_type == "area" and value:
            self.open_area.emit(str(value))
