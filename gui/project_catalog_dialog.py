from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.project_catalog import CatalogProject, ProjectCatalog, ProjectTimeFilter


_TIME_FILTERS: tuple[tuple[str, ProjectTimeFilter], ...] = (
    ("Wszystkie", "all"),
    ("30 dni", "30d"),
    ("7 dni", "7d"),
    ("Wczoraj", "yesterday"),
    ("Dzisiaj", "today"),
)


class ProjectCatalogDialog(QDialog):
    """Managed CRT project picker backed by the application project catalog."""

    project_removed = Signal(str)

    def __init__(self, catalog: ProjectCatalog, parent=None) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self._projects: list[CatalogProject] = []

        self.setObjectName("projectCatalogDialog")
        self.setWindowTitle("Projekty CRT")
        self.resize(1040, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        heading = QLabel("Projekty CRT", self)
        heading.setObjectName("projectCatalogHeading")
        heading.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(heading)

        description = QLabel(
            "Wybierz kartotekę badanego ECU. Wyszukiwanie obejmuje dane projektu, "
            "pojazdu i sterownika.",
            self,
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.search_edit = QLineEdit(self)
        self.search_edit.setObjectName("projectCatalogSearchEdit")
        self.search_edit.setPlaceholderText(
            "Szukaj: marka, model, VIN, producent ECU, HW, SW, numer części, tag…"
        )
        self.search_edit.setClearButtonEnabled(True)
        layout.addWidget(self.search_edit)

        self.time_tabs = QTabBar(self)
        self.time_tabs.setObjectName("projectCatalogTimeTabs")
        self.time_tabs.setExpanding(False)
        self.time_tabs.setDrawBase(False)
        for label, value in _TIME_FILTERS:
            index = self.time_tabs.addTab(label)
            self.time_tabs.setTabData(index, value)
        layout.addWidget(self.time_tabs)

        self.table = QTableWidget(0, 6, self)
        self.table.setObjectName("projectCatalogTable")
        self.table.setHorizontalHeaderLabels(
            ["Projekt", "Pojazd / maszyna", "Sterownik ECU", "Ostatnio otwarty", "Status", "Lokalizacja"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 210)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 210)
        self.table.setColumnWidth(3, 145)
        self.table.setColumnWidth(4, 105)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.summary_label = QLabel(self)
        self.summary_label.setObjectName("projectCatalogSummaryLabel")
        footer.addWidget(self.summary_label, 1)

        self.refresh_button = QPushButton("Odśwież", self)
        self.refresh_button.setObjectName("projectCatalogRefreshButton")
        footer.addWidget(self.refresh_button)
        layout.addLayout(footer)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.open_button = self.buttons.button(QDialogButtonBox.StandardButton.Open)
        self.open_button.setText("Otwórz projekt")
        self.open_button.setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Anuluj")
        layout.addWidget(self.buttons)

        self.search_edit.textChanged.connect(self.refresh)
        self.time_tabs.currentChanged.connect(self.refresh)
        self.refresh_button.clicked.connect(self._refresh_catalog)
        self.table.itemSelectionChanged.connect(self._sync_open_button)
        self.table.itemDoubleClicked.connect(lambda _item: self._accept_available())
        self.table.customContextMenuRequested.connect(self._open_context_menu)
        self.buttons.accepted.connect(self._accept_available)
        self.buttons.rejected.connect(self.reject)

        self._refresh_catalog()
        self.search_edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def selected_project(self) -> CatalogProject | None:
        row = self.table.currentRow()
        if not 0 <= row < len(self._projects):
            return None
        return self._projects[row]

    def selected_project_path(self) -> str | None:
        project = self.selected_project()
        return project.root_path if project is not None and project.available else None

    def refresh(self, *_args: object) -> None:
        selected_id = None
        selected = self.selected_project()
        if selected is not None:
            selected_id = selected.project_id

        time_filter = self.time_tabs.currentData()
        if time_filter not in {value for _label, value in _TIME_FILTERS}:
            time_filter = "all"
        self._projects = self.catalog.list_projects(
            query=self.search_edit.text(),
            time_filter=time_filter,
            include_missing=True,
        )

        self.table.setRowCount(len(self._projects))
        selected_row = -1
        for row, project in enumerate(self._projects):
            if project.project_id == selected_id:
                selected_row = row
            self._populate_row(row, project)

        self.summary_label.setText(self._summary_text())
        if selected_row >= 0:
            self.table.selectRow(selected_row)
        elif self._projects:
            self.table.selectRow(0)
        else:
            self.table.clearSelection()
        self._sync_open_button()

    def _populate_row(self, row: int, project: CatalogProject) -> None:
        profile = project.profile
        vehicle = " ".join(
            part for part in (profile.vehicle_brand, profile.vehicle_model) if part
        )
        if profile.production_year is not None:
            vehicle = f"{vehicle} ({profile.production_year})" if vehicle else str(profile.production_year)
        if not vehicle:
            vehicle = profile.vin or "—"

        ecu = " ".join(
            part for part in (profile.ecu_manufacturer, profile.ecu_type) if part
        )
        ecu_details = " / ".join(
            part for part in (profile.hardware_number, profile.software_number) if part
        )
        if ecu_details:
            ecu = f"{ecu} — {ecu_details}" if ecu else ecu_details
        if not ecu:
            ecu = "—"

        values = (
            project.name,
            vehicle,
            ecu,
            _display_datetime(project.last_opened_at_utc),
            "Dostępny" if project.available else "Brak folderu",
            project.root_path,
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, project.project_id)
            if not project.available:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip(
                    "Folder projektu lub plik project.crt.json nie jest obecnie dostępny."
                )
            self.table.setItem(row, column, item)

    def _summary_text(self) -> str:
        available = sum(1 for project in self._projects if project.available)
        missing = len(self._projects) - available
        if missing:
            return f"Projektów: {len(self._projects)} | dostępnych: {available} | brakujących: {missing}"
        return f"Projektów: {len(self._projects)}"

    def _refresh_catalog(self) -> None:
        self.catalog.refresh_availability()
        self.refresh()

    def _sync_open_button(self) -> None:
        project = self.selected_project()
        self.open_button.setEnabled(bool(project is not None and project.available))

    def _accept_available(self) -> None:
        project = self.selected_project()
        if project is None:
            return
        if not project.available:
            QMessageBox.warning(
                self,
                "Projekt niedostępny",
                "Nie można otworzyć projektu, ponieważ jego folder lub manifest nie jest dostępny.",
            )
            return
        self.accept()

    def _open_context_menu(self, position) -> None:
        row = self.table.rowAt(position.y())
        if row < 0:
            return
        self.table.selectRow(row)
        project = self.selected_project()
        if project is None:
            return

        menu = QMenu(self)
        open_action = QAction("Otwórz projekt", menu)
        open_action.setEnabled(project.available)
        open_action.triggered.connect(self._accept_available)
        menu.addAction(open_action)
        menu.addSeparator()
        remove_action = QAction("Usuń wpis z katalogu", menu)
        remove_action.triggered.connect(self._remove_selected_entry)
        menu.addAction(remove_action)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _remove_selected_entry(self) -> None:
        project = self.selected_project()
        if project is None:
            return
        answer = QMessageBox.question(
            self,
            "Usuń wpis z katalogu",
            f"Usunąć projekt „{project.name}” z listy CRT?\n\n"
            "Pliki projektu nie zostaną usunięte.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.catalog.remove(project.project_id)
        self.project_removed.emit(project.project_id)
        self.refresh()


def _display_datetime(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
