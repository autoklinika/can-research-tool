from __future__ import annotations

import logging
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QSettings, QSize, QThreadPool, QTimer, Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QStyle,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.project import CrtProject
from app.project_catalog import ProjectCatalog
from app.project_dbc import active_project_dbc_paths, list_project_dbc

from .comparison_sets_controller import ComparisonSetsController
from .filter_manager_window import FilterPresetController
from .help_center_controller import HelpCenterController
from .live_capture import LiveCaptureWidget
from .live_log_save_controller import LiveLogSaveController
from .log_search_controller import LogSearchController
from .project_catalog_dialog import ProjectCatalogDialog
from .project_navigator import CloseTabResult
from .project_preparation_progress import (
    ProjectPreparationProgress,
    ProjectPreparationStatusWidget,
)
from .project_properties_controller import ProjectPropertiesController
from .settings_view import SettingsViewWidget
from .window_fullscreen import enable_full_screen
from .workspace_docks import (
    LogicalMessageTooltipSuppressor,
    ProjectDockTitleBar,
    bind_dock_toggle,
)

if TYPE_CHECKING:
    from .application_container import ApplicationContainer
    from .import_task import ProjectImportTask
    from .project_dialog import NewProjectDialog


_LOG = logging.getLogger("crt.gui")
_OUTPUT_LOG_LIMIT = 5000
_DOCK_FEATURES = (
    QDockWidget.DockWidgetFeature.DockWidgetClosable
    | QDockWidget.DockWidgetFeature.DockWidgetMovable
    | QDockWidget.DockWidgetFeature.DockWidgetFloatable
)


