from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QTreeView, QVBoxLayout, QWidget

from app.project import CrtProject, SessionRecord
from app.project_dbc import list_project_dbc


ROLE_NODE_TYPE = Qt.UserRole + 1
ROLE_NODE_VALUE = Qt.UserRole + 2


class ProjectExplorer(QWidget):
    open_overview = Signal()
    open_live_capture = Signal()
    open_session = Signal(str)
    open_area = Signal(str)
    open_decoders = Signal()
    open_filters = Signal()
    import_requested = Signal()
    add_area_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: CrtProject | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.model = QStandardItemModel(self)
        self.model.setHorizontalHeaderLabels(["Projekt"])
        self.tree = QTreeView(self)
        self.tree.setObjectName("projectTree")
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(14)
        self.tree.setAnimated(False)
        self.tree.doubleClicked.connect(self._activate_index)
        root.addWidget(self.tree, 1)

        self.set_project(None)

    def set_project(self, project: CrtProject | None) -> None:
        self._project = project
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["Projekt"])

        if project is None:
            item = QStandardItem("Otwórz lub utwórz projekt CRT")
            item.setEnabled(False)
            self.model.appendRow(item)
            return

        self._build_tree(project)
        self.tree.expandToDepth(1)

    def refresh(self) -> None:
        self.set_project(self._project)

    def _build_tree(self, project: CrtProject) -> None:
        root = self._item(project.manifest.name, "project", str(project.root))
        font = root.font()
        font.setBold(True)
        root.setFont(font)
        root.setToolTip(str(project.root))
        self.model.appendRow(root)

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

        areas_root = self._item("Obszary badań", "section", "areas")
        sessions_by_id = {
            session.id: session for session in project.list_sessions()
        }
        for area in project.list_study_areas():
            area_item = self._item(area.name, "area", area.id)
            linked = project.area_session_ids(area.id)
            if linked:
                linked_root = self._item(
                    "Powiązane sesje",
                    "section",
                    "area-sessions",
                )
                for session_id in sorted(linked):
                    session = sessions_by_id.get(session_id)
                    if session is not None:
                        linked_root.appendRow(self._session_item(project, session))
                area_item.appendRow(linked_root)
            areas_root.appendRow(area_item)
        if areas_root.rowCount() == 0:
            areas_root.appendRow(self._placeholder("Brak obszarów"))
        root.appendRow(areas_root)

        root.appendRow(self._build_decoders(project))
        root.appendRow(self._item("Filtry globalne", "filters", ""))

    def _build_decoders(self, project: CrtProject) -> QStandardItem:
        records = list_project_dbc(project)
        active = sum(record.enabled for record in records)
        decoders = self._item("Dekodery", "decoders", "")
        dbc_root = self._item(
            f"DBC — aktywne {active}/{len(records)}",
            "decoders",
            "",
        )
        for record in records:
            state = "●" if record.enabled else "○"
            item = self._item(f"{state} {record.name}", "dbc", record.id)
            item.setToolTip(
                f"{record.relative_path}\nWiadomości: {record.message_count}\n"
                f"Stan: {'aktywny' if record.enabled else 'wyłączony'}"
            )
            dbc_root.appendRow(item)
        if not records:
            dbc_root.appendRow(self._placeholder("Brak plików DBC"))
        decoders.appendRow(dbc_root)
        return decoders

    def _session_item(
        self,
        project: CrtProject,
        session: SessionRecord,
    ) -> QStandardItem:
        label = session.name
        if session.status == "recording":
            label += "  ●"
        elif session.status == "error":
            label += "  ⚠"
        item = self._item(
            label,
            "session",
            str(project.absolute_path(session.relative_path)),
        )
        item.setToolTip(
            f"{session.relative_path}\nRamki: {session.frame_count:,}\n"
            f"Znaczniki: {session.marker_count:,}\nStatus: {session.status}".replace(
                ",",
                " ",
            )
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
        elif node_type in {"decoders", "dbc"}:
            self.open_decoders.emit()
        elif node_type == "filters":
            self.open_filters.emit()