class MainWindow(QMainWindow):
    """IDE-style CRT shell: window chrome and the active project lifecycle.

    Feature behaviour lives in dedicated controllers created here and called
    explicitly (``filter_presets``, ``live_log``, ``log_search``,
    ``comparison_sets``, ``project_properties``, ``help_center``). The window
    does not depend on subclasses to extend it.
    """

    # Revision 6 adds an opt-in main toolbar alongside the opt-in Inspector.
    WORKSPACE_STATE_VERSION = 6
    GEOMETRY_KEY = "ui/engineeringShellGeometry"
    STATE_KEY = "ui/engineeringShellState"

    def __init__(self, services: ApplicationContainer) -> None:
        super().__init__()
        self.services = services
        self.setObjectName("engineeringMainWindow")
        self.setWindowTitle("CAN Research Tool")
        self.resize(1580, 920)
        self.setMinimumSize(1100, 700)

        self.settings = QSettings()
        self.project: CrtProject | None = None
        self.project_catalog = ProjectCatalog()
        self.output_log: deque[str] = deque(maxlen=_OUTPUT_LOG_LIMIT)
        self._import_tasks: list[ProjectImportTask] = []

        self._build_central_tabs()
        self.navigator = services.create_project_navigator(self.tabs)
        self.project_preparation = ProjectPreparationProgress(self)

        self.filter_presets = FilterPresetController(self)
        self.live_log = LiveLogSaveController(self)
        self.log_search = LogSearchController(self)
        self.comparison_sets = ComparisonSetsController(self)
        self.project_properties = ProjectPropertiesController(self)
        self.help_center = HelpCenterController(self)

        self._build_actions()
        self._build_menu()
        self._build_primary_toolbar()
        self._build_docks()
        self.session_management = services.create_session_management(self)
        self._build_status_bar()
        self.live_log.save_available_changed.connect(self.save_log_action.setEnabled)
        self._show_welcome()

        last_project = self.settings.value("project/lastPath", "", str)
        if last_project and (Path(last_project) / "project.crt.json").is_file():
            try:
                self.open_project_path(Path(last_project))
            except Exception as exc:
                self.append_output(f"Nie udało się automatycznie otworzyć projektu: {exc}")

        self.setDockNestingEnabled(True)
        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
        )
        self.setCorner(Qt.Corner.TopLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self._restore_workspace_layout()
        # Main tools are opt-in on every start, whatever the saved layout says.
        self._hide_primary_toolbar()
        self._update_project_context()
        self._set_capture_status(self.capture_status.text())

        self._table_tooltip_suppressor = LogicalMessageTooltipSuppressor(self)
        self.tabs.currentChanged.connect(self._schedule_tooltip_suppressor_scan)
        QTimer.singleShot(0, self._attach_tooltip_suppressor)

    # ------------------------------------------------------------------ build

    def _build_actions(self) -> None:
        style = self.style()
        standard = QStyle.StandardPixmap

        self.new_project_action = QAction("Nowy projekt…", self)
        self.new_project_action.setShortcut("Ctrl+Shift+N")
        self.new_project_action.setIcon(style.standardIcon(standard.SP_FileIcon))
        self.new_project_action.triggered.connect(self._new_project)

        self.open_project_action = QAction("Otwórz projekt CRT…", self)
        self.open_project_action.setShortcut("Ctrl+Shift+O")
        self.open_project_action.setToolTip(
            "Wybierz projekt z centralnego katalogu CAN Research Tool"
        )
        self.open_project_action.setIcon(style.standardIcon(standard.SP_DirOpenIcon))
        self.open_project_action.triggered.connect(self._open_project_catalog)

        self.project_properties_action = QAction("Właściwości projektu…", self)
        self.project_properties_action.setObjectName("projectPropertiesAction")
        self.project_properties_action.setToolTip(
            "Edytuj dane projektu, pojazdu i sterownika ECU bez zmiany folderu"
        )
        self.project_properties_action.setEnabled(False)
        self.project_properties_action.triggered.connect(self.project_properties.edit)

        self.import_action = QAction("Importuj log…", self)
        self.import_action.setShortcut("Ctrl+I")
        self.import_action.setIcon(style.standardIcon(standard.SP_DialogOpenButton))
        self.import_action.triggered.connect(self._import_log)
        self.import_action.setEnabled(False)

        self.save_log_action = QAction("Zapisz log", self)
        self.save_log_action.setObjectName("savePendingLiveLogAction")
        self.save_log_action.setToolTip(
            "Przenieś zakończony log tymczasowy do trwałych sesji projektu"
        )
        self.save_log_action.setEnabled(False)
        self.save_log_action.triggered.connect(self.live_log.save_pending)

        self.exit_action = QAction("Zakończ", self)
        self.exit_action.triggered.connect(self.close)

        self.toggle_explorer_action = QAction("Projekt", self)
        self.toggle_explorer_action.setCheckable(True)
        self.toggle_explorer_action.setChecked(True)
        self.toggle_explorer_action.setShortcut("Ctrl+Shift+B")
        self.toggle_explorer_action.setToolTip(
            "Pokaż lub ukryj panel Projekt (Ctrl+Shift+B)"
        )
        self.toggle_explorer_action.setStatusTip(
            "Pokaż lub ukryj panel Projekt — Ctrl+Shift+B"
        )
        self.toggle_explorer_action.setIcon(style.standardIcon(standard.SP_DirIcon))

        self.toggle_inspector_action = QAction("Inspektor", self)
        self.toggle_inspector_action.setCheckable(True)
        self.toggle_inspector_action.setChecked(True)
        self.toggle_inspector_action.setShortcut("Ctrl+Shift+I")
        self.toggle_inspector_action.setToolTip(
            "Pokaż lub ukryj Inspektor (Ctrl+Shift+I)"
        )

        self.toggle_primary_toolbar_action = QAction("Narzędzia główne", self)
        self.toggle_primary_toolbar_action.setObjectName("togglePrimaryToolbarAction")
        self.toggle_primary_toolbar_action.setCheckable(True)
        self.toggle_primary_toolbar_action.setChecked(False)
        self.toggle_primary_toolbar_action.setToolTip(
            "Pokaż lub ukryj pasek Narzędzia główne"
        )

        self.reset_layout_action = QAction("Resetuj układ okna", self)
        self.reset_layout_action.setToolTip(
            "Przywróć domyślny układ docków i pasków narzędzi"
        )
        self.reset_layout_action.triggered.connect(self.reset_workspace_layout)

        self.full_screen_controller = enable_full_screen(
            self,
            action_object_name="mainWindowFullScreenAction",
        )
        self.full_screen_action = self.full_screen_controller.action

        self.overview_action = QAction("Przegląd", self)
        self.overview_action.setToolTip("Otwórz przegląd aktualnego projektu")
        self.overview_action.setIcon(style.standardIcon(standard.SP_DesktopIcon))
        self.overview_action.triggered.connect(self._open_overview)

        self.live_action = QAction("Live", self)
        self.live_action.setIcon(style.standardIcon(standard.SP_MediaPlay))
        self.live_action.triggered.connect(self.open_live_capture)

        self.search_action = QAction("Szukaj", self)
        self.search_action.setShortcut("Ctrl+F")
        self.search_action.setShortcutContext(Qt.ApplicationShortcut)
        self.search_action.setToolTip("Otwórz wyszukiwanie w aktywnym logu (Ctrl+F)")
        self.search_action.triggered.connect(self.log_search.open)

        self.compare_action = QAction("Porównaj", self)
        self.compare_action.setToolTip(
            "Twórz trwałe zestawy sesji i uruchamiaj pasywne analizy porównawcze"
        )
        self.compare_action.triggered.connect(
            lambda _checked=False: self.comparison_sets.open()
        )

        self.signals_action = QAction("Sygnały", self)
        self.signals_action.triggered.connect(
            lambda: self._open_placeholder(
                "signals", "Sygnały", "Katalog sygnałów i hipotez"
            )
        )

        self.decoders_action = QAction("Dekodery", self)
        self.decoders_action.setIcon(
            style.standardIcon(standard.SP_FileDialogContentsView)
        )
        self.decoders_action.triggered.connect(self.open_decoders)

        self.filters_action = QAction("Filtry", self)
        self.filters_action.setObjectName("globalFiltersAction")
        self.filters_action.setShortcut("Ctrl+D")
        self.filters_action.setShortcutContext(Qt.ApplicationShortcut)
        self.filters_action.setToolTip("Otwórz globalne filtry w osobnym oknie (Ctrl+D)")
        self.filters_action.setIcon(style.standardIcon(standard.SP_FileDialogListView))
        self.filters_action.triggered.connect(self.filter_presets.open_editor)

        self.session_markers_action = QAction("Znaczniki", self)
        self.session_markers_action.setObjectName("openSessionMarkersAction")
        self.session_markers_action.setShortcut("Ctrl+M")
        self.session_markers_action.setShortcutContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.session_markers_action.setToolTip(
            "Otwórz znaczniki bieżącej zapisanej sesji (Ctrl+M)"
        )
        self.session_markers_action.triggered.connect(self._open_session_markers)

        self.settings_action = QAction("Ustawienia", self)
        self.settings_action.setIcon(style.standardIcon(standard.SP_ComputerIcon))
        self.settings_action.triggered.connect(self._open_settings)

        self.help_action = QAction("Pomoc CRT", self)
        self.help_action.setObjectName("helpCenterAction")
        self.help_action.setShortcut("F1")
        self.help_action.setToolTip(
            "Otwórz przeszukiwalny opis funkcji CAN Research Tool"
        )
        self.help_action.triggered.connect(
            lambda _checked=False: self.help_center.open()
        )

        self.help_quick_start_action = QAction("Szybki start", self)
        self.help_quick_start_action.setObjectName("helpQuickStartAction")
        self.help_quick_start_action.triggered.connect(
            lambda _checked=False: self.help_center.open("quick-start")
        )

        self.help_glossary_action = QAction("Słownik pojęć", self)
        self.help_glossary_action.setObjectName("helpGlossaryAction")
        self.help_glossary_action.triggered.connect(
            lambda _checked=False: self.help_center.open("glossary")
        )

        self.help_shortcuts_action = QAction("Skróty klawiaturowe", self)
        self.help_shortcuts_action.setObjectName("helpShortcutsAction")
        self.help_shortcuts_action.triggered.connect(
            lambda _checked=False: self.help_center.open("shortcuts")
        )

        self.about_action = QAction("O CAN Research Tool", self)
        self.about_action.setObjectName("aboutCrtAction")
        self.about_action.triggered.connect(self.help_center.show_about)

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("Plik")
        file_menu.addAction(self.new_project_action)
        file_menu.addAction(self.open_project_action)
        file_menu.addAction(self.project_properties_action)
        file_menu.addSeparator()
        file_menu.addAction(self.import_action)
        file_menu.addAction(self.save_log_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        view_menu = menu_bar.addMenu("Widok")
        view_menu.addAction(self.toggle_explorer_action)
        view_menu.addAction(self.toggle_inspector_action)
        view_menu.addSeparator()
        view_menu.addAction(self.toggle_primary_toolbar_action)
        view_menu.addAction(self.reset_layout_action)
        view_menu.addSeparator()
        view_menu.addAction(self.full_screen_action)

        capture_menu = menu_bar.addMenu("Capture")
        capture_menu.addAction(self.live_action)

        analysis_menu = menu_bar.addMenu("Analiza")
        analysis_menu.addAction(self.search_action)
        analysis_menu.addAction(self.compare_action)
        analysis_menu.addAction(self.signals_action)

        tools_menu = menu_bar.addMenu("Narzędzia")
        tools_menu.addAction(self.decoders_action)
        tools_menu.addAction(self.filters_action)
        tools_menu.addAction(self.session_markers_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.settings_action)

        help_menu = menu_bar.addMenu("Pomoc")
        help_menu.setObjectName("helpMenu")
        help_menu.addAction(self.help_action)
        help_menu.addAction(self.help_quick_start_action)
        help_menu.addSeparator()
        help_menu.addAction(self.help_glossary_action)
        help_menu.addAction(self.help_shortcuts_action)
        help_menu.addSeparator()
        help_menu.addAction(self.about_action)
        self.help_menu = help_menu

    def _build_primary_toolbar(self) -> None:
        primary = QToolBar("Narzędzia główne", self)
        primary.setObjectName("primaryToolBar")
        primary.setMovable(True)
        primary.setFloatable(False)
        primary.setIconSize(QSize(16, 16))
        primary.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        primary.addAction(self.new_project_action)
        primary.addAction(self.open_project_action)
        primary.addAction(self.import_action)
        primary.addSeparator()
        primary.addAction(self.overview_action)
        primary.addAction(self.live_action)
        primary.addSeparator()
        primary.addAction(self.decoders_action)
        primary.addAction(self.filters_action)

        spacer = QWidget(primary)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        primary.addWidget(spacer)

        self.project_context_label = QLabel("Brak projektu", primary)
        self.project_context_label.setObjectName("toolbarProjectContext")
        primary.addWidget(self.project_context_label)

        self.capture_indicator = QLabel("STOPPED", primary)
        self.capture_indicator.setObjectName("captureIndicator")
        self.capture_indicator.setProperty("state", "stopped")
        primary.addWidget(self.capture_indicator)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, primary)
        self.primary_toolbar = primary

        self.toggle_primary_toolbar_action.toggled.connect(primary.setVisible)
        primary.visibilityChanged.connect(self.toggle_primary_toolbar_action.setChecked)

    def _build_docks(self) -> None:
        self.explorer = self.services.create_project_explorer()
        self.explorer.open_overview.connect(self._open_overview)
        self.explorer.open_live_capture.connect(self.open_live_capture)
        self.explorer.open_session.connect(self._open_session)
        self.explorer.open_area.connect(self._open_area)
        self.explorer.open_decoders.connect(self.open_decoders)
        self.explorer.open_filters.connect(self.filter_presets.open_editor)
        self.explorer.open_comparison_sets.connect(self.comparison_sets.open)
        self.explorer_dock = QDockWidget("Projekt", self)
        self.explorer_dock.setObjectName("projectExplorerDock")
        self.explorer_dock.setWidget(self.explorer)
        self.explorer_dock.setMinimumWidth(230)
        self.explorer_dock.setFeatures(_DOCK_FEATURES)
        self.explorer_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.LeftDockWidgetArea, self.explorer_dock)
        self.project_dock_title_bar = ProjectDockTitleBar(
            self.explorer_dock,
            self._collapse_project_dock,
        )
        self.explorer_dock.setTitleBarWidget(self.project_dock_title_bar)

        self.inspector = QPlainTextEdit()
        self.inspector.setReadOnly(True)
        self.inspector.setMaximumBlockCount(1000)
        self.inspector.setPlaceholderText(
            "Zaznacz ramkę, wiadomość, znacznik lub element projektu."
        )
        self.inspector_dock = QDockWidget("Inspektor", self)
        self.inspector_dock.setObjectName("inspectorDock")
        self.inspector_dock.setWidget(self.inspector)
        self.inspector_dock.setMinimumWidth(260)
        self.inspector_dock.setFeatures(_DOCK_FEATURES)
        self.inspector_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.RightDockWidgetArea, self.inspector_dock)

        bind_dock_toggle(self.toggle_explorer_action, self.explorer_dock)
        bind_dock_toggle(self.toggle_inspector_action, self.inspector_dock)

        self.resizeDocks(
            [self.explorer_dock, self.inspector_dock],
            [280, 320],
            Qt.Orientation.Horizontal,
        )

    def _build_central_tabs(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.setObjectName("workspaceTabs")
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)

        bar = self.tabs.tabBar()
        bar.setExpanding(False)
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._show_tab_context_menu)

    def _build_status_bar(self) -> None:
        status = QStatusBar(self)
        self.setStatusBar(status)
        status.setSizeGripEnabled(True)

        self.project_status = QLabel("Brak projektu")
        self.project_status.setObjectName("projectStatus")
        status.addWidget(self.project_status, 1)

        self.project_preparation_status = ProjectPreparationStatusWidget(
            self.project_preparation,
            status,
        )
        status.addWidget(self.project_preparation_status)

        self.transport_status = QLabel("CAN: —")
        self.transport_status.setObjectName("transportStatus")
        self.mode_status = QLabel("TRYB: —")
        self.mode_status.setObjectName("modeStatus")
        self.capture_status = QLabel("STOPPED")
        self.capture_status.setObjectName("captureStatus")
        self.capture_status.setMinimumWidth(82)
        status.addPermanentWidget(self.transport_status)
        status.addPermanentWidget(self.mode_status)
        status.addPermanentWidget(self.capture_status)

    def _show_welcome(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(60, 60, 60, 60)
        layout.addStretch(1)
        title = QLabel("CAN Research Tool")
        font = title.font()
        font.setPointSize(font.pointSize() + 14)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        layout.addWidget(
            QLabel(
                "Projektowe środowisko reverse engineeringu CAN.\n"
                "Każdy projekt jest samodzielnym folderem z sesjami, znacznikami, "
                "obszarami badań i wiedzą techniczną."
            )
        )
        row = QHBoxLayout()
        new_button = QPushButton("Nowy projekt")
        new_button.clicked.connect(self._new_project)
        row.addWidget(new_button)
        open_button = QPushButton("Otwórz projekt")
        open_button.clicked.connect(self._open_project_dialog)
        row.addWidget(open_button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(2)
        self._add_tab("welcome", widget, "Start", closable=False)
        self.explorer_dock.hide()
        self.inspector_dock.hide()

    # -------------------------------------------------------- project lifecycle

    def _new_project(self) -> None:
        dialog = self.services.create_project_dialog(self)
        result = dialog.exec()
        if result != QDialog.DialogCode.Accepted:
            return
        self.create_project_from_dialog(dialog)

    def create_project_from_dialog(self, dialog: NewProjectDialog) -> None:
        try:
            project = CrtProject.create(
                dialog.project_root(),
                name=dialog.project_name(),
                description=dialog.description(),
                default_bitrate=dialog.bitrate(),
                default_receive_mode=dialog.receive_mode(),
            )
            self.project_catalog.register_project(
                project.root,
                profile=dialog.profile(),
                opened=True,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Nie można utworzyć projektu", str(exc))
            return
        self.set_project(project)
        self.append_output(f"Utworzono projekt i dodano do katalogu CRT: {project.root}")

    def _open_project_catalog(self) -> None:
        try:
            self.project_catalog.refresh_availability()
            dialog = ProjectCatalogDialog(self.project_catalog, self)
            dialog.full_screen_controller = enable_full_screen(
                dialog,
                action_object_name="projectCatalogFullScreenAction",
                maximize_button=True,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Nie można otworzyć katalogu projektów",
                str(exc),
            )
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        path = dialog.selected_project_path()
        if not path:
            return
        try:
            self.open_project_path(Path(path))
        except Exception as exc:
            self.project_catalog.refresh_availability()
            QMessageBox.critical(
                self,
                "Nie można otworzyć projektu",
                str(exc),
            )

    def _open_project_dialog(self) -> None:
        start = self.settings.value("project/lastParent", str(Path.home()), str)
        directory = QFileDialog.getExistingDirectory(
            self, "Otwórz projekt CRT", start
        )
        if directory:
            try:
                self.open_project_path(Path(directory))
            except Exception as exc:
                QMessageBox.critical(self, "Nie można otworzyć projektu", str(exc))

    def open_project_path(self, path: Path) -> None:
        project = CrtProject.open(path)
        self.project_catalog.register_project(project.root, opened=True)
        self.set_project(project)
        self.append_output(f"Otwarto projekt z katalogu CRT: {path}")

    def set_project(self, project: CrtProject) -> None:
        if self.has_active_capture():
            QMessageBox.warning(
                self, "CRT", "Zatrzymaj aktywną rejestrację przed zmianą projektu."
            )
            return

        previous = self.project
        changing = (
            previous is not None
            and Path(previous.root).resolve() != Path(project.root).resolve()
        )
        if changing:
            if not self.live_log.confirm_unsaved("project_change"):
                return
            if not self.filter_presets.close_editor():
                return
        self.comparison_sets.cancel_navigation(
            "Aktywny projekt został zmieniony podczas nawigacji do dowodu."
        )

        self.project = project
        list_project_dbc(project)
        self.settings.setValue("project/lastPath", str(project.root))
        self.settings.setValue("project/lastParent", str(project.root.parent))
        self.setWindowTitle(f"{project.manifest.name} — CAN Research Tool")
        self.project_status.setText(
            f"Projekt: {project.manifest.name} | {project.root}"
        )
        self.import_action.setEnabled(True)
        self.project_properties_action.setEnabled(True)
        self.explorer.set_project(project)
        self.explorer_dock.show()
        self.close_project_tabs()
        self._open_overview()

        self.filter_presets.reload_shortcuts()
        self._update_project_context()
        self.live_log.sync()
        if changing:
            self.log_search.reset()
        try:
            entry = self.project_catalog.register_project(project.root, opened=True)
            self.project_catalog.mark_opened(entry.project_id)
        except Exception as exc:
            self.append_output(f"Nie udało się zaktualizować katalogu projektów: {exc}")

    def refresh_project_identity(self) -> None:
        """Re-render every place showing the project's name or defaults."""

        project = self.project
        if project is None:
            return

        self.setWindowTitle(f"{project.manifest.name} — CAN Research Tool")
        self.project_status.setText(
            f"Projekt: {project.manifest.name} | {project.root}"
        )
        self.explorer.refresh()
        self._update_project_context()

        overview = self.navigator.widget("project-overview")
        if overview is not None:
            previous_widget = self.tabs.currentWidget()
            previous_was_overview = previous_widget is overview
            self.navigator.close_widget(overview)
            self._open_overview()
            if (
                not previous_was_overview
                and previous_widget is not None
                and self.tabs.indexOf(previous_widget) >= 0
            ):
                self.tabs.setCurrentWidget(previous_widget)

        self.settings.setValue("project/lastPath", str(Path(project.root)))

    # ------------------------------------------------------------------ views

    def _open_overview(self) -> None:
        if self.project is None:
            return
        key = "project-overview"
        if self._activate_tab(key):
            return
        widget = self.services.create_project_overview(self.project)
        widget.open_live_requested.connect(self.open_live_capture)
        widget.add_area_requested.connect(self._add_study_area)
        widget.import_requested.connect(self._import_log)
        widget.open_session_requested.connect(self._open_session)
        self._add_tab(key, widget, "Przegląd")

    def open_live_capture(self) -> None:
        if self.project is None:
            QMessageBox.information(
                self, "CRT", "Najpierw otwórz lub utwórz projekt."
            )
            return
        key = "live-capture"
        if self._activate_tab(key):
            self.live_log.sync()
            return
        widget = self.services.create_live_capture_view(self.project)
        widget.inspector_text.connect(self.inspector.setPlainText)
        widget.output_message.connect(self.append_output)
        widget.status_text.connect(self._set_capture_status)
        widget.project_changed.connect(self.explorer.refresh)
        widget.project_changed.connect(self._update_project_context)
        self.live_log.bind(widget)
        self.log_search.bind_live_capture(widget)
        self._add_tab(key, widget, "Live Capture")
        self.live_log.sync()

    def open_decoders(self) -> None:
        if self.project is None:
            QMessageBox.information(
                self, "CRT", "Najpierw otwórz lub utwórz projekt."
            )
            return
        key = "decoders"
        if self._activate_tab(key):
            return
        widget = self.services.create_dbc_manager(self.project)
        widget.inspector_text.connect(self.inspector.setPlainText)
        widget.output_message.connect(self.append_output)
        widget.changed.connect(self._dbc_changed)
        self._add_tab(key, widget, "Dekodery")

    def _dbc_changed(self) -> None:
        if self.project is None:
            return
        paths = active_project_dbc_paths(self.project)
        self.explorer.refresh()
        self.navigator.reload_session_dbc(paths)
        if self.has_active_capture():
            self.append_output(
                "Zmieniono aktywne DBC. Trwająca rejestracja zachowuje zestaw wybrany przy Start; "
                "nowy stan będzie użyty w następnej sesji."
            )
        else:
            self.append_output(f"Aktywne dekodery DBC: {len(paths)}")

    def _open_session(self, path: str) -> None:
        self.navigator.open_session(
            path,
            project=self.project,
            inspector_sink=self.inspector.setPlainText,
            output_sink=self.append_output,
        )

    def _open_area(self, area_id: str) -> None:
        if self.project is None:
            return
        area = next(
            (
                item
                for item in self.project.list_study_areas()
                if item.id == area_id
            ),
            None,
        )
        if area is None:
            return
        key = f"area:{area.id}"
        if self._activate_tab(key):
            return
        self._add_tab(
            key,
            self.services.create_study_area_view(self.project, area.id),
            area.name,
        )

    def _add_study_area(self) -> None:
        if self.project is None:
            return
        name, accepted = QInputDialog.getText(
            self,
            "Nowy obszar badań",
            "Nazwa, np. EGR, VGT, SCR:",
        )
        if not accepted or not name.strip():
            return
        try:
            area = self.project.add_study_area(name)
        except Exception as exc:
            QMessageBox.critical(self, "Nie można dodać obszaru", str(exc))
            return
        self.explorer.refresh()
        self._open_area(area.id)
        self.append_output(f"Dodano obszar badań: {area.name}")

    def _open_settings(self) -> None:
        key = "settings"
        if self._activate_tab(key):
            return
        widget = SettingsViewWidget(self)
        widget.output_message.connect(self.append_output)
        self._add_tab(key, widget, "Ustawienia")

    def _open_session_markers(self) -> None:
        current = self.tabs.currentWidget()
        opener = getattr(current, "open_marker_window", None)
        if callable(opener):
            opener()
            return
        QMessageBox.information(
            self,
            "Znaczniki",
            "Otwórz zapisaną lub tymczasową sesję, aby wyświetlić jej znaczniki.",
        )

    def open_help_topic(self, topic_id: str) -> None:
        """Public hook for context-sensitive Help buttons."""

        self.help_center.open(topic_id)

    def _open_placeholder(self, key: str, title: str, description: str) -> None:
        if self.project is None:
            return
        if self._activate_tab(key):
            return
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)
        heading = QLabel(title)
        font = heading.font()
        font.setPointSize(font.pointSize() + 7)
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)
        layout.addWidget(QLabel(description))
        layout.addWidget(
            QLabel(
                "Moduł został przewidziany w architekturze projektu i będzie rozwijany etapami."
            )
        )
        layout.addStretch(1)
        self._add_tab(key, widget, title)

    # ----------------------------------------------------------------- import

    def _import_log(self) -> None:
        if self.project is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Importuj logi do projektu",
            str(Path.home()),
            "Logi CRT/Kvaser (*.crt.jsonl *.csv);;Sesje CRT (*.crt.jsonl);;CSV (*.csv)",
        )
        for path in paths:
            task = self.services.create_import_task(self.project, path)
            task.signals.completed.connect(self._import_completed)
            task.signals.failed.connect(self._import_failed)
            self._import_tasks.append(task)
            QThreadPool.globalInstance().start(task)
            self.append_output(f"Import rozpoczęty: {path}")

    def _import_completed(self, source: str, target: str) -> None:
        self.append_output(f"Import zakończony: {source} → {target}")
        self.explorer.refresh()
        self._open_session(target)
        self._import_tasks.clear()
        self.log_search.prepare_persistent_session(target)
        self.comparison_sets.refresh()

    def _import_failed(self, source: str, error: str) -> None:
        self.append_output(f"Błąd importu {source}: {error}")
        QMessageBox.critical(self, "Błąd importu", f"{source}\n\n{error}")
        self._import_tasks.clear()

    # ------------------------------------------------------------------- tabs

    def _add_tab(
        self,
        key: str,
        widget: QWidget,
        title: str,
        *,
        closable: bool = True,
    ) -> None:
        self.navigator.add_tab(key, widget, title, closable=closable)

    def _activate_tab(self, key: str) -> bool:
        return self.navigator.activate(key)

    def _close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if (
            isinstance(widget, LiveCaptureWidget)
            and not widget.is_capturing
            and not self.live_log.confirm_unsaved("close_tab")
        ):
            return
        self.log_search.detach_from(widget)
        result = self.navigator.close_at(index)
        if result is CloseTabResult.ACTIVE_CAPTURE:
            QMessageBox.information(
                self,
                "CRT",
                "Zatrzymaj rejestrację przed zamknięciem zakładki Live Capture.",
            )
        self.live_log.sync()

    def close_project_tabs(self) -> None:
        self.navigator.close_all()

    def has_active_capture(self) -> bool:
        return self.navigator.has_active_capture()

    def _show_tab_context_menu(self, point: QPoint) -> None:
        bar = self.tabs.tabBar()
        index = bar.tabAt(point)
        if index < 0:
            return

        menu = QMenu(self)
        close_current = menu.addAction("Zamknij")
        close_others = menu.addAction("Zamknij inne")
        close_all = menu.addAction("Zamknij wszystkie")
        selected = menu.exec(bar.mapToGlobal(point))

        if selected is close_current:
            if self._tab_is_closable(index):
                self._close_tab(index)
        elif selected is close_others:
            self._close_tabs_except(index)
        elif selected is close_all:
            self._close_all_closable_tabs()

    def _tab_is_closable(self, index: int) -> bool:
        widget = self.tabs.widget(index)
        if widget is None:
            return False
        return str(widget.property("crtTabKey") or "") != "welcome"

    def _close_tabs_except(self, keep_index: int) -> None:
        keep_widget = self.tabs.widget(keep_index)
        for index in range(self.tabs.count() - 1, -1, -1):
            widget = self.tabs.widget(index)
            if widget is keep_widget or not self._tab_is_closable(index):
                continue
            self._close_tab(index)

    def _close_all_closable_tabs(self) -> None:
        for index in range(self.tabs.count() - 1, -1, -1):
            if self._tab_is_closable(index):
                self._close_tab(index)

    def _schedule_tooltip_suppressor_scan(self, *_args: object) -> None:
        QTimer.singleShot(0, self._attach_tooltip_suppressor)

    def _attach_tooltip_suppressor(self) -> None:
        current = self.tabs.currentWidget()
        if isinstance(current, QWidget):
            self._table_tooltip_suppressor.attach_to_tables_in(current)

    # ----------------------------------------------------------------- status

    def append_output(self, text: str) -> None:
        """Diagnostic sink for views and controllers (kept off-screen)."""

        self.output_log.append(text)
        _LOG.info("%s", text)

    def _set_capture_status(self, text: str) -> None:
        normalized = (text or "STOPPED").strip()
        upper = normalized.upper()
        if "ERROR" in upper or "BŁĄD" in upper:
            state = "error"
            foreground, background = "#a32121", "#fbe8e8"
        elif "CONNECT" in upper or "ŁĄCZ" in upper:
            state = "connecting"
            foreground, background = "#8a5a00", "#fff4d6"
        elif (
            "CAPTUR" in upper
            or "RECORD" in upper
            or "RUNNING" in upper
            or "AKTYW" in upper
        ):
            state = "running"
            foreground, background = "#176b35", "#e5f4ea"
        else:
            state = "stopped"
            foreground, background = "#5c636b", "transparent"

        self.capture_status.setText(normalized)
        self.capture_indicator.setText(normalized)
        self.capture_indicator.setProperty("state", state)
        self.capture_indicator.setStyleSheet(
            "QLabel#captureIndicator {"
            f"color: {foreground}; background: {background};"
            "border-left: 1px solid #c9cdd2; padding: 2px 10px;"
            "min-width: 78px; font-weight: 600;"
            "}"
        )

    def _update_project_context(self) -> None:
        if self.project is None:
            self.project_context_label.setText("Brak projektu")
            self.transport_status.setText("CAN: —")
            self.mode_status.setText("TRYB: —")
            return

        bitrate = int(self.project.manifest.default_bitrate)
        mode = self.project.manifest.default_receive_mode.upper().replace("_", " ")
        bitrate_text = f"{bitrate // 1000} kbit/s"
        self.project_context_label.setText(
            f"{self.project.manifest.name}  |  {bitrate_text}  |  {mode}"
        )
        self.transport_status.setText(f"CAN: {bitrate_text}")
        self.mode_status.setText(f"TRYB: {mode}")

    # ----------------------------------------------------------------- layout

    def _restore_workspace_layout(self) -> None:
        geometry = self.settings.value(self.GEOMETRY_KEY)
        state = self.settings.value(self.STATE_KEY)
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            restored = self.restoreState(state, self.WORKSPACE_STATE_VERSION)
            if restored:
                return
        self._apply_default_layout()

    def _apply_default_layout(self) -> None:
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.explorer_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.inspector_dock)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.primary_toolbar)

        self.explorer_dock.setVisible(self.project is not None)
        self.inspector_dock.hide()
        self.toggle_inspector_action.setChecked(False)
        self._hide_primary_toolbar()

        self.resizeDocks(
            [self.explorer_dock, self.inspector_dock],
            [280, 320],
            Qt.Orientation.Horizontal,
        )

    def reset_workspace_layout(self) -> None:
        self.settings.remove(self.GEOMETRY_KEY)
        self.settings.remove(self.STATE_KEY)
        self._apply_default_layout()
        self.append_output("Przywrócono domyślny układ okna.")

    def _hide_primary_toolbar(self) -> None:
        self.primary_toolbar.hide()
        self.toggle_primary_toolbar_action.setChecked(False)

    def _collapse_project_dock(self) -> None:
        """Hide Project immediately; Ctrl+Shift+B or View -> Project restores it."""

        self.explorer_dock.hide()
        self.toggle_explorer_action.setChecked(False)

    # ------------------------------------------------------------------ close

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.has_active_capture():
            QMessageBox.warning(
                self,
                "CRT",
                "Zatrzymaj rejestrację przed zamknięciem programu.",
            )
            event.ignore()
            return
        if not self.live_log.confirm_unsaved("close"):
            event.ignore()
            return
        if not self.filter_presets.close_editor():
            event.ignore()
            return

        self.navigator.shutdown_sessions()
        event.accept()
        self.filter_presets.clear_shortcuts()
        self.settings.setValue(self.GEOMETRY_KEY, self.saveGeometry())
        self.settings.setValue(
            self.STATE_KEY,
            self.saveState(self.WORKSPACE_STATE_VERSION),
        )
        self.log_search.reset()
